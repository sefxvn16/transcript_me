"""
FastAPI Main Application
Quản lý các API endpoints và luồng xử lý bất đồng bộ cho cả 2 chế độ:
- Chế độ 1: Xuất Audio Offline (Tải về máy)
- Chế độ 2: Đọc luôn (Audiobook Player với Prefetch Buffer)
Chạy local (python run.py) hoặc làm backend public trên Render cho transcript-me.pages.dev.
"""

import re
import time
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.downloader import acquire_document_file
from app.extractor import extract_and_chunk_document, extract_document_sections, chunks_for_text
from app.tts import synthesize_speech, get_available_voices, is_configured, SUPPORTED_RATES
from app.utils import (
    task_manager,
    stream_manager,
    merge_mp3_files,
    group_and_merge_chunks,
    create_zip_archive,
    cleanup_old_outputs
)

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("pdf_audiobook")

# Cấu hình đường dẫn thư mục
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
AUDIO_OUTPUT_DIR = STORAGE_DIR / "audio_output"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Số đoạn gửi Azure Speech song song ở Chế độ 1 (tốc độ tổng còn bị giới hạn trong tts.py)
OFFLINE_CONCURRENCY = 3
# File và phiên cũ hơn mức này bị dọn khi có yêu cầu mới (server public, đĩa tạm)
MAX_AGE_SECONDS = 6 * 3600

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="PDF Audiobook Studio",
    description="Chuyển sách PDF/Word thành giọng nói với Azure Speech",
    version="1.1.0"
)

# Giao diện trên transcript-me.pages.dev gọi API này từ origin khác; localhost để thử khi phát triển
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://(?:[a-z0-9-]+\.)?transcript-me\.pages\.dev|http://(?:localhost|127\.0\.0\.1)(?::\d+)?",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/audio", StaticFiles(directory=str(AUDIO_OUTPUT_DIR)), name="audio")


# --------------------------------------------------------------------------
# ROUTES GIAO DIỆN VÀ THÔNG TIN CẤU HÌNH
# --------------------------------------------------------------------------

@app.get("/")
async def serve_home():
    """Hiển thị giao diện local của ứng dụng."""
    return FileResponse(TEMPLATES_DIR / "index.html", media_type="text/html")


@app.get("/health")
async def health():
    return {"status": "ok", "tts_configured": is_configured()}


@app.get("/api/voices")
async def api_get_voices():
    """Trả về danh sách giọng đọc và tốc độ hỗ trợ."""
    return {
        "voices": get_available_voices(),
        "rates": SUPPORTED_RATES
    }


@app.get("/download/{folder}/{filename}")
async def download_output(folder: str, filename: str):
    """
    Tải file kết quả kèm Content-Disposition: attachment, để điện thoại lưu thành file
    (trình duyệt bỏ qua thuộc tính download của link khác origin).
    """
    path = (AUDIO_OUTPUT_DIR / folder / filename).resolve()
    if not folder.startswith("offline_") or path.parent.parent != AUDIO_OUTPUT_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy file (file cũ hơn 6 giờ đã bị xóa).")
    # Bỏ tiền tố ngẫu nhiên "xxxxxxxx_" (chỉ để tránh trùng trên máy chủ) khỏi tên file người dùng lưu
    return FileResponse(path, filename=re.sub(r"^[0-9a-f]{8}_", "", filename))


def _require_tts() -> None:
    if not is_configured():
        raise HTTPException(status_code=503, detail="Máy chủ chưa cấu hình Azure Speech (AZURE_SPEECH_KEY, AZURE_SPEECH_REGION).")


def _cleanup_storage() -> None:
    cleanup_old_outputs([UPLOAD_DIR, AUDIO_OUTPUT_DIR], MAX_AGE_SECONDS)


def _file_info(task_id: str, path: Path) -> dict:
    return {
        "filename": path.name,
        "download_url": f"/download/offline_{task_id}/{path.name}",
        "size_mb": round(path.stat().st_size / (1024 * 1024), 2)
    }


