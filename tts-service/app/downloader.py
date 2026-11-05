"""
Module tiếp nhận tài liệu (PDF hoặc Word .docx) từ upload trực tiếp, link trực tiếp, Google Drive hoặc OneDrive.
Định dạng được nhận diện theo nội dung file, không theo tên.
"""

import re
import uuid
import socket
import asyncio
import logging
import zipfile
import ipaddress
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urljoin, parse_qs, urlencode, urlunparse

import requests
import gdown
from fastapi import UploadFile, HTTPException

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_REDIRECTS = 5
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class FileTooLargeError(ValueError):
    pass


def sanitize_filename(filename: str) -> str:
    """Loại bỏ các ký tự không hợp lệ trong tên file."""
    clean = re.sub(r'[\\/*?:"<>|]', "", filename)
    clean = clean.strip().replace(" ", "_")
    return clean if clean else "document"


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _host_matches(url: str, domains: tuple) -> bool:
    host = _host(url)
    return any(host == d or host.endswith("." + d) for d in domains)


def is_google_drive_link(url: str) -> bool:
    return _host_matches(url, ("drive.google.com", "docs.google.com"))


def is_onedrive_link(url: str) -> bool:
    return _host_matches(url, ("1drv.ms", "onedrive.live.com", "sharepoint.com"))


