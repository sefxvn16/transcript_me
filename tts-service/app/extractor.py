"""
Module trích xuất, làm sạch văn bản từ file PDF/DOCX và chia nhỏ thành các đoạn (chunks) hợp lý cho TTS.
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import Counter

import docx
import pdfplumber
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

logger = logging.getLogger(__name__)

# Danh sách từ viết tắt phổ biến để tránh tách câu sai
COMMON_ABBREVIATIONS = {
    "tp.", "ths.", "ts.", "pgs.", "gs.", "bs.", "ks.", "mr.", "mrs.", "ms.",
    "dr.", "prof.", "e.g.", "i.e.", "etc.", "vs.", "v.v.", "approx.", "fig.",
    "no.", "vol.", "pp.", "st.", "co.", "ltd.", "inc.", "corp."
}


def clean_page_text(raw_text: str) -> str:
    """Làm sạch sơ bộ văn bản trong một trang PDF."""
    if not raw_text:
        return ""
    
    # 1. Chuẩn hóa ký tự xuống dòng Windows / Unix
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    
    # 2. Xóa các ký tự null hoặc ký tự điều khiển không in được
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    
    # 3. Nối lại từ bị gãy dòng bằng dấu gạch nối (Hyphenation)
    # Tiếng Việt tách âm tiết bằng khoảng trắng: "nghiên-\n cứu" -> "nghiên cứu"
    # Ngôn ngữ khác nối liền: "tech-\n nology" -> "technology"
    # Gạch ngang dài (– —) là dấu câu thật nên không xử lý ở đây.
    text = _HYPHEN_BREAK_RE.sub(_join_hyphen_break, text)

    return text


_HYPHEN_BREAK_RE = re.compile(r'(\w+)[-‐‑]\s*\n\s*(\w+)')
_VIETNAMESE_CHAR_RE = re.compile(r'[À-ỹ]')


def _join_hyphen_break(m: re.Match) -> str:
    left, right = m.group(1), m.group(2)
    if _VIETNAMESE_CHAR_RE.search(left) or _VIETNAMESE_CHAR_RE.search(right):
        return f"{left} {right}"
    return left + right


def remove_repetitive_headers_and_footers(pages_text: List[str]) -> List[str]:
    """
    Phát hiện và loại bỏ header, footer và số trang lặp lại trên nhiều trang.
    """
    if len(pages_text) <= 1:
        return pages_text

    first_lines = []
    last_lines = []

    for text in pages_text:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if lines:
            first_lines.append(lines[0])
            last_lines.append(lines[-1])

    threshold = max(2, int(len(pages_text) * 0.35))
    common_headers = {line for line, count in Counter(first_lines).items() if count >= threshold}
    common_footers = {line for line, count in Counter(last_lines).items() if count >= threshold}

    page_number_pattern = re.compile(
        r"^(?:page|trang|\-|\–)?\s*\d+\s*(?:[/|\-–]\s*\d+)?\s*$",
        re.IGNORECASE
    )

    cleaned_pages = []
    for text in pages_text:
        lines = text.split("\n")
        filtered_lines = []
        total_lines = len(lines)

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                filtered_lines.append("")
                continue

            # Kiểm tra dòng đầu (header)
            if idx == 0 and (stripped in common_headers or page_number_pattern.match(stripped)):
                continue

            # Kiểm tra dòng cuối (footer)
            if idx == total_lines - 1 and (stripped in common_footers or page_number_pattern.match(stripped)):
                continue

            # Kiểm tra dòng chỉ có số trang đơn thuần ở bất kỳ vị trí biên
            if (idx <= 2 or idx >= total_lines - 3) and page_number_pattern.match(stripped):
                continue

            filtered_lines.append(line)

        cleaned_pages.append("\n".join(filtered_lines))

    return cleaned_pages


def normalize_full_text(text: str) -> str:
    """
    Chuẩn hóa toàn bộ văn bản sau khi ghép trang:
    - Nối các dòng bị ngắt ngẫu nhiên giữa câu
    - Chuẩn hóa khoảng trắng
    - Giữ các đoạn văn mạch lạc
    """
    # Tách theo từng dòng
    lines = text.split("\n")
    processed_paragraphs = []
    current_para = []

    punctuation_ends = {'.', '?', '!', ':', ';', '…', '"', '”', '’', ')', '»'}

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_para:
                processed_paragraphs.append(" ".join(current_para))
                current_para = []
            continue

        if not current_para:
            current_para.append(stripped)
        else:
            prev_line = current_para[-1]
            last_char = prev_line[-1] if prev_line else ''
            
            # Nếu dòng trước kết thúc bằng dấu chấm kết câu hoặc dấu hai chấm
            if last_char in punctuation_ends:
                processed_paragraphs.append(" ".join(current_para))
                current_para = [stripped]
            else:
                # Nối tiếp vào dòng trước vì ngắt dòng giữa chừng trong câu
                current_para.append(stripped)

    if current_para:
        processed_paragraphs.append(" ".join(current_para))

    # Ghép lại thành chuỗi văn bản hoàn chỉnh
    normalized = "\n\n".join(processed_paragraphs)
    # Loại bỏ khoảng trắng thừa liên tiếp
    normalized = re.sub(r"[ \t]+", " ", normalized)
    return normalized.strip()


def split_sentences(text: str) -> List[str]:
    """
    Tách văn bản thành danh sách các câu hoàn chỉnh.
    Tôn trọng chữ viết tắt, số thập phân và dấu ngoặc kép.
    """
    # Regex tách câu tại dấu chấm, hỏi, than, chấm lửng
    # nhưng đảm bảo phía sau là khoảng trắng và ký tự viết hoa hoặc mở ngoặc/số
    raw_sentences = re.split(
        # Python chỉ cho lookbehind cố định độ dài: tách 2 trường hợp có/không dấu nháy đóng
        r'(?:(?<=[.?!…])|(?<=[.?!…]["”\']))\s+(?=[A-ZÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰÝỲỶỸỴ0-9"“\'\(\[])',
        text
    )

    sentences = []
    for s in raw_sentences:
        s = s.strip()
        if not s:
            continue
        
        # Câu trước kết thúc bằng từ viết tắt (ví dụ: "ThS." hoặc "TP.") nghĩa là bị tách sai: ghép lại
        if sentences and sentences[-1].lower().rsplit(None, 1)[-1] in COMMON_ABBREVIATIONS:
            sentences[-1] = sentences[-1] + " " + s
        else:
            sentences.append(s)

    return sentences


def force_split_long_sentence(sentence: str, max_chars: int = 1800) -> List[str]:
    """
    Bẻ nhỏ một câu cực dài (nếu câu vượt quá max_chars) tại dấu phẩy, chấm phẩy hoặc khoảng trắng.
    """
    if len(sentence) <= max_chars:
        return [sentence]

    sub_chunks = []
    # Tách thử theo dấu phẩy, chấm phẩy hoặc liên từ
    parts = re.split(r'(?<=[,;:\-–—])\s+', sentence)
    curr = ""
    for part in parts:
        if len(curr) + len(part) + 1 <= max_chars:
            curr = f"{curr} {part}".strip()
        else:
            if curr:
                sub_chunks.append(curr)
            if len(part) > max_chars:
                # Nếu một mẩu vẫn dài hơn max_chars, cắt theo khoảng trắng
                words = part.split()
                w_curr = ""
                for w in words:
                    if len(w_curr) + len(w) + 1 <= max_chars:
                        w_curr = f"{w_curr} {w}".strip()
                    else:
                        if w_curr:
                            sub_chunks.append(w_curr)
                        w_curr = w
                if w_curr:
                    curr = w_curr
            else:
                curr = part
    if curr:
        sub_chunks.append(curr)
    return sub_chunks


def create_chunks_from_text(
    full_text: str,
    min_chars: int = 1000,
    max_chars: int = 1800
) -> List[Dict[str, Any]]:
    """
    Chia văn bản thành danh sách các đoạn (chunks) từ 1.000 đến 1.800 ký tự.
    Đảm bảo ngắt câu đúng vị trí (không cắt ngang câu văn).
    """
    sentences = split_sentences(full_text)
    chunks: List[Dict[str, Any]] = []

    current_chunk_sentences: List[str] = []
    current_length = 0

    def finalize_chunk(seq_id: int, s_list: List[str]) -> Dict[str, Any]:
        chunk_content = " ".join(s_list).strip()
        word_count = len(chunk_content.split())
        # Ước lượng thời gian đọc: ~140 từ / phút -> 2.33 từ / giây
        estimated_seconds = max(1, round(word_count / 2.33))
        return {
            "id": seq_id,
            "text": chunk_content,
            "char_count": len(chunk_content),
            "word_count": word_count,
            "estimated_seconds": estimated_seconds,
            "preview": chunk_content[:120] + "..." if len(chunk_content) > 120 else chunk_content
        }

    for sentence in sentences:
        # force_split_long_sentence trả nguyên câu nếu câu không vượt max_chars
        for s in force_split_long_sentence(sentence, max_chars):
            s_len = len(s)

            # Thêm câu này sẽ vượt max_chars: đóng đoạn hiện tại (ưu tiên không vượt max_chars
            # hơn là đạt min_chars), câu này mở đoạn mới
            if current_chunk_sentences and current_length + s_len + 1 > max_chars:
                chunks.append(finalize_chunk(len(chunks), current_chunk_sentences))
                current_chunk_sentences = [s]
                current_length = s_len
            else:
                current_chunk_sentences.append(s)
                current_length += s_len + (1 if current_length else 0)

    # Đóng đoạn cuối cùng nếu còn
    if current_chunk_sentences:
        chunks.append(finalize_chunk(len(chunks), current_chunk_sentences))

    return chunks


def _extract_pdf_text(pdf_path: Path) -> str:
    """PDF: duyệt từng trang, làm sạch header/footer, số trang, gạch nối ngắt dòng."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        raw_pages = [clean_page_text(page.extract_text(layout=False) or "") for page in pdf.pages]
    pages_without_headers = remove_repetitive_headers_and_footers(raw_pages)
    return "\n\n".join(p for p in pages_without_headers if p.strip())


