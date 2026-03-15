"""
PDF Extractor Agent
-------------------
Reads uploaded PDFs with PyMuPDF and returns clean extracted text.
"""
import os
import fitz  # PyMuPDF


class PDFExtractorAgent:
    """Agent responsible for reading PDFs and extracting raw text."""

    def extract(self, file_path: str) -> dict:
        """
        Extract text from a single PDF file.

        Args:
            file_path: Absolute path to the PDF file.

        Returns:
            dict with keys: filename, text, page_count
        """
        filename = os.path.basename(file_path)
        try:
            doc = fitz.open(file_path)
            pages_text = []
            for page in doc:
                text = page.get_text("text")
                # Clean up whitespace
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                pages_text.append(" ".join(lines))
            doc.close()
            full_text = "\n\n".join(pages_text)
            return {
                "filename": filename,
                "text": full_text,
                "page_count": len(pages_text),
            }
        except Exception as e:
            return {
                "filename": filename,
                "text": f"[Error extracting {filename}: {e}]",
                "page_count": 0,
            }