def _root_error(e: BaseException) -> BaseException:
    """Lấy lỗi gốc từ ExceptionGroup (TaskGroup) để thông báo dễ hiểu."""
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return e


# --------------------------------------------------------------------------
# PHÂN TÍCH TÀI LIỆU: CHIA THEO CHƯƠNG/MỤC ĐỂ NGƯỜI DÙNG CHỌN PHẦN MUỐN NGHE
# --------------------------------------------------------------------------

# doc_id -> {"title", "created_at", "sections": [{"id", "title", "text", ...}]}
_documents: Dict[str, dict] = {}


def _display_title(stem: str) -> str:
    return re.sub(r"^[0-9a-f]{8}_", "", stem)


@app.post("/api/document")
async def analyze_document(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None)
):
    """
    Nhận PDF/DOCX, chia thành các phần (theo mục lục/heading, hoặc theo dung lượng)
    và trả về danh sách phần để người dùng chọn. Chưa gọi Azure Speech, chưa tốn quota.
    """
    await asyncio.to_thread(_cleanup_storage)
    doc_path = await acquire_document_file(file, url, UPLOAD_DIR)
    try:
        doc = await asyncio.to_thread(extract_document_sections, doc_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        doc_path.unlink(missing_ok=True)  # đã lấy xong chữ, không cần giữ file gốc

    cutoff = time.time() - MAX_AGE_SECONDS
    for key in [k for k, v in _documents.items() if v["created_at"] < cutoff]:
        del _documents[key]
    doc_id = uuid.uuid4().hex[:12]
    title = _display_title(doc_path.stem)
    _documents[doc_id] = {"title": title, "created_at": time.time(), "sections": doc["sections"]}

    return {
        "doc_id": doc_id,
        "title": title,
        "structure": doc["structure"],
        "total_pages": doc["total_pages"],
        "total_characters": doc["total_characters"],
        "sections": [{k: v for k, v in sec.items() if k != "text"} for sec in doc["sections"]],
    }


def _selected_text(doc_id: str, section_ids: Optional[str]) -> Tuple[str, str]:
    """Trả về (tiêu đề, văn bản) của các phần đã chọn; section_ids dạng "0,3,4", rỗng = cả tài liệu."""
    doc = _documents.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Tài liệu đã hết hạn (quá 6 giờ hoặc máy chủ khởi động lại). Hãy tải lên lại.")
    sections = doc["sections"]
    if section_ids and section_ids.strip():
        try:
            wanted = {int(x) for x in section_ids.split(",") if x.strip()}
        except ValueError:
            raise HTTPException(status_code=400, detail="Danh sách phần không hợp lệ.")
        sections = [sec for sec in sections if sec["id"] in wanted]
        if not sections:
            raise HTTPException(status_code=400, detail="Chưa chọn phần nào để đọc.")
    if len(sections) == 1:
        title = f"{doc['title']} - {sections[0]['title']}"
    elif len(sections) < len(doc["sections"]):
        title = f"{doc['title']} - {len(sections)} phần"
    else:
        title = doc["title"]
    return title, "\n\n".join(sec["text"] for sec in sections)


async def _resolve_source(doc_id, section_ids, file, url) -> Tuple[str, Optional[str], Optional[Path]]:
    """(tiêu đề, văn bản đã chọn | None, file tài liệu | None): ưu tiên doc_id, nếu không thì nhận file/link như cũ."""
    if doc_id:
        title, text = _selected_text(doc_id, section_ids)
        return title, text, None
    doc_path = await acquire_document_file(file, url, UPLOAD_DIR)
    return _display_title(doc_path.stem), None, doc_path


def _safe_filename(title: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", title).strip().replace(" ", "_")[:120] or "audiobook"


# --------------------------------------------------------------------------
# CHẾ ĐỘ 1: XUẤT AUDIO OFFLINE (TẢI VỀ MÁY)
# --------------------------------------------------------------------------

async def _process_offline_task(
    task_id: str,
    file_path: Optional[Path],
    text: Optional[str],
    voice: str,
    rate: str,
    merge_option: str,
    original_title: str
):
    """Tiến trình nền chuyển trọn vẹn tài liệu thành file âm thanh."""
    task_audio_dir = AUDIO_OUTPUT_DIR / f"offline_{task_id}"
    task_audio_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Bước 1: Trích xuất và chia chunks
        await task_manager.update_task(
            task_id,
            status="PROCESSING",
            progress=10,
            current_step="Đang đọc tài liệu và làm sạch văn bản..."
        )

        if text is not None:
            extracted = await asyncio.to_thread(chunks_for_text, text)
        else:
            extracted = await asyncio.to_thread(extract_and_chunk_document, file_path)
        chunks = extracted["chunks"]
        total_chunks = len(chunks)

        if total_chunks == 0:
            raise ValueError("Không tìm thấy văn bản phù hợp trong tài liệu.")

        await task_manager.update_task(
            task_id,
            total_chunks=total_chunks,
            progress=20,
            current_step=f"Đã trích xuất {total_chunks} đoạn. Bắt đầu sinh âm thanh..."
        )

        # Bước 2: Sinh giọng nói song song (giới hạn OFFLINE_CONCURRENCY đoạn cùng lúc)
        chunk_audio_files: List[Path] = [task_audio_dir / f"chunk_{i:04d}.mp3" for i in range(total_chunks)]
        semaphore = asyncio.Semaphore(OFFLINE_CONCURRENCY)
        done_count = 0

        async def process_chunk(i: int) -> None:
            nonlocal done_count
            async with semaphore:
                await synthesize_speech(text=chunks[i]["text"], output_path=chunk_audio_files[i], voice=voice, rate=rate)
            done_count += 1
            await task_manager.update_task(
                task_id,
                processed_chunks=done_count,
                progress=20 + int((done_count / total_chunks) * 65),
                current_step=f"Đã đọc {done_count}/{total_chunks} đoạn..."
            )

        async with asyncio.TaskGroup() as tg:
            for i in range(total_chunks):
                tg.create_task(process_chunk(i))

        # Bước 3: Ghép nối file theo tùy chọn của người dùng
        await task_manager.update_task(
            task_id,
            progress=90,
            current_step="Đang gom các file âm thanh..."
        )

        clean_base_title = _safe_filename(original_title)

        if merge_option == "single_file" or total_chunks <= 1:
            single_output = task_audio_dir / f"{clean_base_title}_Full.mp3"
            await asyncio.to_thread(merge_mp3_files, chunk_audio_files, single_output)
            final_mp3_files = [single_output]
        else:
            # Chia thành từng file 15-20 phút (khoảng 10 đoạn/file)
            final_mp3_files = await asyncio.to_thread(
                group_and_merge_chunks,
                chunk_audio_files,
                task_audio_dir,
                clean_base_title,
                10
            )

        # Đã ghép xong: xóa các file đoạn tạm để không tốn gấp đôi dung lượng
        for p in chunk_audio_files:
            p.unlink(missing_ok=True)

        # Bước 4: Tạo file ZIP nếu có nhiều file kết quả
        zip_info = None
        if len(final_mp3_files) > 1:
            await task_manager.update_task(
                task_id,
                progress=95,
                current_step="Đang đóng gói file ZIP các phần..."
            )
            zip_path = task_audio_dir / f"{clean_base_title}_Tron_Bo_Audiobook.zip"
            await asyncio.to_thread(create_zip_archive, final_mp3_files, zip_path)
            zip_info = _file_info(task_id, zip_path)

        result_files_info = [_file_info(task_id, f) for f in final_mp3_files]

        await task_manager.update_task(
            task_id,
            status="COMPLETED",
            progress=100,
            current_step="Hoàn thành xuất Audiobook!",
            output_files=result_files_info,
            zip_file=zip_info
        )
        logger.info(f"[Task {task_id}] Hoàn thành: {len(result_files_info)} file.")

    except Exception as e:
        err = _root_error(e)
        logger.error(f"[Task {task_id}] Xảy ra lỗi: {err}", exc_info=True)
        for p in task_audio_dir.glob("chunk_*.mp3"):
            p.unlink(missing_ok=True)
        await task_manager.update_task(
            task_id,
            status="FAILED",
            error=str(err),
            current_step=f"Lỗi: {err}"
        )


@app.post("/api/process/offline")
async def start_offline_conversion(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    voice: str = Form("vi-VN-HoaiMyNeural"),
    rate: str = Form("+0%"),
    merge_option: str = Form("single_file"),
    doc_id: Optional[str] = Form(None),
    section_ids: Optional[str] = Form(None)
):
    """
    API bắt đầu xuất Audio Offline.
    Nguồn: doc_id + section_ids (các phần đã chọn sau /api/document),
    hoặc upload PDF/DOCX / link Google Drive / OneDrive / trực tiếp (cả tài liệu).
    """
    _require_tts()
    await asyncio.to_thread(_cleanup_storage)
    original_title, text, doc_path = await _resolve_source(doc_id, section_ids, file, url)

    task_id = uuid.uuid4().hex[:12]

    await task_manager.create_task(task_id, title=original_title, max_age_seconds=MAX_AGE_SECONDS)

    background_tasks.add_task(
        _process_offline_task,
        task_id=task_id,
        file_path=doc_path,
        text=text,
        voice=voice,
        rate=rate,
        merge_option=merge_option,
        original_title=original_title
    )

    return {
        "status": "QUEUED",
        "task_id": task_id,
        "title": original_title,
        "message": "Tác vụ chuyển đổi đang chạy trong nền."
    }


@app.get("/api/process/offline/status/{task_id}")
async def get_offline_status(task_id: str):
    """Truy vấn tiến độ của tác vụ xuất Audio Offline."""
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ yêu cầu.")
    return task


# --------------------------------------------------------------------------
# CHẾ ĐỘ 2: ĐỌC LUÔN (WEB AUDIO PLAYER)
# --------------------------------------------------------------------------

class PrefetchRequest(BaseModel):
    chunk_indices: List[int]


# Mỗi đoạn chỉ có tối đa một tác vụ xử lý đang chạy; request đến sau chờ chung tác vụ đó
_chunk_jobs: Dict[Tuple[str, int], asyncio.Task] = {}


async def _process_single_chunk(session_id: str, chunk_idx: int) -> dict:
    """Sinh TTS cho một đoạn duy nhất của session."""
    session = await stream_manager.get_session(session_id)
    if not session or chunk_idx < 0 or chunk_idx >= session["total_chunks"]:
        raise ValueError("Session hoặc chunk không tồn tại.")

    chunk_info = session["chunks"][chunk_idx]
    if chunk_info["status"] == "ready" and chunk_info["audio_url"]:
        return chunk_info

    await stream_manager.update_chunk(session_id, chunk_idx, status="processing", error=None)

    audio_path = AUDIO_OUTPUT_DIR / f"stream_{session_id}" / f"chunk_{chunk_idx:04d}.mp3"

    try:
        await synthesize_speech(
            text=chunk_info["text"],
            output_path=audio_path,
            voice=session["voice"],
            rate=session["rate"]
        )

        await stream_manager.update_chunk(
            session_id,
            chunk_idx,
            audio_url=f"/audio/stream_{session_id}/{audio_path.name}",
            audio_path=str(audio_path),
            status="ready"
        )
        return await stream_manager.get_chunk_info(session_id, chunk_idx)

    except Exception as e:
        logger.error(f"[Session {session_id}] Lỗi xử lý chunk {chunk_idx}: {e}")
        await stream_manager.update_chunk(session_id, chunk_idx, status="error", error=str(e))
        raise


def _on_chunk_job_done(key: Tuple[str, int], job: asyncio.Task) -> None:
    _chunk_jobs.pop(key, None)
    if not job.cancelled():
        job.exception()  # Đánh dấu đã đọc lỗi; lỗi đã được log và lưu vào status của chunk


def _schedule_chunk(session_id: str, chunk_idx: int) -> asyncio.Task:
    """Trả về tác vụ đang chạy của đoạn, hoặc tạo mới nếu chưa có."""
    key = (session_id, chunk_idx)
    job = _chunk_jobs.get(key)
    if job is None:
        job = asyncio.create_task(_process_single_chunk(session_id, chunk_idx))
        _chunk_jobs[key] = job
        job.add_done_callback(lambda t: _on_chunk_job_done(key, t))
    return job


@app.post("/api/player/init")
async def init_player_session(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    voice: str = Form("vi-VN-HoaiMyNeural"),
    rate: str = Form("+0%"),
    doc_id: Optional[str] = Form(None),
    section_ids: Optional[str] = Form(None)
):
    """
    Khởi tạo phiên đọc trực tuyến cho Chế độ 2:
    - Nguồn: các phần đã chọn (doc_id + section_ids) hoặc file/link (cả tài liệu)
    - Lập tức tiền xử lý Đoạn 1 và Đoạn 2 trong nền
    - Trả về danh sách tóm tắt tất cả các đoạn để hiển thị lên Player
    """
    _require_tts()
    await asyncio.to_thread(_cleanup_storage)
    title, text, doc_path = await _resolve_source(doc_id, section_ids, file, url)

    try:
        if text is not None:
            extracted = await asyncio.to_thread(chunks_for_text, text)
        else:
            extracted = await asyncio.to_thread(extract_and_chunk_document, doc_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    chunks = extracted["chunks"]
    if not chunks:
        raise HTTPException(status_code=400, detail="Tài liệu không có nội dung văn bản.")

    session_id = uuid.uuid4().hex[:12]

    session = await stream_manager.create_session(
        session_id=session_id,
        title=title,
        chunks=chunks,
        voice=voice,
        rate=rate,
        max_age_seconds=MAX_AGE_SECONDS
    )

    for idx in range(min(2, len(chunks))):
        _schedule_chunk(session_id, idx)

    return {
        "session_id": session_id,
        "title": title,
        "total_chunks": session["total_chunks"],
        "total_words": extracted["total_words"],
        "voice": voice,
        "rate": rate,
        "chunks": [
            {
                "id": c["id"],
                "char_count": c["char_count"],
                "word_count": c["word_count"],
                "estimated_seconds": c["estimated_seconds"],
                "preview": c["preview"]
            }
            for c in session["chunks"]
        ]
    }


@app.get("/api/player/chunk/{session_id}/{chunk_idx}")
async def get_player_chunk(session_id: str, chunk_idx: int):
    """
    Lấy thông tin và file âm thanh của một đoạn cụ thể.
    Nếu đoạn đang được xử lý (prefetch) thì chờ kết quả đó; nếu chưa có thì xử lý ngay.
    """
    chunk_info = await stream_manager.get_chunk_info(session_id, chunk_idx)
    if not chunk_info:
        raise HTTPException(status_code=404, detail="Không tìm thấy đoạn yêu cầu (phiên có thể đã hết hạn).")

    if chunk_info["status"] != "ready":
        try:
            # shield: client ngắt kết nối không hủy tác vụ dùng chung
            chunk_info = await asyncio.shield(_schedule_chunk(session_id, chunk_idx))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Không thể xử lý đoạn {chunk_idx}: {e}")

    return chunk_info


@app.post("/api/player/prefetch/{session_id}")
async def prefetch_chunks(session_id: str, req: PrefetchRequest):
    """
    Prefetch ngầm: khi trình duyệt đang phát Đoạn N, chuẩn bị trước Đoạn N+1, N+2.
    Đoạn đang xử lý hoặc đã sẵn sàng sẽ không bị làm lại; đoạn lỗi được thử lại.
    """
    session = await stream_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session không tồn tại.")

    for idx in req.chunk_indices:
        if 0 <= idx < session["total_chunks"] and session["chunks"][idx]["status"] in ("idle", "error"):
            _schedule_chunk(session_id, idx)

    return {"status": "prefetching_dispatched", "requested_indices": req.chunk_indices}
