# Ship Tonight 🚀

**Estimated time: 30 minutes total**

Everything is built and tested. Follow these steps to go live.

---

## Step 1: Get a Gemini API Key (2 min)

Go to [Google AI Studio](https://aistudio.google.com/apikey) and create a free API key. The free tier gives you 1500 requests/minute, more than enough for personal use.

```bash
export GEMINI_API_KEY="your-key-here"
```

## Step 2: Install Dependencies (1 min)

```bash
cd ~/clawd/tmp/gemini-memory
pip install -r requirements.txt
```

## Step 3: Dry Run — Verify Vault Discovery (2 min)

```bash
python ingest_vault.py --dry-run
```

This scans your Obsidian vault and shows file counts by folder. No API calls, no ingestion. Confirm it finds the right files.

## Step 4: Ingest Projects First (5–10 min)

Start small. Ingest just your Projects folder, not the entire vault:

```bash
python ingest_vault.py --folder 03_Projects
```

Watch the progress output. Each file gets embedded and stored. This is your proof-of-concept run.

## Step 5: First Demo Query (1 min)

```bash
python recall.py "cybercab fleet business plan"
```

You should see your Cybercab project notes surface with high similarity scores. Try a few more:

```bash
python recall.py "Gemini memory architecture"
python recall.py "weekly review template"
```

## Step 6: Push to GitHub (5 min)

```bash
cd ~/clawd/tmp/gemini-memory

# Create LICENSE file
echo "MIT License\n\nCopyright (c) 2026 Peter Brown\n\nPermission is hereby granted..." > LICENSE

# Init and push
git init
git add .
git commit -m "Initial release: Gemini Memory Engine"
git remote add origin git@github.com:YOUR_USERNAME/gemini-memory-engine.git
git branch -M main
git push -u origin main
```

## Step 7: Post on X (5 min)

Open `content/x_thread.md` for the ready-to-post thread. Key points:

1. Google dropped Gemini Embedding 2 yesterday
2. You built a personal memory layer with it in one evening
3. Voice notes, screenshots, notes — all searchable by meaning
4. Link to the GitHub repo
5. "Fork this" CTA

---

## What's Next

- [ ] Ingest the full vault: `python ingest_vault.py` (will take longer, do it overnight)
- [ ] Ingest OpenClaw logs: `python ingest_openclaw.py`
- [ ] Write the LinkedIn post (draft in `content/linkedin_post.md`)
- [ ] Build the OpenClaw skill wrapper (Phase 2)
- [ ] Add watch mode for auto-capture (Phase 3)
