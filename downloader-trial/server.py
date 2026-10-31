"""One fixed public-video trial, without cookies, a database or retained media."""

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

VIDEO_URL = "https://www.facebook.com/share/v/1cJ7U3xjpA/"
MAX_BYTES = 64 * 1024 * 1024
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


def perform_trial():
    started = time.monotonic()
    stage = "download"
    try:
        with tempfile.TemporaryDirectory(prefix="transcript-trial-") as directory:
            run_command([
                sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist",
                "--no-progress", "--no-warnings", "--socket-timeout", "15",
                "--retries", "0", "--extractor-retries", "0",
                "--max-filesize", "32M", "--match-filter", "duration <= 3600",
                "-f", "bestaudio/best", "-o", "source.%(ext)s", VIDEO_URL,
            ], directory, 150)
            sources = [p for p in Path(directory).glob("source.*") if p.suffix not in {".part", ".ytdl"}]
            if len(sources) != 1 or not sources[0].stat().st_size:
                raise RuntimeError("Downloader did not produce a complete media file")
            source = sources[0]
            source_bytes = source.stat().st_size
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
            with audio.open("rb") as audio_file:
                digest = hashlib.file_digest(audio_file, "sha256").hexdigest()
            result = {
                "ok": True, "sourceBytes": source_bytes,
                "audioBytes": audio.stat().st_size, "durationSeconds": round(duration, 3),
                "stream": streams[0], "sha256": digest,
            }
        result["temporaryFilesDeleted"] = not Path(directory).exists()
        result["elapsedSeconds"] = round(time.monotonic() - started, 2)
        return result
    except Exception as error:
        return {"ok": False, "stage": stage, "error": str(error),
                "elapsedSeconds": round(time.monotonic() - started, 2)}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"ok": True, "service": "transcript-downloader-trial",
                                 "trialFinished": trial_result is not None})
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        global trial_result
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

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), Handler)
    print("Downloader trial ready", flush=True)
    server.serve_forever()
