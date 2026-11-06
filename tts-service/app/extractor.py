"""
Module trích xuất, làm sạch văn bản từ file PDF/DOCX và chia nhỏ thành các đoạn (chunks) hợp lý cho TTS.
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import Counter

import docx
import pypdfium2 as pdfium
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


def _digits_masked(line: str) -> str:
    return re.sub(r"\d+", "#", line.strip())


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
    # So khớp sau khi thay số bằng "#": header kiểu "ha.ngohuu Page 6", "Page 7" vẫn được coi là lặp
    first_lines = [_digits_masked(l) for l in first_lines]
    last_lines = [_digits_masked(l) for l in last_lines]
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
        non_empty = [i for i, l in enumerate(lines) if l.strip()]
        first_idx = non_empty[0] if non_empty else -1
        last_idx = non_empty[-1] if non_empty else -1

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                filtered_lines.append("")
                continue
            masked = _digits_masked(stripped)

            # Dòng chữ đầu tiên của trang (header)
            if idx == first_idx and (masked in common_headers or page_number_pattern.match(stripped)):
                continue

            # Dòng chữ cuối cùng của trang (footer)
            if idx == last_idx and (masked in common_footers or page_number_pattern.match(stripped)):
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


# Ở một cấp mục lục, nếu có phần chiếm hơn tỉ lệ này của cả tài liệu (và đủ dài) thì xuống cấp sâu hơn.
# Ví dụ: "Phần 2" chiếm 44% sách -> chia theo "Chương"; chương dài 35/447 trang vẫn giữ nguyên.
MAX_SECTION_SHARE = 0.25
MIN_SPLIT_CHARS = 20000
# Phần quá ngắn (trang bìa "PHẦN MỘT", trang trống) được gộp vào phần ngay sau
MIN_SECTION_CHARS = 300
# Khi tài liệu không có mục lục/heading: chia theo dung lượng, ~20 phút đọc mỗi phần
FALLBACK_SECTION_CHARS = 18000

IMAGE_PDF_MESSAGE = (
    "PDF này có {n} trang nhưng không có lớp chữ: đây là PDF dạng ảnh (scan, chụp hoặc "
    "'Print to PDF' từ ảnh). App chưa đọc được loại file này; hãy dùng bản PDF/Word có chữ chọn được."
)


def _pdf_pages_and_bookmarks(pdf_path: Path):
    """
    PDF: lấy chữ từng trang bằng pdfium (nhanh, ít RAM: sách 259 trang < 1s) và mục lục (bookmark).
    Trả về (danh sách chữ từng trang đã làm sạch, [(cấp, chỉ số trang, tiêu đề)]).
    """
    raw_pages: List[str] = []
    bookmarks = []
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        for i in range(len(doc)):
            page = doc[i]
            textpage = page.get_textpage()
            raw_pages.append(clean_page_text(textpage.get_text_range()))
            textpage.close()
            page.close()
        for bm in doc.get_toc(max_depth=4):
            dest = bm.get_dest()
            index = dest.get_index() if dest else None
            title = re.sub(r"\s+", " ", bm.get_title() or "").strip()
            # Bỏ bookmark chú thích kiểu "[12]" hoặc chỉ là số
            if re.fullmatch(r"\[?\d+\]?\.?", title):
                continue
            if index is not None and 0 <= index < len(raw_pages) and title:
                bookmarks.append((bm.level, index, title))
    finally:
        doc.close()

    pages = remove_repetitive_headers_and_footers(raw_pages)
    # Chỉ có watermark/số trang lặp lại (đã bị loại) cũng tính là không có lớp chữ
    if raw_pages and not any(p.strip() for p in pages):
        raise ValueError(IMAGE_PDF_MESSAGE.format(n=len(raw_pages)))
    return pages, bookmarks


def _docx_blocks(docx_path: Path):
    """
    DOCX: lấy đoạn văn và bảng theo đúng thứ tự trong tài liệu.
    Trả về [(văn bản, cấp heading hoặc None)]; Title = cấp 0, Heading N = cấp N.
    """
    document = docx.Document(str(docx_path))
    blocks = []
    for element in document.element.body.iterchildren():
        if element.tag == qn("w:p"):
            para = Paragraph(element, document)
            text = para.text.strip()
            if not text:
                continue
            style = (para.style.name if para.style is not None else "") or ""
            level = None
            if style == "Title":
                level = 0
            else:
                m = re.match(r"Heading (\d)", style)
                if m:
                    level = int(m.group(1))
            blocks.append((text, level))
        elif element.tag == qn("w:tbl"):
            for row in Table(element, document).rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    # Ô gộp lặp lại cùng nội dung: bỏ trùng liền kề
                    unique = [c for i, c in enumerate(cells) if i == 0 or c != cells[i - 1]]
                    blocks.append((", ".join(unique) + ".", None))
    return blocks


def _split_by_markers(units: List[str], markers: List[tuple]) -> List[Dict[str, Any]]:
    """
    units: các đơn vị văn bản (trang PDF hoặc khối DOCX). markers: [(chỉ số unit bắt đầu, tiêu đề)].
    Trả về [{"title", "start", "end"}] phủ toàn bộ units, có phần "Mở đầu" nếu trước marker đầu có chữ.
    """
    markers = sorted({start: title for start, title in reversed(markers)}.items())  # 1 tiêu đề/vị trí, giữ cái xuất hiện trước
    spans = []
    if not markers or markers[0][0] > 0:
        first = markers[0][0] if markers else len(units)
        spans.append({"title": "Mở đầu", "start": 0, "end": first})
    for i, (start, title) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else len(units)
        spans.append({"title": title, "start": start, "end": end})
    return [s for s in spans if s["end"] > s["start"]]


def _choose_level(items: List[tuple], units: List[str]) -> List[tuple]:
    """
    items: [(cấp, chỉ số unit, tiêu đề)]. Chọn cấp nông nhất mà không phần nào chiếm quá
    MAX_SECTION_SHARE tài liệu; nếu cấp nào cũng còn phần quá lớn thì dùng cấp sâu nhất có.
    """
    total = sum(len(u) for u in units) or 1
    levels = sorted({lvl for lvl, _, _ in items})
    chosen = []
    for lvl in levels:
        chosen = [(idx, title) for l, idx, title in items if l <= lvl]
        sizes = [sum(len(u) for u in units[s["start"]:s["end"]]) for s in _split_by_markers(units, chosen)]
        # Cấp chỉ có 1 phần (vd. một Title duy nhất) thì luôn thử cấp sâu hơn
        if len(sizes) > 1 and not any(size > MIN_SPLIT_CHARS and size / total > MAX_SECTION_SHARE for size in sizes):
            break
    return chosen


def _fallback_markers(units: List[str], unit_label: Optional[str]) -> List[tuple]:
    """Không có cấu trúc: cắt theo dung lượng ~FALLBACK_SECTION_CHARS, tại ranh giới unit."""
    markers, size, start = [], 0, 0
    for i, u in enumerate(units):
        if size >= FALLBACK_SECTION_CHARS:
            markers.append((start, None))
            start, size = i, 0
        size += len(u)
    # Phần cuối quá ngắn thì gộp vào phần trước
    if markers and size < FALLBACK_SECTION_CHARS / 3:
        pass
    else:
        markers.append((start, None))
    if not markers:
        markers.append((0, None))
    total = len(markers)
    result = []
    for k, (s, _) in enumerate(markers):
        e = markers[k + 1][0] if k + 1 < total else len(units)
        label = f"Phần {k + 1}/{total}"
        if unit_label:
            label += f" ({unit_label} {s + 1}–{e})"
        result.append((s, label))
    return result


def _finalize_sections(units: List[str], spans: List[Dict[str, Any]], unit_label: Optional[str]) -> List[Dict[str, Any]]:
    """Ghép chữ từng phần, gộp phần quá ngắn vào phần sau, đánh số id."""
    sections = []
    pending = None  # phần quá ngắn chờ gộp vào phần kế tiếp
    for s in spans:
        text = normalize_full_text("\n\n".join(u for u in units[s["start"]:s["end"]] if u.strip()))
        item = {"title": s["title"], "start": s["start"], "end": s["end"], "text": text}
        if pending:
            item["title"] = f"{pending['title']} · {item['title']}"
            item["start"] = pending["start"]
            item["text"] = f"{pending['text']}\n\n{item['text']}".strip()
            pending = None
        if len(item["text"]) < MIN_SECTION_CHARS:
            pending = item
            continue
        sections.append(item)
    if pending:
        if sections:
            sections[-1]["end"] = pending["end"]
            sections[-1]["text"] = f"{sections[-1]['text']}\n\n{pending['text']}".strip()
        elif pending["text"]:
            sections.append(pending)

    result = []
    for i, s in enumerate(sections):
        if not s["text"]:
            continue
        chunks = create_chunks_from_text(s["text"])
        result.append({
            "id": len(result),
            "title": s["title"],
            "pages": f"{s['start'] + 1}–{s['end']}" if unit_label == "trang" else None,
            "char_count": len(s["text"]),
            "estimated_seconds": sum(c["estimated_seconds"] for c in chunks),
            "text": s["text"],
        })
    return result


SUPPORTED_SUFFIXES = {".pdf", ".docx"}


def extract_document_sections(doc_path: Path) -> Dict[str, Any]:
    """
    Trích xuất PDF/DOCX và chia thành các phần để người dùng chọn nghe:
    - PDF: theo mục lục (bookmark), chọn cấp chương/mục sao cho mỗi phần không quá dài.
    - DOCX: theo các đoạn có style Title/Heading.
    - Không có cấu trúc: theo dung lượng ~20 phút đọc mỗi phần.
    """
    if not doc_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {doc_path}")

    suffix = doc_path.suffix.lower()
    if suffix == ".pdf":
        units, bookmarks = _pdf_pages_and_bookmarks(doc_path)
        items, unit_label, structure = bookmarks, "trang", "bookmark"
    elif suffix == ".docx":
        blocks = _docx_blocks(doc_path)
        units = [clean_page_text(text) for text, _ in blocks]
        items = [(lvl, i, text[:120]) for i, (text, lvl) in enumerate(blocks) if lvl is not None]
        unit_label, structure = None, "heading"
    else:
        raise ValueError(f"Không hỗ trợ định dạng {suffix}. Chỉ nhận PDF hoặc Word (.docx).")

    sections = []
    if items:
        sections = _finalize_sections(units, _split_by_markers(units, _choose_level(items, units)), unit_label)
    # Không có cấu trúc, hoặc cấu trúc chỉ cho 1 phần dài: chia theo dung lượng
    if len(sections) <= 1 and sum(len(u) for u in units) > FALLBACK_SECTION_CHARS:
        structure = "size"
        sections = _finalize_sections(units, _split_by_markers(units, _fallback_markers(units, unit_label)), unit_label)
    elif not items:
        structure = "size"
        sections = _finalize_sections(units, _split_by_markers(units, _fallback_markers(units, unit_label)), unit_label)

    if not sections:
        raise ValueError(
            "Không trích xuất được chữ từ tài liệu này (có thể là file scan dạng ảnh, file bị mã hóa hoặc file rỗng)."
        )
    return {
        "total_pages": len(units) if unit_label == "trang" else None,
        "total_characters": sum(s["char_count"] for s in sections),
        "structure": structure,
        "sections": sections,
    }


def chunks_for_text(text: str) -> Dict[str, Any]:
    chunks = create_chunks_from_text(text)
    return {
        "total_characters": len(text),
        "total_words": len(text.split()),
        "total_chunks": len(chunks),
        "chunks": chunks
    }


def extract_and_chunk_document(doc_path: Path) -> Dict[str, Any]:
    """Toàn bộ tài liệu (mọi phần) thành chunks; dùng khi không chọn phần."""
    doc = extract_document_sections(doc_path)
    return chunks_for_text("\n\n".join(s["text"] for s in doc["sections"]))
