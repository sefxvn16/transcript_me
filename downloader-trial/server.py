"""Bounded Facebook audio downloads, without cookies or retained media."""

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

VIDEO_URL = "https://www.facebook.com/share/v/1cJ7U3xjpA/"
MAX_BYTES = 64 * 1024 * 1024
ALLOWED_ORIGIN = "https://transcript-me.pages.dev"
FACEBOOK_HOSTS = {"facebook.com", "www.facebook.com", "m.facebook.com",
                  "mbasic.facebook.com", "web.facebook.com", "fb.watch", "www.fb.watch"}
trial_lock = threading.Lock()
trial_result = None


def run_command(args, directory, timeout):
    """Keep tool output off service logs; stop the process tree on timeout."""
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            args, cwd=directory, stdout=stdout, stderr=stderr,
            start_new_session=os.name != "nt",
        )
        deadline = time.monotonic() + timeout
        problem = None
        try:
            while process.poll() is None:
                if time.monotonic() > deadline:
                    problem = "Tool timed out"
                    break
                total_bytes = 0
                for path in Path(directory).iterdir():
                    try:
                        if path.is_file():
                            total_bytes += path.stat().st_size
                    except FileNotFoundError:
                        # yt-dlp may rename .part files while this scan runs.
                        continue
                if total_bytes > MAX_BYTES:
                    problem = "Temporary download exceeded 64 MiB"
                    break
                time.sleep(0.2)
            if problem:
                raise RuntimeError(problem)
            if process.returncode:
                # Avoid including signed media URLs or request headers in the response.
                stderr.seek(0)
                details = stderr.read(65536).decode("utf-8", errors="replace")
                if "HTTP Error 400" in details:
                    raise RuntimeError("Downloader received HTTP 400")
                if "HTTP Error 403" in details:
                    raise RuntimeError("Downloader received HTTP 403")
                if "login" in details.lower() or "log in" in details.lower():
                    raise RuntimeError("Downloader reports login is required")
                if "Cannot parse data" in details:
                    raise RuntimeError("Downloader could not parse video data")
                raise RuntimeError(f"{Path(args[0]).name} exited with code {process.returncode}")
            stdout.seek(0)
            return stdout.read(1024 * 1024).decode("utf-8", errors="replace")
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def is_facebook_url(url):
    try:
        parsed = urlsplit(url)
        return (isinstance(url, str) and len(url) <= 2048
                and parsed.scheme == "https" and parsed.hostname in FACEBOOK_HOSTS
                and parsed.port in (None, 443) and not parsed.username and not parsed.password)
    except (ValueError, TypeError, AttributeError):
        return False


class FacebookRedirectHandler(HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, request, response, code, message, headers, new_url):
        if not is_facebook_url(new_url):
            raise RuntimeError("Facebook redirected to an unsupported host")
        return super().redirect_request(request, response, code, message, headers, new_url)


def resolve_video_url(url):
    # Share links need redirects before the Facebook-specific extractor can match.
    if urlsplit(url).hostname not in {"fb.watch", "www.fb.watch"} and not urlsplit(url).path.startswith("/share/"):
        return url
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with build_opener(FacebookRedirectHandler()).open(request, timeout=15) as response:
        resolved = response.geturl()
    if not is_facebook_url(resolved):
        raise RuntimeError("Facebook redirected to an unsupported host")
    return resolved


