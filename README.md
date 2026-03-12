# Gemini Memory Engine 🧠

A universal personal memory layer powered by Google's **Gemini Embedding 2** — the first natively multimodal embedding model that puts text, images, audio, video, and documents in the same vector space.

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
git clone https://github.com/YOUR_USERNAME/gemini-memory-engine.git
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

# Ingest just one folder (recommended first run)
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

# Search only OpenClaw sessions
python recall.py "what did I discuss last week" --tag openclaw

# JSON output (for piping to other tools)
python recall.py "vacation plans" --json

# List all memories
python recall.py --list

# Stats
python recall.py --stats
```

## Peter's Setup

This is how I use the Gemini Memory Engine as part of my personal AI stack:

```
┌──────────────────────────────────────────────────────────┐
│                    Obsidian LifeOS Vault                  │
│         ~/Documents/Obsidian/LifeOS/                     │
│   Daily logs • Projects • Research • Weekly reviews      │
│                    (Tier 0: source of truth)              │
└────────────────────────┬─────────────────────────────────┘
                         │  ingest_vault.py
                         ▼
┌──────────────────────────────────────────────────────────┐
│              Gemini Memory Engine (ChromaDB)              │
│            Tier 3: on-demand semantic retrieval           │
│    "What changed since last week?"                       │
│    "Find my notes about X from 3 months ago"             │
└────────────────────────┬─────────────────────────────────┘
                         │  recall.py --json
                         ▼
┌──────────────────────────────────────────────────────────┐
│                       OpenClaw Agent                     │
│    Session logs, voice notes, daily interactions         │
│          ingest_openclaw.py feeds back in                │
└──────────────────────────────────────────────────────────┘
```

**The memory model has 4 tiers:**

| Tier | What | How |
|------|------|-----|
| 0 | Vault is the source of truth | Obsidian, plain markdown |
| 1 | Session continuity | Agent summaries, context windows |
| 2 | Core memories | Curated facts, capped at 20-40 items |
| 3 | Semantic retrieval | **This project** — on-demand search by meaning |

**When to add a semantic memory layer:**
- You're re-explaining the same context to your AI weekly
- You need "what changed since last week?" queries
- You want proactive monitoring of your notes

## How It Works

1. **Capture**: Detect file type → embed with Gemini Embedding 2 → store vector + metadata in ChromaDB
2. **Recall**: Embed your query → cosine similarity search → return top-k matches with scores

The model outputs 768-dimensional vectors by default (configurable to 1536 or 3072). All modalities — text, image, audio, video, PDF — land in the same vector space, so cross-modal search works out of the box.

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | (required) | Your Google AI API key |
| `MEMORY_DB_PATH` | `~/.memory/chromadb` | Where ChromaDB stores vectors |

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

## OpenClaw Integration

This tool works well as an [OpenClaw](https://openclaw.com) skill. Wire `capture.py` into your agent's workflow to automatically index documents, voice notes, screenshots, and more. Use `recall.py --json` for structured output your agent can reason over.

```bash
# Agent captures a screenshot
python capture.py screenshot.png --tags agent auto-captured

# Agent recalls context for a conversation
python recall.py "project deadlines this week" --json --top 3
```

## Roadmap

- [ ] Watch mode: auto-capture new files in a directory
- [ ] Chunking for large documents
- [ ] Web UI for browsing memories
- [ ] Export/import for backup
- [ ] Obsidian plugin for in-vault search
- [ ] OpenClaw skill wrapper (auto-capture inbound messages)

## License

MIT
