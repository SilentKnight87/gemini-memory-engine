#!/usr/bin/env python3
"""
ingest_openclaw.py — Ingest OpenClaw session logs into the Gemini Memory Engine.

Scans ~/clawd/memory/ for daily session logs (YYYY-MM-DD.md files) and
~/clawd/MEMORY.md for the main memory file. Tags everything with 'openclaw'
and 'session-log' for filtered recall.

Uses the same deterministic ID logic (filepath + mtime hash) as capture.py
to skip already-ingested files.

Usage:
    python ingest_openclaw.py              # ingest all session logs
    python ingest_openclaw.py --dry-run    # count files without ingesting
"""

import argparse
import hashlib
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import chromadb
import google.generativeai as genai

# ── Config ──────────────────────────────────────────────────────────
MODEL = "models/gemini-embedding-2-preview"
DIMENSIONS = 768
DB_PATH = os.environ.get("MEMORY_DB_PATH", str(Path.home() / ".memory" / "chromadb"))
COLLECTION = "memory"

MEMORY_DIR = str(Path.home() / "clawd" / "memory")
MEMORY_FILE = str(Path.home() / "clawd" / "MEMORY.md")

BATCH_DELAY_SEC = 0.1


def get_collection():
    """Get or create the ChromaDB collection."""
    os.makedirs(DB_PATH, exist_ok=True)
    client = chromadb.PersistentClient(path=DB_PATH)
    return client.get_or_create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def file_id(filepath: str) -> str:
    """Deterministic ID from filepath + modification time (matches capture.py)."""
    stat = os.stat(filepath)
    raw = f"{os.path.abspath(filepath)}:{stat.st_mtime}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def embed_text(text: str) -> list[float]:
    """Embed a text string via Gemini Embedding 2."""
    result = genai.embed_content(
        model=MODEL,
        content=text,
        task_type="RETRIEVAL_DOCUMENT",
        output_dimensionality=DIMENSIONS,
    )
    return result["embedding"]


def discover_files() -> list[str]:
    """Find all OpenClaw memory files to ingest."""
    files = []

    # Main memory file
    if os.path.isfile(MEMORY_FILE):
        files.append(MEMORY_FILE)

    # Daily session logs
    if os.path.isdir(MEMORY_DIR):
        for fname in sorted(os.listdir(MEMORY_DIR)):
            if fname.endswith(".md"):
                files.append(os.path.join(MEMORY_DIR, fname))

    return files


def extract_date_from_filename(filepath: str) -> str:
    """Try to extract a date from filenames like 2026-01-21.md."""
    stem = Path(filepath).stem
    # Handle formats: 2026-01-21, 2026-01-27-0712, 2026-01-27-evening
    parts = stem.split("-")
    if len(parts) >= 3:
        try:
            int(parts[0])  # year
            int(parts[1])  # month
            int(parts[2])  # day
            return f"{parts[0]}-{parts[1]}-{parts[2]}"
        except ValueError:
            pass
    return ""


def ingest_file(filepath: str, collection) -> dict:
    """Embed and store a single OpenClaw file."""
    fid = file_id(filepath)
    fname = os.path.basename(filepath)

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    if not content.strip():
        return {"id": fid, "status": "skipped", "reason": "empty"}

    # Truncate for embedding
    embed_content = content[:30000]
    embedding = embed_text(embed_content)

    # Build tags
    tags = ["openclaw", "session-log"]
    session_date = extract_date_from_filename(filepath)

    # Determine title
    if filepath == MEMORY_FILE:
        title = "OpenClaw Main Memory"
        tags.append("main-memory")
    else:
        title = f"Session Log — {session_date}" if session_date else f"Session Log — {fname}"

    metadata = {
        "filename": fname,
        "filepath": os.path.abspath(filepath),
        "title": title,
        "type": "text",
        "extension": ".md",
        "tags": ",".join(tags),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": os.path.getsize(filepath),
        "source": "openclaw",
    }
    if session_date:
        metadata["session_date"] = session_date

    collection.upsert(
        ids=[fid],
        embeddings=[embedding],
        documents=[content[:500]],
        metadatas=[metadata],
    )

    return {"id": fid, "status": "ingested", "title": title}


def main():
    parser = argparse.ArgumentParser(
        description="Ingest OpenClaw session logs into the Gemini Memory Engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s              # ingest all session logs + MEMORY.md
  %(prog)s --dry-run    # count files without ingesting
        """,
    )
    parser.add_argument("--dry-run", action="store_true", help="Count files without ingesting")
    args = parser.parse_args()

    # Discover files
    files = discover_files()
    print(f"Found {len(files)} OpenClaw memory file(s)\n")

    if not files:
        print("No OpenClaw memory files found.")
        print(f"  Checked: {MEMORY_FILE}")
        print(f"  Checked: {MEMORY_DIR}/")
        return

    if args.dry_run:
        for f in files:
            print(f"  {os.path.basename(f)}")
        print(f"\n  Total: {len(files)} files")
        print("  (use without --dry-run to ingest)")
        return

    # Configure Gemini
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: set GEMINI_API_KEY or GOOGLE_API_KEY environment variable", file=sys.stderr)
        sys.exit(1)
    genai.configure(api_key=api_key)

    # Check existing
    collection = get_collection()
    existing_ids = set()
    try:
        all_items = collection.get()
        existing_ids = set(all_items["ids"])
    except Exception:
        pass

    to_ingest = []
    skipped = 0
    for f in files:
        if file_id(f) in existing_ids:
            skipped += 1
        else:
            to_ingest.append(f)

    if skipped > 0:
        print(f"  Skipping {skipped} already-ingested files")
    print(f"  Ingesting {len(to_ingest)} new/changed files\n")

    if not to_ingest:
        print("Everything is up to date.")
        return

    ingested = 0
    errors = 0
    start_time = time.time()

    for i, filepath in enumerate(to_ingest, 1):
        fname = os.path.basename(filepath)
        try:
            result = ingest_file(filepath, collection)
            if result["status"] == "ingested":
                ingested += 1
                print(f"  [{i}/{len(to_ingest)}] ✓ {fname}")
            else:
                print(f"  [{i}/{len(to_ingest)}] - {fname} ({result.get('reason', '')})")
        except Exception as e:
            errors += 1
            print(f"  [{i}/{len(to_ingest)}] ✗ {fname} — {e}")

        if i < len(to_ingest):
            time.sleep(BATCH_DELAY_SEC)

    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Ingested: {ingested}")
    if errors:
        print(f"  Errors: {errors}")
    print(f"  Total in memory: {collection.count()}")


if __name__ == "__main__":
    main()