def ensure_public_http_url(url: str) -> None:
    """Chỉ cho phép http(s) tới địa chỉ Internet công khai (chặn localhost, mạng nội bộ của server)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Link phải bắt đầu bằng http:// hoặc https://.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror:
        raise ValueError(f"Không phân giải được tên miền {parsed.hostname}.")
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ValueError("Link trỏ tới địa chỉ nội bộ, không được phép.")


def extract_gdrive_file_id(url: str) -> Optional[str]:
    """
    Trích xuất file_id từ URL Google Drive công khai:
    - https://drive.google.com/file/d/<FILE_ID>/view?usp=sharing
    - https://drive.google.com/open?id=<FILE_ID>
    - https://drive.google.com/uc?id=<FILE_ID>
    - https://docs.google.com/document/d/<FILE_ID>/edit
    """
    for pattern in (r"/(?:file|document)/d/([a-zA-Z0-9_-]+)", r"[?&]id=([a-zA-Z0-9_-]+)"):
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _get_following_redirects(url: str, method: str = "GET", **kwargs) -> requests.Response:
    """Gửi request, tự theo redirect nhưng kiểm tra từng đích có phải địa chỉ công khai."""
    headers = {"User-Agent": USER_AGENT}
    for _ in range(MAX_REDIRECTS + 1):
        ensure_public_http_url(url)
        resp = requests.request(method, url, headers=headers, allow_redirects=False, **kwargs)
        if resp.is_redirect and "location" in resp.headers:
            url = urljoin(url, resp.headers["location"])
            resp.close()
            continue
        return resp
    raise ValueError("Link chuyển hướng quá nhiều lần.")


def convert_onedrive_url_to_direct(url: str) -> str:
    """
    Chuyển URL OneDrive công khai thành link tải trực tiếp (download=1).
    Link rút gọn 1drv.ms được giải quyết redirect trước.
    """
    if _host_matches(url, ("1drv.ms",)):
        try:
            resp = _get_following_redirects(url, method="HEAD", timeout=15)
            url = resp.url
        except Exception as e:
            logger.warning(f"Không thể resolve link 1drv.ms, thử dùng link gốc: {e}")

    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    query_params["download"] = ["1"]
    return urlunparse(parsed._replace(query=urlencode(query_params, doseq=True)))


def detect_document_suffix(path: Path) -> Optional[str]:
    """Nhận diện PDF/DOCX theo nội dung; trả None nếu không phải hai loại này."""
    with open(path, "rb") as f:
        header = f.read(5)
    if header.startswith(b"%PDF"):
        return ".pdf"
    if header.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(path) as z:
                if "word/document.xml" in z.namelist():
                    return ".docx"
        except zipfile.BadZipFile:
            return None
    return None


async def save_upload_file(upload_file: UploadFile, dest_folder: Path) -> Path:
    """Lưu file upload, giới hạn MAX_FILE_BYTES."""
    dest_folder.mkdir(parents=True, exist_ok=True)
    target_path = dest_folder / f"{uuid.uuid4().hex[:8]}_{sanitize_filename(Path(upload_file.filename or 'document').stem)}"

    written = 0
    try:
        with open(target_path, "wb") as f:
            while chunk := await upload_file.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_FILE_BYTES:
                    raise FileTooLargeError()
                f.write(chunk)
    except FileTooLargeError:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail=f"File vượt quá {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    except Exception as e:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu file upload: {e}")

    return target_path


def _download_gdrive_sync(file_id: str, dest_path: Path) -> Path:
    """Tải file từ Google Drive bằng gdown (đồng bộ)."""
    try:
        output = gdown.download(id=file_id, output=str(dest_path), quiet=True)
        if not output or not Path(output).exists() or Path(output).stat().st_size == 0:
            raise ValueError("File tải về rỗng hoặc link chưa được chia sẻ công khai.")
        return Path(output)
    except Exception as e:
        dest_path.unlink(missing_ok=True)
        logger.error(f"Lỗi tải Google Drive: {e}")
        raise ValueError(f"Không thể tải từ Google Drive (hãy bật 'Bất kỳ ai có đường liên kết'): {e}")


def _download_direct_url_sync(url: str, dest_path: Path) -> Path:
    """Tải file từ URL trực tiếp hoặc OneDrive (stream, giới hạn MAX_FILE_BYTES)."""
    try:
        with _get_following_redirects(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            written = 0
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=512 * 1024):
                    written += len(chunk)
                    if written > MAX_FILE_BYTES:
                        raise FileTooLargeError(f"File vượt quá {MAX_FILE_BYTES // (1024 * 1024)} MB.")
                    f.write(chunk)
        if dest_path.stat().st_size == 0:
            raise ValueError("File tải về rỗng.")
        return dest_path
    except Exception as e:
        dest_path.unlink(missing_ok=True)
        logger.error(f"Lỗi tải từ URL: {e}")
        raise ValueError(f"Không thể tải file từ link: {e}")


async def download_from_url(url: str, dest_folder: Path) -> Path:
    """Phân loại và tải file từ link Google Drive, OneDrive hoặc link trực tiếp."""
    dest_folder.mkdir(parents=True, exist_ok=True)
    prefix = uuid.uuid4().hex[:8]

    try:
        if is_google_drive_link(url):
            file_id = extract_gdrive_file_id(url)
            if not file_id:
                raise ValueError("Không nhận diện được File ID từ link Google Drive.")
            if "/document/d/" in url:
                # Google Docs gốc không phải file: xuất ra .docx
                export_url = f"https://docs.google.com/document/d/{file_id}/export?format=docx"
                path = await asyncio.to_thread(_download_direct_url_sync, export_url, dest_folder / f"{prefix}_gdocs_document")
            else:
                path = await asyncio.to_thread(_download_gdrive_sync, file_id, dest_folder / f"{prefix}_gdrive_document")
        elif is_onedrive_link(url):
            direct_url = await asyncio.to_thread(convert_onedrive_url_to_direct, url)
            path = await asyncio.to_thread(_download_direct_url_sync, direct_url, dest_folder / f"{prefix}_onedrive_document")
        else:
            stem = sanitize_filename(Path(urlparse(url).path).stem or "online_document")
            path = await asyncio.to_thread(_download_direct_url_sync, url, dest_folder / f"{prefix}_{stem}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if path.stat().st_size > MAX_FILE_BYTES:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail=f"File vượt quá {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    return path


async def acquire_document_file(
    upload_file: Optional[UploadFile],
    url: Optional[str],
    dest_folder: Path
) -> Path:
    """
    Cổng vào: nhận tài liệu từ upload hoặc link, xác thực là PDF hoặc DOCX
    và trả về đường dẫn có đuôi đúng định dạng (.pdf/.docx).
    """
    if upload_file and upload_file.filename:
        file_path = await save_upload_file(upload_file, dest_folder)
    elif url and url.strip():
        file_path = await download_from_url(url.strip(), dest_folder)
    else:
        raise HTTPException(status_code=400, detail="Vui lòng tải lên file PDF/Word hoặc dán link tài liệu.")

    suffix = detect_document_suffix(file_path)
    if suffix is None:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="File không phải PDF hoặc Word (.docx). File .doc đời cũ hãy lưu lại thành .docx hoặc PDF.")

    return file_path.rename(file_path.with_name(file_path.name + suffix))