def perform_trial(video_url=VIDEO_URL, include_audio=False):
    started = time.monotonic()
    stage = "download"
    try:
        with tempfile.TemporaryDirectory(prefix="transcript-trial-") as directory:
            video_url = resolve_video_url(video_url)
            run_command([
                sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist",
                "--no-cache-dir", "--use-extractors", "(?i)facebook.*",
                "--no-progress", "--no-warnings", "--socket-timeout", "15",
                "--retries", "0", "--extractor-retries", "0",
                "--max-filesize", "32M", "--match-filter", "duration <= 3600",
                "-f", "bestaudio/best", "-o", "source.%(ext)s", video_url,
            ], directory, 150)
            sources = [p for p in Path(directory).glob("source.*") if p.suffix not in {".part", ".ytdl"}]
            if len(sources) != 1 or not sources[0].stat().st_size:
                raise RuntimeError("Downloader did not produce a complete media file")
            source = sources[0]
            source_bytes = source.stat().st_size
            if source_bytes > 32 * 1024 * 1024:
                raise RuntimeError("Video download exceeded 32 MiB")
            source_probe = json.loads(run_command([
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "json", str(source),
            ], directory, 10))
            source_duration = float(source_probe.get("format", {}).get("duration", 0))
            if not 0 < source_duration <= 3600:
                raise RuntimeError("Video duration must be between 0 and 3600 seconds")
            stage = "convert"
            audio = Path(directory) / "audio.mp3"
            run_command([
                "ffmpeg", "-nostdin", "-v", "error", "-i", str(source),
                "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k",
                "-threads", "1", "-t", "3600", str(audio),
            ], directory, 90)
            stage = "verify"
            probe = json.loads(run_command([
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "format=duration:stream=codec_name,sample_rate,channels",
                "-of", "json", str(audio),
            ], directory, 10))
            streams = probe.get("streams", [])
            duration = float(probe.get("format", {}).get("duration", 0))
            if not streams or duration <= 0:
                raise RuntimeError("Converted file has no valid audio stream")
            if source_bytes + audio.stat().st_size > MAX_BYTES:
                raise RuntimeError("Temporary download exceeded 64 MiB")
            with audio.open("rb") as audio_file:
                digest = hashlib.file_digest(audio_file, "sha256").hexdigest()
            result = {
                "ok": True, "sourceBytes": source_bytes,
                "audioBytes": audio.stat().st_size, "durationSeconds": round(duration, 3),
                "stream": streams[0], "sha256": digest,
            }
            if include_audio:
                # Bound by MAX_BYTES; the temporary file is deleted before replying.
                result["audio"] = audio.read_bytes()
        result["temporaryFilesDeleted"] = not Path(directory).exists()
        result["elapsedSeconds"] = round(time.monotonic() - started, 2)
        return result
    except Exception as error:
        return {"ok": False, "stage": stage, "error": str(error),
                "elapsedSeconds": round(time.monotonic() - started, 2)}


class Handler(BaseHTTPRequestHandler):
    def cors_headers(self):
        self.send_header("Vary", "Origin")
        if self.headers.get("Origin") == ALLOWED_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)

    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if self.path != "/audio" or self.headers.get("Origin") != ALLOWED_ORIGIN:
            self.send_json(403, {"error": "Origin is not allowed"})
            return
        self.send_response(204)
        self.cors_headers()
        self.send_header("Access-Control-Allow-Methods", "POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"ok": True, "service": "transcript-downloader-trial",
                                 "trialFinished": trial_result is not None})
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        global trial_result
        if self.path == "/audio":
            self.download_audio()
            return
        if self.path != "/trial":
            self.send_json(404, {"error": "Not found"})
            return
        if not trial_lock.acquire(blocking=False):
            self.send_json(409, {"error": "Trial is already running"})
            return
        try:
            # Repeat requests return the recorded result, not another download.
            if trial_result is None:
                trial_result = perform_trial()
                print(json.dumps({"trial": trial_result}), flush=True)
            self.send_json(200 if trial_result["ok"] else 422, trial_result)
        finally:
            trial_lock.release()

    def download_audio(self):
        if self.headers.get("Origin") != ALLOWED_ORIGIN:
            self.send_json(403, {"error": "Origin is not allowed"})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "Expected application/json"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= 4096 or self.headers.get("Transfer-Encoding"):
            self.send_json(413, {"error": "Request body must be 1 to 4096 bytes"})
            return
        try:
            self.connection.settimeout(15)
            body = json.loads(self.rfile.read(length))
            url = body.get("url") if isinstance(body, dict) else None
        except (ValueError, OSError):
            self.send_json(400, {"error": "Invalid JSON body"})
            return
        if not is_facebook_url(url):
            self.send_json(400, {"error": "Expected a public Facebook HTTPS video link"})
            return
        if not trial_lock.acquire(blocking=False):
            self.send_json(409, {"error": "Downloader is busy. Please try again shortly."})
            return
        try:
            result = perform_trial(url, include_audio=True)
            if not result["ok"]:
                self.send_json(422, {"error": result["error"], "stage": result["stage"]})
                return
            audio = result.pop("audio")
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(audio)))
            self.send_header("Cache-Control", "no-store")
            self.cors_headers()
            self.end_headers()
            self.wfile.write(audio)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            # A stopped browser request must not retain files or the busy lock.
            pass
        finally:
            trial_lock.release()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), Handler)
    print("Downloader trial ready", flush=True)
    server.serve_forever()
