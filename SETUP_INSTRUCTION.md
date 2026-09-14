# Paralegal Sophia — Setup Guide

This guide walks you through getting the Paralegal Sophia repo running locally with Docker for the first time. It covers the two containers (`frontend`, `backend`), the Supabase backend they depend on, and every environment variable and external service credential you'll need before `docker compose up` will work.

---

## 1. What you'll need before you start

Docker Compose only builds and runs the **frontend** and **backend** containers — it does not stand up a database. This project relies on **Supabase** (hosted, or a local Supabase stack) plus a handful of third-party APIs. Get accounts/keys for these first:

| Service | Used for | Where to get it |
|---|---|---|
| [Supabase](https://supabase.com) | Postgres + pgvector DB, auth, storage, edge functions | Create a project at supabase.com |
| [Laws.Africa](https://laws.africa) | Ugandan case law search | Laws.Africa API access |
| [Tavily](https://tavily.com) | Web search tool | Tavily API key |
| [OpenRouter](https://openrouter.ai) | Report generation LLM + embeddings | OpenRouter API key |
| AWS (Bedrock) | Chat/drafting agent LLM (`deepseek.v3-v1:0`, region `eu-north-1`) | AWS account with Bedrock model access enabled in `eu-north-1` |

You'll also want the [Supabase CLI](https://supabase.com/docs/guides/cli) installed locally — it's used to push the database schema and deploy edge functions, neither of which runs inside the Docker containers.

Install Docker Desktop (or Docker Engine + Compose plugin) if you don't already have it.

---

## 2. Clone the repo

```bash
git clone https://github.com/amanyiredanielmasse/paralegal.git
cd paralegal
```

---

## 3. Configure environment variables

Copy the example env file:

```bash
cp .env.example .env
```

Open `.env` and fill in every value:

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (backend only — keep secret) |
| `LAWS_AFRICA_API_KEY` | Laws.Africa API key |
| `TAVILY_API_KEY` | Tavily search API key |
| `OPENROUTER_API_KEY` | OpenRouter API key (report generation + embeddings) |
| `AWS_ACCESS_KEY_ID` | AWS credentials with Bedrock access |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials with Bedrock access |
| `AWS_DEFAULT_REGION` | Must be `eu-north-1` (region of the `deepseek.v3-v1:0` model) |
| `VITE_AGENT_API_URL` | URL the frontend uses to reach the backend — `http://localhost:8080` for local Docker use |
| `VITE_SUPABASE_URL` | Same as `SUPABASE_URL` (exposed to the frontend) |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Supabase anon/public key |

**Note on the backend container:** `docker-compose.yml` loads all of `.env` into the `backend` service via `env_file`, so anything you set there is available to the FastAPI app automatically. The `frontend` service only receives the three `VITE_*` variables explicitly listed in `docker-compose.yml` — if you add other frontend-facing variables later, you'll need to add them there too.

### Edge function secrets (separate from `.env`)

The Supabase Edge Functions (`monthly-report`, `activity-report`, the embedding pipeline) run on Supabase's infrastructure, not in your Docker containers, so they don't read from `.env` at all. Set their secrets directly on your Supabase project:

```bash
supabase secrets set OPENROUTER_API_KEY=sk-or-...
supabase secrets set SUPABASE_URL=...
supabase secrets set SUPABASE_SERVICE_ROLE_KEY=...
```

---

## 4. Set up the Supabase database

This step happens outside Docker, using the Supabase CLI:

```bash
supabase link --project-ref YOUR_PROJECT_REF
supabase db push
```

This applies the migrations in `supabase/migrations/` (schema for `profiles`, `cases`, `user_documents`, `legal_corpus_chunks`, and the pgvector setup).

Then deploy the edge functions (report generation, exports, court-submission drafting):

```bash
supabase functions deploy monthly-report
supabase functions deploy activity-report
supabase functions deploy excel-export
```

Make sure the edge function secrets from step 3 are set **before** deploying, or `monthly-report` and `activity-report` will fail at request time.

---

## 5. Build and run with Docker Compose

From the repo root:

```bash
docker compose up
```

This builds and starts two services, both defined in `docker-compose.yml`:

- **`backend`** — built from `app/Dockerfile` (Python 3.11-slim, installs `app/requirements.txt`, runs `uvicorn app.main:app` on port `8080`). This is the FastAPI + Strands Agents backend that powers the chat/drafting agent.
- **`frontend`** — built from `Dockerfile.frontend` (`oven/bun:1`, runs `bun install` then `bun run dev --host 0.0.0.0 --port 3000`). This is the React/TanStack Router app in dev mode.

The `frontend` service depends on `backend` and is configured to talk to it at `http://localhost:8080`.

To rebuild after dependency or Dockerfile changes:

```bash
docker compose up --build
```

To run in the background:

```bash
docker compose up -d
```

To stop everything:

```bash
docker compose down
```

---

## 6. Verify it's working

- **Backend health check:** `curl http://localhost:8080/healthz` should return a healthy response.
- **Frontend:** open `http://localhost:3000` in a browser — you should see the Paralegal Sophia app and be able to sign in via Supabase auth.
- **Chat agent:** try a message in the chat tab; it calls `/api/chat`, which proxies to the backend container.

If the chat agent fails, double-check `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION` and that your AWS account actually has access enabled to the `deepseek.v3-v1:0` model in Bedrock, in the `eu-north-1` region — Bedrock model access is opt-in per account/region.

---

## 7. Optional: seed the legal corpus

If you want semantic search over your own documents, upload them through the app as `legal_corpus` documents, or run the embedding pipeline manually (this runs locally via `uv`, not in Docker):

```bash
uv run python scripts/embed_documents.py
```

This embeds any unembedded `legal_corpus_chunks` rows via OpenRouter (`baai/bge-m3`).

---
Last but not least, feel free to change the model in `agent.py` to something stronger; we actually encourage you to do this, unless you are being conscious of the cost, in that case, the current model does a pretty good job.
