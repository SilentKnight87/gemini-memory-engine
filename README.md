# Gemini Memory Engine 🧠

> ⚠️ **DEPRECATED** — As of [OpenClaw 2026.3.11](https://docs.openclaw.ai/concepts/memory), Gemini Embedding 2 is natively integrated into OpenClaw's memory search with multimodal indexing, hybrid search (BM25 + vector), MMR diversity, temporal decay, and embedding caching. This standalone tool is no longer actively maintained. See the [OpenClaw memory docs](https://docs.openclaw.ai/concepts/memory) for the built-in solution.

---

A standalone personal memory layer powered by Google's **Gemini Embedding 2**, the first natively multimodal embedding model that puts text, images, audio, video, and documents in the same vector space.

Capture anything. Recall by meaning. Zero server required.

## What It Does

- **`capture.py`** — Feed it any file (notes, photos, voice memos, PDFs) and it embeds the content using Gemini Embedding 2, then stores it locally in ChromaDB
- **`recall.py`** — Ask a question in plain English and get back the most semantically relevant memories, regardless of whether they were text, images, or audio
- **`ingest_vault.py`** — Bulk-ingest an entire Obsidian vault into the memory index (skip what's unchanged, filter by folder)
- **`ingest_openclaw.py`** — Ingest OpenClaw session logs and voice note transcripts into the same index

Because all modalities live in the same embedding space, you can search across them: a text query like "sunset at the beach" will surface your beach photos, your journal entry about that day, *and* the voice memo you recorded on the drive home.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CAPTURE LAYER                            │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│  capture.py  │ ingest_vault │ ingest_open  │  (future: watch   │
│  (any file)  │   .py        │  claw.py     │   mode, webhook)  │
│              │  (Obsidian)  │  (sessions)  │                   │
└──────┬───────┴──────┬───────┴──────┬───────┴───────────────────┘
       │              │              │
       ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Gemini Embedding 2 (multimodal)                    │
│         models/gemini-embedding-2-preview                       │
│    text • images • audio • video • PDF → 768-dim vectors        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ChromaDB (local)                              │
│            ~/.memory/chromadb  •  cosine similarity              │
│             zero config  •  SQLite under the hood               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                       RECALL LAYER                              │
│  recall.py — semantic search across all captured content        │
│  --json output for piping into agents / scripts / UIs           │
└─────────────────────────────────────────────────────────────────┘
```

## Quickstart

### Prerequisites

- Python 3.11+
- A [Gemini API key](https://aistudio.google.com/apikey) (free tier works)

### Install

```bash
git clone https://github.com/SilentKnight87/gemini-memory-engine.git
cd gemini-memory-engine
pip install -r requirements.txt
export GEMINI_API_KEY="your-key-here"
```

### Capture Individual Files

```bash
# Text files
python capture.py meeting-notes.txt --tags work standup

# Images
python capture.py vacation-photo.jpg --tags travel hawaii

# Voice memos
python capture.py voice-memo.m4a --tags ideas startup

# PDFs
python capture.py quarterly-report.pdf --tags finance q4

# Raw text (no file needed)
python capture.py --text "The Thai place on 5th Ave was incredible" --tags food nyc
```

### Bulk Ingest an Obsidian Vault

```bash
# See what would be ingested (no API calls)
python ingest_vault.py --dry-run

# Ingest just one folder
python ingest_vault.py --folder 03_Projects

# Ingest the entire vault
python ingest_vault.py

# Custom vault path
python ingest_vault.py --vault ~/my-other-vault
```

The vault ingester:
- Scans for `.md` files only
- Skips `Archive/`, `Templates/`, `.obsidian/`, `.trash/`, `.git/`
- Tags each file with `obsidian` + its top-level subfolder name
- Extracts the title from the first H1 heading (falls back to filename)
- Skips files that haven't changed since last ingest (deterministic ID from path + mtime)
- Respects Gemini API rate limits

### Ingest OpenClaw Session Logs

```bash
# See what would be ingested
python ingest_openclaw.py --dry-run

# Ingest all session logs + MEMORY.md
python ingest_openclaw.py
```

### Recall / Search

```bash
# Semantic search across everything
python recall.py "that restaurant recommendation"

# Filter by type
python recall.py "sunset photos" --type image

# Filter by tag
python recall.py "meeting about budget" --tag work

# Search only Obsidian notes
python recall.py "cybercab fleet business plan" --tag obsidian

# JSON output (for piping to other tools)
python recall.py "vacation plans" --json

# List all memories
python recall.py --list

# Stats
python recall.py --stats
```

## How It Works

1. **Capture**: Detect file type → embed with Gemini Embedding 2 → store vector + metadata in ChromaDB
2. **Recall**: Embed your query → cosine similarity search → return top-k matches with scores

The model outputs 768-dimensional vectors by default (configurable to 1536 or 3072). All modalities land in the same vector space, so cross-modal search works out of the box.

## Supported File Types

| Type | Extensions | Method |
|---|---|---|
| Text | .txt, .md, .py, .json, .csv, .yaml, .html, ... | Direct embed |
| Image | .jpg, .png, .gif, .webp, .bmp | PIL → embed |
| Audio | .mp3, .wav, .ogg, .m4a, .flac | Upload → embed |
| Video | .mp4, .mov, .webm | Upload → embed |
| PDF | .pdf | Upload → embed |

## Architecture Decisions

- **ChromaDB** over Qdrant/Pinecone: zero config, no server, SQLite under the hood. Perfect for a personal tool.
- **768 dimensions**: Gemini Embedding 2 supports 768/1536/3072 via Matryoshka Representation Learning. 768 is ~95% of peak quality at 25% of the storage.
- **No chunking**: Each file = one embedding. Works well for notes, photos, short audio. Chunking for large docs is a natural v2.
- **Deterministic IDs**: File path + mtime hash prevents duplicates on re-capture.
- **No frameworks**: Raw Gemini SDK + ChromaDB. No LangChain, no LlamaIndex. Fewer dependencies, easier to understand.

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | (required) | Your Google AI API key |
| `MEMORY_DB_PATH` | `~/.memory/chromadb` | Where ChromaDB stores vectors |

## Why Deprecated?

This project was built as a proof-of-concept the week Gemini Embedding 2 launched (March 2026). It demonstrated that multimodal semantic search over personal data was practical with ~200 lines of Python and zero infrastructure.

[OpenClaw 2026.3.11](https://github.com/openclaw/openclaw) subsequently shipped native Gemini Embedding 2 support that exceeds this tool's capabilities:

- **Hybrid search** (BM25 + vector) for both semantic and keyword matching
- **MMR re-ranking** to deduplicate near-identical results
- **Temporal decay** so recent memories rank higher
- **Embedding cache** to avoid re-embedding unchanged content
- **Multimodal indexing** of images and audio files
- **File watching** with automatic reindexing on changes
- **Session transcript indexing** for conversation recall

The code here remains available as a reference implementation for anyone building standalone multimodal search without a platform dependency.

## License

MIT
