#!/usr/bin/env python3
"""
recall.py — Search your personal memory by meaning.

Queries Gemini Embedding 2 to find semantically similar captures
across text, images, audio, and documents in your local ChromaDB.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import chromadb
import google.generativeai as genai

# ── Config ──────────────────────────────────────────────────────────
MODEL = "models/gemini-embedding-2-preview"
DIMENSIONS = 768
DB_PATH = os.environ.get("MEMORY_DB_PATH", str(Path.home() / ".memory" / "chromadb"))
COLLECTION = "memory"


def get_collection():
    """Get the ChromaDB collection."""
    client = chromadb.PersistentClient(path=DB_PATH)
    try:
        return client.get_collection(name=COLLECTION)
    except Exception:
        print("No memories found. Capture something first with capture.py", file=sys.stderr)
        sys.exit(1)


def recall(query: str, top_k: int = 5, tag_filter: str | None = None,
           type_filter: str | None = None, output_json: bool = False):
    """Search memories by semantic similarity."""
    # Embed the query
    result = genai.embed_content(
        model=MODEL,
        content=query,
        task_type="RETRIEVAL_QUERY",
        output_dimensionality=DIMENSIONS,
    )
    query_embedding = result["embedding"]

    # Build ChromaDB where filter
    where = {}
    if tag_filter:
        where["tags"] = {"$contains": tag_filter}
    if type_filter:
        where["type"] = type_filter

    collection = get_collection()

    query_params = {
        "query_embeddings": [query_embedding],
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        query_params["where"] = where

    results = collection.query(**query_params)

    if not results["ids"][0]:
        print("No matching memories found.")
        return

    memories = []
    for i, mid in enumerate(results["ids"][0]):
        meta = results["metadatas"][0][i]
        doc = results["documents"][0][i]
        distance = results["distances"][0][i]
        # ChromaDB cosine distance: 0 = identical, 2 = opposite
        # Convert to similarity score: 1 - (distance / 2)
        similarity = 1.0 - (distance / 2.0)

        memories.append({
            "id": mid,
            "similarity": round(similarity, 4),
            "filename": meta.get("filename", ""),
            "type": meta.get("type", ""),
            "tags": meta.get("tags", ""),
            "note": meta.get("note", ""),
            "captured_at": meta.get("captured_at", ""),
            "filepath": meta.get("filepath", ""),
            "preview": doc[:200] if doc else "",
        })

    if output_json:
        print(json.dumps(memories, indent=2))
        return

    # Pretty print
    print(f"\n🔍 Query: \"{query}\"")
    print(f"   Found {len(memories)} result(s)\n")

    for i, m in enumerate(memories, 1):
        score_bar = "█" * int(m["similarity"] * 20) + "░" * (20 - int(m["similarity"] * 20))
        print(f"  {i}. [{score_bar}] {m['similarity']:.1%}")
        print(f"     📄 {m['filename'] or '(text snippet)'}  ({m['type']})")
        if m["tags"]:
            print(f"     🏷️  {m['tags']}")
        if m["note"]:
            print(f"     📝 {m['note']}")
        if m["preview"] and m["type"] == "text":
            preview = m["preview"].replace("\n", " ")[:120]
            print(f"     → {preview}...")
        if m["captured_at"]:
            print(f"     ⏰ {m['captured_at'][:19]}")
        print()


def list_memories(output_json: bool = False):
    """List all stored memories."""
    collection = get_collection()
    all_items = collection.get(include=["metadatas"])

    if not all_items["ids"]:
        print("No memories stored yet.")
        return

    if output_json:
        items = []
        for i, mid in enumerate(all_items["ids"]):
            meta = all_items["metadatas"][i]
            items.append({"id": mid, **meta})
        print(json.dumps(items, indent=2))
        return

    print(f"\n📦 Memory Store: {len(all_items['ids'])} items\n")
    by_type = {}
    for i, mid in enumerate(all_items["ids"]):
        meta = all_items["metadatas"][i]
        ftype = meta.get("type", "unknown")
        by_type.setdefault(ftype, []).append(meta)

    for ftype, items in sorted(by_type.items()):
        print(f"  {ftype} ({len(items)}):")
        for item in items[:10]:
            fname = item.get("filename", "(unknown)")
            tags = f" [{item['tags']}]" if item.get("tags") else ""
            print(f"    • {fname}{tags}")
        if len(items) > 10:
            print(f"    ... and {len(items) - 10} more")
        print()


def stats():
    """Show memory store statistics."""
    collection = get_collection()
    count = collection.count()
    all_items = collection.get(include=["metadatas"])

    types = {}
    tags_set = set()
    for meta in all_items["metadatas"]:
        t = meta.get("type", "unknown")
        types[t] = types.get(t, 0) + 1
        if meta.get("tags"):
            for tag in meta["tags"].split(","):
                tags_set.add(tag.strip())

    print(f"\n📊 Memory Stats")
    print(f"   Total memories: {count}")
    print(f"   DB path: {DB_PATH}")
    print(f"\n   By type:")
    for t, n in sorted(types.items()):
        print(f"     {t}: {n}")
    if tags_set:
        print(f"\n   Tags: {', '.join(sorted(tags_set))}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Search your personal memory by meaning.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "that restaurant with great pasta"
  %(prog)s "meeting about Q4 budget" --top 3
  %(prog)s "sunset photos" --type image
  %(prog)s "AI podcast" --tag podcast
  %(prog)s --list
  %(prog)s --stats
  %(prog)s "vacation plans" --json
        """,
    )
    parser.add_argument("query", nargs="?", help="Search query (natural language)")
    parser.add_argument("--top", "-k", type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("--tag", help="Filter by tag")
    parser.add_argument("--type", dest="type_filter", choices=["text", "image", "audio", "video", "pdf"],
                        help="Filter by content type")
    parser.add_argument("--json", dest="output_json", action="store_true", help="Output as JSON")
    parser.add_argument("--list", "-l", action="store_true", help="List all stored memories")
    parser.add_argument("--stats", "-s", action="store_true", help="Show memory statistics")
    args = parser.parse_args()

    if not args.query and not args.list and not args.stats:
        parser.error("Provide a search query, --list, or --stats")

    # Configure Gemini
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: set GEMINI_API_KEY or GOOGLE_API_KEY environment variable", file=sys.stderr)
        sys.exit(1)
    genai.configure(api_key=api_key)

    if args.stats:
        stats()
    elif args.list:
        list_memories(args.output_json)
    else:
        recall(args.query, args.top, args.tag, args.type_filter, args.output_json)


if __name__ == "__main__":
    main()