def _extract_docx_text(docx_path: Path) -> str:
    """DOCX: lấy đoạn văn và bảng theo đúng thứ tự trong tài liệu, mỗi khối cách nhau một dòng trống."""
    document = docx.Document(str(docx_path))
    blocks: List[str] = []
    for element in document.element.body.iterchildren():
        if element.tag == qn("w:p"):
            text = Paragraph(element, document).text.strip()
            if text:
                blocks.append(text)
        elif element.tag == qn("w:tbl"):
            for row in Table(element, document).rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    # Ô gộp lặp lại cùng nội dung: bỏ trùng liền kề
                    unique = [c for i, c in enumerate(cells) if i == 0 or c != cells[i - 1]]
                    blocks.append(", ".join(unique) + ".")
    return clean_page_text("\n\n".join(blocks))


SUPPORTED_SUFFIXES = {".pdf", ".docx"}


def extract_and_chunk_document(
    doc_path: Path,
    min_chars: int = 1000,
    max_chars: int = 1800
) -> Dict[str, Any]:
    """
    Trích xuất văn bản từ PDF hoặc DOCX (theo đuôi file), chuẩn hóa câu
    và chia thành chunks không quá max_chars ký tự.
    """
    if not doc_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {doc_path}")

    suffix = doc_path.suffix.lower()
    if suffix == ".pdf":
        raw_text = _extract_pdf_text(doc_path)
    elif suffix == ".docx":
        raw_text = _extract_docx_text(doc_path)
    else:
        raise ValueError(f"Không hỗ trợ định dạng {suffix}. Chỉ nhận PDF hoặc Word (.docx).")

    normalized_text = normalize_full_text(raw_text)
    if not normalized_text:
        raise ValueError(
            "Không trích xuất được chữ từ tài liệu này (có thể là file scan dạng ảnh, file bị mã hóa hoặc file rỗng)."
        )

    chunks = create_chunks_from_text(normalized_text, min_chars=min_chars, max_chars=max_chars)

    return {
        "total_characters": len(normalized_text),
        "total_words": len(normalized_text.split()),
        "total_chunks": len(chunks),
        "chunks": chunks
    }
