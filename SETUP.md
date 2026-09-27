# Running Urja Kavach locally

This gets the full stack — backend + India Connect Portal frontend — running
on your machine. Two terminals, no external database to install.

## 0. Prerequisites (install once)

- **Python 3.11+** — check with `python3 --version`
- **Node.js 20+** — check with `node --version`
- **Git**

That's it. The backend uses SQLite (a local file) and seeds itself on first run.

## 1. Get the code

`main` is the single integrated branch — no branch switch needed.

If cloning fresh:

```bash
git clone https://github.com/Titli06/Urja-Kawach.git
cd Urja-Kawach
```

If you already have the repo:

```bash
cd Urja-Kawach
git checkout main
git pull
```

## 2. Terminal 1 — start the backend (do this first)

```bash
# from the repo root
python3 -m venv .venv

# activate the venv:
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows (PowerShell/CMD)

pip install -r requirements.txt
uvicorn backend.app:app --reload
```

Leave it running. It's up when you see `Uvicorn running on http://127.0.0.1:8000`.
First launch auto-creates the database and seeds the corridors/suppliers/refineries.
(Optional check: open `http://localhost:8000/docs`.)

## 3. Terminal 2 — start the frontend

```bash
# from the repo root, in a SECOND terminal
cd "India Connect Portal"
npm install          # first time only; takes a minute
npm run dev
```

It's up when you see `Local: http://localhost:8080`.

## 4. Use it

Open **http://localhost:8080** in your browser.

- Click **Get started**, create an account, and pick a role:
  - **Official** → lands on **Mission Control** → hit **"Launch Simulation"** to see
    the full cascade (risk gauge, corridor map, economic impact, reroutes, reserve,
    audit trail).
  - **Citizen** → the calm public status board.
- No config needed — the frontend automatically talks to the backend on port 8000.

## Important notes / troubleshooting

- **Start the backend first.** The frontend proxies API + WebSocket calls to
  `localhost:8000`; if the backend isn't running, login/data won't work.
- **Keep both terminals open** — one backend, one frontend.
- **Port already in use?** Something else is on 8000 or 8080 — stop it, or run the
  backend on another port:
  ```bash
  uvicorn backend.app:app --reload --port 8001
  ```
  then before `npm run dev`, set:
  ```bash
  export BACKEND_URL=http://localhost:8001   # macOS/Linux
  # set BACKEND_URL=http://localhost:8001    # Windows CMD
  ```
- **`command not found` on activate (Windows):** use `.venv\Scripts\activate`
  instead of the `source` line.
- **Run the backend tests** (optional): with the venv active, `python -m pytest`.
- You **don't** need a `.env` file for local dev; the defaults work. There's a
  dev-only `JWT_SECRET` default — only real deployments need to set a proper one
  (see `.env.example` and `India Connect Portal/.env.example`).
- **Watch agent (v1.3, optional):** by default `USE_REAL_AGENTS=0`, so Watch
  uses its deterministic offline stub — no extra setup needed. To try the real
  RAG+LLM agent, set `USE_REAL_AGENTS=1` and `GROQ_API_KEY=<your key>` in a
  local `.env` (free tier at [console.groq.com](https://console.groq.com)).
  The **first** real-agent run downloads a small (~90MB) local embedding model
  (Chroma's bundled ONNX MiniLM) — this needs network access once; after that
  it's cached locally and every run is fully offline. Any missing key, rate
  limit, or network error automatically falls back to the same deterministic
  stub, so the demo never hard-fails.

## Project docs

- [CLAUDE.md](CLAUDE.md) — orientation for a new contributor or AI agent; start here.
- [PLAN.md](.claude/docs/PLAN.md) — the live forward plan (what's built vs. what's left, phased).
- [PROJECT_GUIDE.md](PROJECT_GUIDE.md) — architecture, full PRD (v1.0 + v1.3
  delta), and the historical per-dev status board.
- [README.md](README.md) — the main project README: pitch, live demo links, quick start, and the contract layer (`backend/schemas/contract.py`).
- [README-dev-a.md](README-dev-a.md) — backend API reference.
- [DEV_B_ROADMAP.md](.claude/docs/DEV_B_ROADMAP.md) — AI/ML implementation detail (LLM
  client, RAG, formulas, knowledge graph).
- [India Connect Portal/spec.md](India%20Connect%20Portal/spec.md) — frontend architecture and phased build history.
