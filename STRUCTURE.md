# Repository Structure

```
gemini-memory-engine/
├── .github/
│   └── FUNDING.yml              # Sponsorship config (placeholder)
├── content/
│   ├── linkedin_post.md         # LinkedIn launch post draft
│   └── x_thread.md              # X/Twitter thread draft
├── capture.py                   # Capture any file into memory (core)
├── recall.py                    # Semantic search across memories (core)
├── ingest_vault.py              # Bulk-ingest Obsidian vault
├── ingest_openclaw.py           # Ingest OpenClaw session logs
├── requirements.txt             # Python dependencies
├── README.md                    # Full documentation + architecture
├── STRUCTURE.md                 # This file — repo layout
├── SHIP_TONIGHT.md              # Quick-start action plan
└── LICENSE                      # MIT (create before pushing)
```

## File Roles

| File | Purpose |
|------|---------|
| `capture.py` | Core: embed any file (text/image/audio/PDF) into ChromaDB |
| `recall.py` | Core: semantic search across all captured memories |
| `ingest_vault.py` | Batch: bulk-ingest an Obsidian vault, skip unchanged files |
| `ingest_openclaw.py` | Batch: ingest OpenClaw session logs + MEMORY.md |
| `requirements.txt` | `google-generativeai`, `chromadb`, `Pillow`, `python-magic` |
