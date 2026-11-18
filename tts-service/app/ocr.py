"""
Nhận dạng chữ (OCR) cho PDF dạng ảnh bằng Azure Document Intelligence (model prebuilt-read, API 2024-11-30).

Cấu hình qua biến môi trường (hoặc pdf_audiobook/.env khi chạy local, đã được app.tts nạp):
- AZURE_DOCINTEL_ENDPOINT: ví dụ https://<tên-resource>.cognitiveservices.azure.com/
- AZURE_DOCINTEL_KEY:      key của resource (Keys and Endpoint)
Gói Free F0: 500 trang/tháng, 20 lần gọi/phút (ghi trên Azure portal khi tạo resource), mỗi lần gọi
chỉ xử lý 2 trang, file ≤ 4 MB => gửi từng trang dưới dạng ảnh JPEG, mọi lần gọi (gửi ảnh và hỏi kết quả)
cách nhau tối thiểu MIN_INTERVAL_SECONDS.
"""

import io
import os
import time
import asyncio
import logging
from pathlib import Path
from typing import Callable, Awaitable, Dict, List, Optional

import requests
import pypdfium2 as pdfium

logger = logging.getLogger(__name__)

API_VERSION = "2024-11-30"
MIN_INTERVAL_SECONDS = 3.1          # F0: 20 lần gọi/phút => ~3 giây/lần
MAX_IMAGE_BYTES = 4 * 1024 * 1024   # F0: tối đa 4 MB mỗi lần gửi
TARGET_LONG_SIDE_PX = 2000          # đủ nét cho chữ thường, ảnh JPEG thường vài trăm KB
POLL_TIMEOUT_SECONDS = 120


def is_configured() -> bool:
    return bool(os.environ.get("AZURE_DOCINTEL_ENDPOINT") and os.environ.get("AZURE_DOCINTEL_KEY"))


class _Spacer:
    """Mọi lời gọi tới Document Intelligence cách nhau tối thiểu một khoảng (dùng chung toàn app)."""

    def __init__(self, interval: float):
        self.interval = interval
        self.last = 0.0
        self.lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self.lock:
            delay = self.last + self.interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self.last = time.monotonic()


_spacer = _Spacer(MIN_INTERVAL_SECONDS)


def render_page_jpeg(pdf_path: Path, index: int) -> bytes:
    """Chuyển một trang PDF thành ảnh JPEG (cạnh dài ~2000 px), giảm chất lượng nếu vượt 4 MB."""
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        page = doc[index]
        width, height = page.get_size()
        scale = min(4.0, TARGET_LONG_SIDE_PX / max(width, height, 1))
        image = page.render(scale=scale).to_pil().convert("RGB")
        page.close()
    finally:
        doc.close()
    for quality in (85, 70, 55, 40):
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= MAX_IMAGE_BYTES:
            return buf.getvalue()
    image.thumbnail((TARGET_LONG_SIDE_PX // 2, TARGET_LONG_SIDE_PX // 2))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=60)
    return buf.getvalue()


def _headers(content_type: Optional[str] = None) -> dict:
    h = {"Ocp-Apim-Subscription-Key": os.environ["AZURE_DOCINTEL_KEY"].strip()}
    if content_type:
        h["Content-Type"] = content_type
    return h


async def _request(method: str, url: str, **kwargs) -> requests.Response:
    """Gửi request qua bộ giãn cách; 429/5xx thử lại có backoff (tôn trọng Retry-After)."""
    last = None
    for attempt in range(1, 6):
        await _spacer.wait()
        try:
            resp = await asyncio.to_thread(requests.request, method, url, timeout=60, **kwargs)
        except requests.RequestException as e:
            # Không đưa str(e) vào thông báo: nó chứa URL ghép từ AZURE_DOCINTEL_ENDPOINT (trang status là công khai)
            last = f"lỗi mạng ({type(e).__name__})"
        else:
            if resp.status_code < 400:
                return resp
            if resp.status_code in (400, 401, 403, 404, 415):
                detail = resp.text[:200]
                hint = " (kiểm tra AZURE_DOCINTEL_ENDPOINT và AZURE_DOCINTEL_KEY)" if resp.status_code in (401, 403, 404) else ""
                raise RuntimeError(f"Document Intelligence từ chối yêu cầu: HTTP {resp.status_code}{hint}: {detail}")
            last = f"HTTP {resp.status_code}"
            retry_after = resp.headers.get("Retry-After", "")
            if retry_after.isdigit():
                await asyncio.sleep(int(retry_after))
                continue
        await asyncio.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"Document Intelligence không phản hồi sau 5 lần thử: {last}")


async def ocr_image(jpeg: bytes) -> str:
    """Gửi một ảnh tới prebuilt-read và trả về toàn bộ chữ nhận dạng được."""
    endpoint = os.environ["AZURE_DOCINTEL_ENDPOINT"].strip().rstrip("/")
    if not endpoint.startswith("https://"):
        raise RuntimeError("AZURE_DOCINTEL_ENDPOINT không hợp lệ: phải là URL dạng https://<tên-resource>.cognitiveservices.azure.com/")
    url = f"{endpoint}/documentintelligence/documentModels/prebuilt-read:analyze?api-version={API_VERSION}"
    resp = await _request("POST", url, headers=_headers("image/jpeg"), data=jpeg)
    op_url = resp.headers.get("Operation-Location")
    if not op_url:
        raise RuntimeError("Document Intelligence không trả về Operation-Location.")

    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        result = (await _request("GET", op_url, headers=_headers())).json()
        status = result.get("status")
        if status == "succeeded":
            return (result.get("analyzeResult") or {}).get("content", "") or ""
        if status == "failed":
            raise RuntimeError(f"Nhận dạng chữ thất bại: {result.get('error', {}).get('message', 'không rõ')}")
    raise RuntimeError("Nhận dạng chữ quá lâu không xong.")


async def ocr_pdf_pages(
    pdf_path: Path,
    indices: List[int],
    on_page_done: Optional[Callable[[int, int], Awaitable[None]]] = None,
) -> Dict[int, str]:
    """OCR lần lượt các trang (chỉ số 0-based). Trả về {chỉ số trang: chữ}."""
    if not is_configured():
        raise RuntimeError("Máy chủ chưa cấu hình Azure Document Intelligence (AZURE_DOCINTEL_ENDPOINT, AZURE_DOCINTEL_KEY).")
    texts: Dict[int, str] = {}
    for done, index in enumerate(indices, start=1):
        jpeg = await asyncio.to_thread(render_page_jpeg, pdf_path, index)
        texts[index] = await ocr_image(jpeg)
        if on_page_done:
            await on_page_done(done, len(indices))
    return texts
