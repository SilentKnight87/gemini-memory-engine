#!/usr/bin/env python3
"""
capture.py — Capture any file into your personal memory layer.

Embeds text, images, audio, and PDFs into a unified vector space
using Google's Gemini Embedding 2, then stores in local ChromaDB.
"""

import argparse
import hashlib
import mimetypes
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import chromadb
import google.generativeai as genai

# ── Config ──────────────────────────────────────────────────────────
MODEL = "models/gemini-embedding-2-preview"
DIMENSIONS = 768  # 768/1536/3072 — 768 is best tradeoff
DB_PATH = os.environ.get("MEMORY_DB_PATH", str(Path.home() / ".memory" / "chromadb"))
COLLECTION = "memory"

# File types that need upload_file() (server-side processing)
UPLOAD_TYPES = {".mp3", ".wav", ".ogg", ".m4a", ".flac",  # audio
                ".mp4", ".mov", ".webm",                    # video
                ".pdf"}

# File types handled as PIL images (client-side)
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}

# File types read as text
TEXT_TYPES = {".txt", ".md", ".csv", ".json", ".py", ".js", ".ts",
              ".html", ".xml", ".yaml", ".yml", ".toml", ".ini",
              ".sh", ".zsh", ".bash", ".log", ".rst", ".tex"}


def get_collection():
    """Get or create the ChromaDB collection."""
    os.makedirs(DB_PATH, exist_ok=True)
    client = chromadb.PersistentClient(path=DB_PATH)
    return client.get_or_create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"}
    )


def file_id(filepath: str) -> str:
    """Generate a deterministic ID from filepath + modification time."""
    stat = os.stat(filepath)
    raw = f"{os.path.abspath(filepath)}:{stat.st_mtime}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def detect_type(filepath: str) -> str:
    """Classify file into: text, image, audio, video, pdf, unknown."""
    ext = Path(filepath).suffix.lower()
    if ext in TEXT_TYPES:
        return "text"
    if ext in IMAGE_TYPES:
        return "image"
    if ext in {".mp3", ".wav", ".ogg", ".m4a", ".flac"}:
        return "audio"
    if ext in {".mp4", ".mov", ".webm"}:
        return "video"
    if ext == ".pdf":
        return "pdf"
    # Fallback: check mimetype
    mime, _ = mimetypes.guess_type(filepath)
    if mime:
        if mime.startswith("text/"):
            return "text"
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("audio/"):
            return "audio"
        if mime.startswith("video/"):
            return "video"
        if mime == "application/pdf":
            return "pdf"
    return "unknown"


def embed_text(text: str) -> list[float]:
    """Embed a text string."""
    result = genai.embed_content(
        model=MODEL,
        content=text,
        task_type="RETRIEVAL_DOCUMENT",
        output_dimensionality=DIMENSIONS,
    )
    return result["embedding"]


def embed_image(filepath: str) -> list[float]:
    """Embed an image file using PIL."""
    from PIL import Image
    img = Image.open(filepath)
    result = genai.embed_content(
        model=MODEL,
        content=img,
        task_type="RETRIEVAL_DOCUMENT",
        output_dimensionality=DIMENSIONS,
    )
    return result["embedding"]


def embed_uploaded(filepath: str) -> list[float]:
    """Embed audio, video, or PDF via file upload."""
    uploaded = genai.upload_file(path=filepath)
    # Wait for server-side processing
    max_wait = 120
    waited = 0
    while uploaded.state.name == "PROCESSING" and waited < max_wait:
        time.sleep(3)
        waited += 3
        uploaded = genai.get_file(uploaded.name)
    if uploaded.state.name == "PROCESSING":
        raise TimeoutError(f"File processing timed out after {max_wait}s: {filepath}")
    if uploaded.state.name == "FAILED":
        raise RuntimeError(f"File processing failed: {filepath}")

    result = genai.embed_content(
        model=MODEL,
        content=uploaded,
        task_type="RETRIEVAL_DOCUMENT",
        output_dimensionality=DIMENSIONS,
    )
    return result["embedding"]


