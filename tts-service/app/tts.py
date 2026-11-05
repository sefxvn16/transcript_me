"""
Module Text-to-Speech: sinh file MP3 bằng Azure Speech (API chính thức của Microsoft, giọng Neural).

Cấu hình qua biến môi trường (hoặc file pdf_audiobook/.env khi chạy local):
- AZURE_SPEECH_KEY:    key của Speech resource (Azure portal > Keys and Endpoint)
- AZURE_SPEECH_REGION: region của resource, ví dụ southeastasia
Gói Free F0: 0,5 triệu ký tự/tháng, tối đa 20 request mỗi 60 giây (không nâng được).
"""

import os
import time
import asyncio
import logging
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional
from xml.sax.saxutils import escape, quoteattr

import requests

logger = logging.getLogger(__name__)

AVAILABLE_VOICES: List[Dict[str, str]] = [
    {"id": "vi-VN-HoaiMyNeural", "name": "Hoài My (Nữ - Truyền cảm, tự nhiên)", "lang": "vi-VN", "gender": "Female", "is_default": True},
    {"id": "vi-VN-NamMinhNeural", "name": "Nam Minh (Nam - Trầm ấm, dõng dạc)", "lang": "vi-VN", "gender": "Male", "is_default": False},
    {"id": "en-US-JennyNeural", "name": "Jenny (Nữ - Tiếng Anh Mỹ)", "lang": "en-US", "gender": "Female", "is_default": False},
    {"id": "en-US-GuyNeural", "name": "Guy (Nam - Tiếng Anh Mỹ)", "lang": "en-US", "gender": "Male", "is_default": False},
]
DEFAULT_VOICE = "vi-VN-HoaiMyNeural"
SUPPORTED_RATES = ["-20%", "+0%", "+10%", "+20%", "+30%"]

OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
REQUEST_TIMEOUT_SECONDS = 120
# Giới hạn F0: 20 request / 60 giây. Gói S0 có thể đặt cao hơn qua biến môi trường.
MAX_REQUESTS_PER_MINUTE = int(os.environ.get("AZURE_TTS_MAX_PER_MINUTE", "20"))


class TTSConfigError(RuntimeError):
    pass


def _load_dotenv() -> None:
    """Đọc pdf_audiobook/.env (KEY=VALUE) khi chạy local; biến đã có trong môi trường được giữ nguyên."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def is_configured() -> bool:
    return bool(os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION"))


class _RateLimiter:
    """Cửa sổ trượt: không quá max_calls lần gọi trong period giây (dùng chung cho mọi tác vụ)."""

    def __init__(self, max_calls: int, period: float):
        self.max_calls, self.period = max_calls, period
        self.calls: deque = deque()
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self.lock:
            while True:
                now = time.monotonic()
                while self.calls and now - self.calls[0] >= self.period:
                    self.calls.popleft()
                if len(self.calls) < self.max_calls:
                    self.calls.append(now)
                    return
                await asyncio.sleep(self.period - (now - self.calls[0]) + 0.05)


_rate_limiter = _RateLimiter(MAX_REQUESTS_PER_MINUTE, 60.0)


def format_rate(rate: str) -> str:
    """Chuẩn hóa rate: '0%' -> '+0%', '10' -> '+10%', '-20%' giữ nguyên."""
    rate = (rate or "").strip()
    if not rate:
        return "+0%"
    if not rate.endswith("%"):
        rate += "%"
    if not rate.startswith(("+", "-")):
        rate = f"+{rate}"
    return "+0%" if rate in ("+0%", "-0%") else rate


def build_ssml(text: str, voice: str, rate: str) -> str:
    lang = "-".join(voice.split("-")[:2])
    return (
        f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang={quoteattr(lang)}>"
        f"<voice name={quoteattr(voice)}><prosody rate={quoteattr(rate)}>{escape(text)}</prosody></voice></speak>"
    )


def _post_tts_sync(ssml: str) -> requests.Response:
    region = os.environ["AZURE_SPEECH_REGION"].strip()
    return requests.post(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        headers={
            "Ocp-Apim-Subscription-Key": os.environ["AZURE_SPEECH_KEY"].strip(),
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
            "User-Agent": "pdf-audiobook",
        },
        data=ssml.encode("utf-8"),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


async def synthesize_speech(
    text: str,
    output_path: Path,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    max_retries: int = 5
) -> Path:
    """
    Chuyển một đoạn văn bản thành file MP3 bằng Azure Speech.
    Lỗi tạm thời (429, 5xx, mạng) được thử lại có backoff; lỗi cấu hình (400, 401, 403) báo ngay.
    """
    if not is_configured():
        raise TTSConfigError("Máy chủ chưa cấu hình AZURE_SPEECH_KEY và AZURE_SPEECH_REGION.")

    cleaned_text = text.strip()
    if not cleaned_text:
        raise ValueError("Văn bản truyền vào để tạo giọng nói bị rỗng.")

    if voice not in {v["id"] for v in AVAILABLE_VOICES}:
        logger.warning(f"Giọng {voice} không có trong danh sách, dùng {DEFAULT_VOICE}")
        voice = DEFAULT_VOICE

    ssml = build_ssml(cleaned_text, voice, format_rate(rate))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Optional[str] = None

    for attempt in range(1, max_retries + 1):
        await _rate_limiter.acquire()
        wait_time = min(2 ** attempt, 30)
        try:
            resp = await asyncio.to_thread(_post_tts_sync, ssml)
        except requests.RequestException as e:
            last_error = f"lỗi mạng: {e}"
        else:
            if resp.status_code == 200 and resp.content:
                output_path.write_bytes(resp.content)
                return output_path
            if resp.status_code in (400, 401, 403, 415):
                hint = " (kiểm tra AZURE_SPEECH_KEY và AZURE_SPEECH_REGION)" if resp.status_code in (401, 403) else ""
                raise RuntimeError(f"Azure Speech từ chối yêu cầu: HTTP {resp.status_code}{hint}")
            last_error = f"HTTP {resp.status_code}"
            retry_after = resp.headers.get("Retry-After", "")
            if retry_after.isdigit():
                wait_time = max(wait_time, int(retry_after))

        logger.warning(f"[TTS] Lần thử {attempt}/{max_retries} lỗi: {last_error}. Thử lại sau {wait_time}s...")
        if attempt < max_retries:
            await asyncio.sleep(wait_time)

    raise RuntimeError(f"Không tạo được âm thanh bằng Azure Speech sau {max_retries} lần thử: {last_error}")


def get_available_voices() -> List[Dict[str, str]]:
    """Trả về danh sách các giọng đọc hỗ trợ."""
    return AVAILABLE_VOICES
