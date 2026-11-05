"""
Module các tiện ích phụ trợ:
- Ghép nối file MP3 (1 file lớn hoặc các file 15-20 phút)
- Nén file zip tải về
- Quản lý tiến trình (TaskManager) cho Chế độ 1 và Quản lý phiên phát (SessionManager) cho Chế độ 2
"""

import re
import time
import shutil
import zipfile
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def merge_mp3_files(input_files: List[Path], output_file: Path) -> Path:
    """
    Ghép nối nhiều file MP3 thành một file MP3 duy nhất.
    Do tất cả các đoạn âm thanh được sinh ra từ cùng một giọng đọc Azure Speech
    (đồng nhất về sample rate và codec), việc ghép nhị phân trực tiếp đảm bảo
    tốc độ cực nhanh mà không cần phụ thuộc vào phần mềm bên ngoài (như ffmpeg).
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "wb") as outfile:
        for idx, file_path in enumerate(input_files):
            if not file_path.exists() or file_path.stat().st_size == 0:
                continue
            with open(file_path, "rb") as infile:
                # Ghi toàn bộ dữ liệu âm thanh
                while chunk := infile.read(1024 * 64):  # 64KB buffer
                    outfile.write(chunk)

    return output_file


def group_and_merge_chunks(
    chunk_files: List[Path],
    output_dir: Path,
    base_title: str,
    chunks_per_group: int = 10
) -> List[Path]:
    """
    Gom các đoạn nhỏ thành các file MP3 vừa phải (mỗi file tương ứng 15-20 phút đọc).
    Mỗi đoạn văn bản ~1.500 ký tự đọc mất khoảng 1.5 - 2 phút, do đó ~10 đoạn sẽ tạo thành 1 file 15-20 phút.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    merged_files: List[Path] = []
    
    # Chia danh sách chunk_files thành từng nhóm
    total_chunks = len(chunk_files)
    if total_chunks <= chunks_per_group:
        # Nếu tổng số chunk ít hơn hoặc bằng 1 nhóm thì chỉ cần tạo 1 file
        single_out = output_dir / f"{base_title}_Full.mp3"
        merged_files.append(merge_mp3_files(chunk_files, single_out))
        return merged_files

    group_index = 1
    for i in range(0, total_chunks, chunks_per_group):
        group_chunk_files = chunk_files[i:i + chunks_per_group]
        start_chunk = i + 1
        end_chunk = min(i + chunks_per_group, total_chunks)
        
        part_name = f"{base_title}_Phan_{group_index:02d}_(Doan_{start_chunk}-{end_chunk}).mp3"
        part_path = output_dir / part_name
        merge_mp3_files(group_chunk_files, part_path)
        merged_files.append(part_path)
        group_index += 1

    return merged_files


def create_zip_archive(files_to_zip: List[Path], zip_output_path: Path) -> Path:
    """Nén danh sách các file MP3 thành một file ZIP hoàn chỉnh."""
    zip_output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with zipfile.ZipFile(zip_output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file_path in files_to_zip:
            if file_path.exists():
                # Bỏ tiền tố ngẫu nhiên "xxxxxxxx_" khỏi tên file trong ZIP
                zipf.write(file_path, arcname=re.sub(r"^[0-9a-f]{8}_", "", file_path.name))
                
    return zip_output_path


def cleanup_old_outputs(dirs: List[Path], max_age_seconds: float) -> None:
    """Xóa file/thư mục con cũ hơn max_age_seconds (server public: tránh đầy đĩa)."""
    cutoff = time.time() - max_age_seconds
    for d in dirs:
        if not d.exists():
            continue
        for entry in d.iterdir():
            try:
                if entry.stat().st_mtime >= cutoff:
                    continue
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
            except OSError as e:
                logger.warning(f"Không xóa được {entry}: {e}")


def _prune(store: Dict[str, Dict[str, Any]], max_age_seconds: float) -> None:
    cutoff = time.time() - max_age_seconds
    for key in [k for k, v in store.items() if v["created_at"] < cutoff]:
        del store[key]


class TaskManager:
    """
    Quản lý trạng thái và tiến độ xử lý cho Chế độ 1 (Offline Batch Processing).
    """
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create_task(self, task_id: str, title: str, max_age_seconds: float) -> Dict[str, Any]:
        async with self._lock:
            _prune(self.tasks, max_age_seconds)
            task = {
                "task_id": task_id,
                "title": title,
                "status": "PENDING",  # PENDING, PROCESSING, COMPLETED, FAILED
                "progress": 0,        # 0 -> 100
                "current_step": "Khởi tạo tác vụ...",
                "total_chunks": 0,
                "processed_chunks": 0,
                "created_at": time.time(),
                "output_files": [],   # Danh sách file mp3 kết quả
                "zip_file": None,     # Link file zip nếu có
                "error": None
            }
            self.tasks[task_id] = task
            return task

    async def update_task(self, task_id: str, **kwargs):
        async with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(kwargs)

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            return self.tasks.get(task_id)


class StreamSessionManager:
    """
    Quản lý phiên đọc trực tuyến và bộ đệm (Prefetching Queue) cho Chế độ 2.
    """
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        session_id: str,
        title: str,
        chunks: List[Dict[str, Any]],
        voice: str,
        rate: str,
        max_age_seconds: float
    ) -> Dict[str, Any]:
        async with self._lock:
            _prune(self.sessions, max_age_seconds)
            session_data = {
                "session_id": session_id,
                "title": title,
                "voice": voice,
                "rate": rate,
                "total_chunks": len(chunks),
                "chunks": [
                    {
                        "id": c["id"],
                        "text": c["text"],
                        "audio_url": None,
                        "audio_path": None,
                        "status": "idle",  # idle, processing, ready, error
                        "char_count": c["char_count"],
                        "word_count": c["word_count"],
                        "estimated_seconds": c["estimated_seconds"],
                        "preview": c["preview"]
                    }
                    for c in chunks
                ],
                "created_at": time.time()
            }
            self.sessions[session_id] = session_data
            return session_data

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            return self.sessions.get(session_id)

    async def get_chunk_info(self, session_id: str, chunk_idx: int) -> Optional[Dict[str, Any]]:
        async with self._lock:
            sess = self.sessions.get(session_id)
            if not sess or chunk_idx < 0 or chunk_idx >= len(sess["chunks"]):
                return None
            return sess["chunks"][chunk_idx]

    async def update_chunk(self, session_id: str, chunk_idx: int, **kwargs):
        async with self._lock:
            sess = self.sessions.get(session_id)
            if sess and 0 <= chunk_idx < len(sess["chunks"]):
                sess["chunks"][chunk_idx].update(kwargs)


# Khởi tạo các singleton instance
task_manager = TaskManager()
stream_manager = StreamSessionManager()
