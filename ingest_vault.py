#!/usr/bin/env python3
"""
ingest_vault.py — Bulk-ingest an Obsidian vault into the Gemini Memory Engine.

Scans a vault directory for .md files, generates embeddings via Gemini
Embedding 2, and stores them in the shared ChromaDB memory index.

Skips Archive/, Templates/, and .obsidian/ folders by default.
Uses deterministic IDs (filepath + mtime hash) to avoid re-ingesting
unchanged files.

Usage:
    python ingest_vault.py                          # ingest entire vault
    python ingest_vault.py --dry-run                # count files, don't ingest
    python ingest_vault.py --folder 03_Projects     # ingest one subfolder
    python ingest_vault.py --vault ~/my-vault       # custom vault path
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

DEFAULT_VAULT = str(Path.home() / "Documents" / "Obsidian" / "LifeOS")

# Folders to skip during ingestion
SKIP_FOLDERS = {"Archive", "Templates", ".obsidian", ".trash", ".git"}

# Rate limit: Gemini free tier = 1500 RPM, but be conservative
BATCH_DELAY_SEC = 0.1  # 100ms between API calls


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


def extract_title(filepath: str, content: str) -> str:
    """Extract the note title from first H1 heading, or fall back to filename."""
    for line in content.split("\n")[:20]:
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("##"):
            return stripped[2:].strip()
    return Path(filepath).stem


def get_subfolder(filepath: str, vault_root: str) -> str:
    """Get the top-level subfolder name relative to vault root."""
    rel = os.path.relpath(filepath, vault_root)
    parts = Path(rel).parts
    if len(parts) > 1:
        return parts[0]
    return "(root)"


def should_skip(filepath: str, vault_root: str) -> bool:
    """Check if the file is in a folder that should be skipped."""
    rel = os.path.relpath(filepath, vault_root)
    parts = Path(rel).parts
    for part in parts:
        if part in SKIP_FOLDERS:
            return True
    return False


def discover_files(vault_root: str, folder_filter: str | None = None) -> list[str]:
    """Walk the vault and collect all .md files, respecting skip rules."""
    files = []
    scan_root = vault_root
    if folder_filter:
        scan_root = os.path.join(vault_root, folder_filter)
        if not os.path.isdir(scan_root):
            print(f"Error: folder not found: {scan_root}", file=sys.stderr)
            sys.exit(1)

    for root, dirs, filenames in os.walk(scan_root):
        # Prune skipped directories in-place so os.walk doesn't descend
        dirs[:] = [d for d in dirs if d not in SKIP_FOLDERS]

        for fname in filenames:
            if not fname.endswith(".md"):
                continue
            full_path = os.path.join(root, fname)
            if not should_skip(full_path, vault_root):
                files.append(full_path)

    return sorted(files)


def embed_text(text: str) -> list[float]:
    """Embed a text string via Gemini Embedding 2."""
    result = genai.embed_content(
        model=MODEL,
        content=text,
        task_type="RETRIEVAL_DOCUMENT",
        output_dimensionality=DIMENSIONS,
    )
    return result["embedding"]


def ingest_file(filepath: str, vault_root: str, collection) -> dict:
    """Embed and store a single vault file. Returns metadata dict."""
    fid = file_id(filepath)
    rel_path = os.path.relpath(filepath, vault_root)
    subfolder = get_subfolder(filepath, vault_root)

    # Read file content
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    if not content.strip():
        return {"id": fid, "status": "skipped", "reason": "empty"}

    title = extract_title(filepath, content)

    # Truncate very large notes for embedding (Gemini handles up to ~10K tokens)
    embed_content = content[:30000]

    # Generate embedding
    embedding = embed_text(embed_content)

    # Build metadata
    tags = ["obsidian", subfolder]
    metadata = {
        "filename": os.path.basename(filepath),
        "filepath": os.path.abspath(filepath),
        "vault_path": rel_path,
        "title": title,
        "type": "text",
        "extension": ".md",
        "tags": ",".join(tags),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": os.path.getsize(filepath),
        "source": "obsidian-vault",
    }

    # Store in ChromaDB (upsert handles duplicates)
    collection.upsert(
        ids=[fid],
        embeddings=[embedding],
        documents=[content[:500]],  # preview text
        metadatas=[metadata],
    )

    return {"id": fid, "status": "ingested", "title": title, "path": rel_path}


def main():
    parser = argparse.ArgumentParser(
        description="Bulk-ingest an Obsidian vault into the Gemini Memory Engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # ingest entire vault
  %(prog)s --dry-run                    # count files without ingesting
  %(prog)s --folder 03_Projects         # ingest only Projects folder
  %(prog)s --vault ~/my-other-vault     # use a different vault path
        """,
    )
    parser.add_argument("--vault", default=DEFAULT_VAULT, help=f"Vault root path (default: {DEFAULT_VAULT})")
    parser.add_argument("--folder", help="Only ingest files in this subfolder")
    parser.add_argument("--dry-run", action="store_true", help="Count files without ingesting")
    args = parser.parse_args()

    vault_root = os.path.expanduser(args.vault)
    if not os.path.isdir(vault_root):
        print(f"Error: vault not found at {vault_root}", file=sys.stderr)
        sys.exit(1)

    # Discover files
    print(f"Scanning vault: {vault_root}")
    if args.folder:
        print(f"  Filtering to: {args.folder}/")
    files = discover_files(vault_root, args.folder)
    print(f"  Found {len(files)} .md files\n")

    if not files:
        print("No files to ingest.")
        return

    # Dry run: just show stats
    if args.dry_run:
        # Group by subfolder
        by_folder = {}
        for f in files:
            sf = get_subfolder(f, vault_root)
            by_folder.setdefault(sf, []).append(f)

        print("Dry run — files by folder:\n")
        for folder, folder_files in sorted(by_folder.items()):
            print(f"  {folder}: {len(folder_files)} files")
        print(f"\n  Total: {len(files)} files")
        print("  (use without --dry-run to ingest)")
        return

    # Configure Gemini
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: set GEMINI_API_KEY or GOOGLE_API_KEY environment variable", file=sys.stderr)
        sys.exit(1)
    genai.configure(api_key=api_key)

    # Check which files are already ingested
    collection = get_collection()
    existing_ids = set()
    try:
        all_items = collection.get()
        existing_ids = set(all_items["ids"])
    except Exception:
        pass

    # Filter to new/changed files only
    to_ingest = []
    skipped_existing = 0
    for f in files:
        fid = file_id(f)
        if fid in existing_ids:
            skipped_existing += 1
        else:
            to_ingest.append(f)

    if skipped_existing > 0:
        print(f"  Skipping {skipped_existing} already-ingested files")
    print(f"  Ingesting {len(to_ingest)} new/changed files\n")

    if not to_ingest:
        print("Everything is up to date.")
        return

    # Ingest files with progress
    ingested = 0
    errors = 0
    start_time = time.time()

    for i, filepath in enumerate(to_ingest, 1):
        rel = os.path.relpath(filepath, vault_root)
        try:
            result = ingest_file(filepath, vault_root, collection)
            if result["status"] == "ingested":
                ingested += 1
                print(f"  [{i}/{len(to_ingest)}] ✓ {rel}")
            else:
                print(f"  [{i}/{len(to_ingest)}] - {rel} ({result.get('reason', 'skipped')})")
        except Exception as e:
            errors += 1
            print(f"  [{i}/{len(to_ingest)}] ✗ {rel} — {e}")

        # Rate limit
        if i < len(to_ingest):
            time.sleep(BATCH_DELAY_SEC)

    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Ingested: {ingested}")
    if errors:
        print(f"  Errors: {errors}")
    print(f"  Total in memory: {collection.count()}")
    print(f"  DB path: {DB_PATH}")


if __name__ == "__main__":
    main()