def read_text_file(filepath: str, max_chars: int = 30000) -> str:
    """Read a text file, truncating if necessary."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        return f.read(max_chars)


def capture(filepath: str, tags: list[str] | None = None, note: str | None = None):
    """Embed and store a file in the memory collection."""
    filepath = os.path.expanduser(filepath)
    if not os.path.isfile(filepath):
        print(f"Error: file not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    ftype = detect_type(filepath)
    fname = os.path.basename(filepath)
    fid = file_id(filepath)
    ext = Path(filepath).suffix.lower()

    print(f"Capturing: {fname} (type={ftype})")

    # Generate embedding based on file type
    if ftype == "text":
        text_content = read_text_file(filepath)
        if not text_content.strip():
            print("Error: file is empty", file=sys.stderr)
            sys.exit(1)
        embedding = embed_text(text_content)
        doc_text = text_content[:500]  # Store preview in ChromaDB document field
    elif ftype == "image":
        embedding = embed_image(filepath)
        doc_text = f"[image: {fname}]"
    elif ftype in ("audio", "video", "pdf"):
        embedding = embed_uploaded(filepath)
        doc_text = f"[{ftype}: {fname}]"
    else:
        # Try as text, fall back to upload
        try:
            text_content = read_text_file(filepath)
            embedding = embed_text(text_content)
            doc_text = text_content[:500]
            ftype = "text"
        except Exception:
            embedding = embed_uploaded(filepath)
            doc_text = f"[file: {fname}]"

    # Build metadata
    metadata = {
        "filename": fname,
        "filepath": os.path.abspath(filepath),
        "type": ftype,
        "extension": ext,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": os.path.getsize(filepath),
    }
    if tags:
        metadata["tags"] = ",".join(tags)
    if note:
        metadata["note"] = note

    # Store in ChromaDB
    collection = get_collection()
    collection.upsert(
        ids=[fid],
        embeddings=[embedding],
        documents=[doc_text],
        metadatas=[metadata],
    )

    tag_str = f" tags=[{', '.join(tags)}]" if tags else ""
    print(f"Stored: {fname} → id={fid}{tag_str}")
    print(f"  type={ftype}  dims={len(embedding)}  db={DB_PATH}")


def capture_text_snippet(text: str, tags: list[str] | None = None, note: str | None = None):
    """Capture raw text (not from a file) as a memory."""
    fid = hashlib.sha256(text.encode()).hexdigest()[:16]
    embedding = embed_text(text)

    metadata = {
        "filename": "(text snippet)",
        "filepath": "",
        "type": "text",
        "extension": "",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": len(text.encode()),
    }
    if tags:
        metadata["tags"] = ",".join(tags)
    if note:
        metadata["note"] = note

    collection = get_collection()
    collection.upsert(
        ids=[fid],
        embeddings=[embedding],
        documents=[text[:500]],
        metadatas=[metadata],
    )

    tag_str = f" tags=[{', '.join(tags)}]" if tags else ""
    print(f"Stored text snippet → id={fid}{tag_str}")
    print(f"  dims={len(embedding)}  db={DB_PATH}")


def main():
    parser = argparse.ArgumentParser(
        description="Capture a file or text into your personal memory layer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s photo.jpg --tags vacation hawaii
  %(prog)s meeting-notes.txt --tags work standup
  %(prog)s podcast.m4a --tags podcast tech --note "Episode about AI agents"
  %(prog)s report.pdf --tags finance q4
  %(prog)s --text "The restaurant on 5th Ave had amazing pasta" --tags food nyc
        """,
    )
    parser.add_argument("file", nargs="?", help="File to capture (text, image, audio, video, PDF)")
    parser.add_argument("--text", "-t", help="Capture a text snippet instead of a file")
    parser.add_argument("--tags", nargs="*", default=[], help="Optional tags for this memory")
    parser.add_argument("--note", "-n", help="Optional note / description")
    args = parser.parse_args()

    # Validate
    if not args.file and not args.text:
        parser.error("Provide a file path or --text 'your text'")
    if args.file and args.text:
        parser.error("Provide either a file or --text, not both")

    # Configure Gemini
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: set GEMINI_API_KEY or GOOGLE_API_KEY environment variable", file=sys.stderr)
        sys.exit(1)
    genai.configure(api_key=api_key)

    if args.text:
        capture_text_snippet(args.text, args.tags or None, args.note)
    else:
        capture(args.file, args.tags or None, args.note)


if __name__ == "__main__":
    main()
