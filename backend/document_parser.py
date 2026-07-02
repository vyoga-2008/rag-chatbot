"""
Extracts raw text from supported document types: pdf, docx, csv, txt, md.
Each format has one dedicated helper; parse_document() dispatches by extension.
"""
import os
import pandas as pd
from pypdf import PdfReader
import mammoth


def _parse_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)
    return "\n".join(text_parts)


def _parse_docx(file_path: str) -> str:
    with open(file_path, "rb") as f:
        result = mammoth.extract_raw_text(f)
    return result.value


def _parse_csv(file_path: str) -> str:
    df = pd.read_csv(file_path)
    # Convert rows into readable "column: value" text so the LLM can
    # reason over tabular data as natural language.
    lines = []
    for idx, row in df.iterrows():
        row_text = ", ".join(f"{col}: {row[col]}" for col in df.columns)
        lines.append(f"Row {idx}: {row_text}")
    return "\n".join(lines)


def _parse_plain_text(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def parse_document(file_path: str) -> str:
    """
    Dispatch to the correct parser based on file extension.
    Returns the extracted plain text, or raises ValueError if unsupported.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return _parse_pdf(file_path)
    elif ext == ".docx":
        return _parse_docx(file_path)
    elif ext == ".csv":
        return _parse_csv(file_path)
    elif ext in (".txt", ".md"):
        return _parse_plain_text(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")
