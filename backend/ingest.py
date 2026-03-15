"""
ingest.py — Parse uploaded documents and web URLs into overlapping text chunks.

Supported formats: PDF, DOCX, TXT/MD, image, URL
Each returned chunk: { "text": str, "source": str, "page": int }
"""
import base64
import io
import re
from typing import BinaryIO

import fitz  # PyMuPDF
import ollama
from docx import Document

VISION_MODEL = "llava-phi3:3.8b"  # <= 5B parameters

CHUNK_SIZE = 400       # characters per chunk (≈ 120-150 tokens)
CHUNK_OVERLAP = 60     # overlap to preserve context across chunk boundaries


def _split_text(text: str, source: str, page: int = 0) -> list[dict]:
    """Split a block of text into overlapping chunks."""
    chunks = []
    start = 0
    text = text.strip()
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({"text": chunk_text, "source": source, "page": page})
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def parse_pdf(file_bytes: bytes, source_name: str) -> list[dict]:
    chunks = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text()
            chunks.extend(_split_text(text, source_name, page=page_num))
    return chunks


def parse_docx(file_bytes: bytes, source_name: str) -> list[dict]:
    doc = Document(io.BytesIO(file_bytes))
    full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return _split_text(full_text, source_name, page=0)


def parse_txt(file_bytes: bytes, source_name: str) -> list[dict]:
    text = file_bytes.decode("utf-8", errors="replace")
    return _split_text(text, source_name, page=0)


def parse_image(file_bytes: bytes, source_name: str) -> list[dict]:
    """Describe an image using llava and index the description as text chunks."""
    b64_image = base64.b64encode(file_bytes).decode("utf-8")
    prompt = (
        "Describe this image for study notes and knowledge graph creation. "
        "Focus on concrete entities, labels, numbers, relationships, and notable details. "
        "Return one concise paragraph then 3-6 bullet points."
    )
    resp = ollama.chat(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt,
                "images": [b64_image],
            }
        ],
        stream=False,
        options={"temperature": 0.2, "num_predict": 600},
    )
    description = (resp.get("message", {}) or {}).get("content", "").strip()
    if not description:
        description = f"Image source: {source_name}. No visual description produced."
    return _split_text(description, source_name, page=1)


def ingest_file(file_bytes: bytes, filename: str) -> list[dict]:
    """Auto-detect file type and return list of chunks."""
    name_lower = filename.lower()
    if name_lower.endswith(".pdf"):
        return parse_pdf(file_bytes, filename)
    elif name_lower.endswith(".docx"):
        return parse_docx(file_bytes, filename)
    elif name_lower.endswith(".txt") or name_lower.endswith(".md"):
        return parse_txt(file_bytes, filename)
    elif name_lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")):
        return parse_image(file_bytes, filename)
    else:
        # Fallback: try UTF-8 text
        return parse_txt(file_bytes, filename)


def parse_url(url: str) -> list[dict]:
    """Fetch a webpage and return text chunks. Strips nav/footer/scripts."""
    try:
        import httpx
        r = httpx.get(
            url, timeout=15, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; EduGraph/1.0)"},
        )
        r.raise_for_status()
    except Exception as e:
        raise ValueError(f"Could not fetch URL: {e}")

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "html.parser")

    # Remove boilerplate elements
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "noscript", "iframe"]):
        tag.decompose()

    # Prefer main content containers
    content = (
        soup.find("article")
        or soup.find("main")
        or soup.find(id=re.compile(r"content|main|article", re.I))
        or soup.find(class_=re.compile(r"content|article|post|entry", re.I))
        or soup.find("body")
        or soup
    )

    text = content.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)  # collapse blank lines

    title = soup.find("title")
    source_name = (title.get_text(strip=True) if title else url)[:120]

    return _split_text(text, source_name, page=0)
