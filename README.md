# Paralegal Sophia

An AI-powered paralegal assistant built for Ugandan legal practitioners. Sophia helps lawyers and paralegals research case law, manage client files, and draft formal court submissions — all through a conversational interface backed by a multi-agent architecture.

---

## What it does

Sophia is a multi-agent system that understands the Ugandan legal context. You can ask it questions in plain English and it will:

- **Research Ugandan case law** by querying the [Laws.Africa](https://laws.africa) judgments database and surfacing relevant precedents with citations
- **Search your private legal corpus** using semantic (vector) search over documents you've uploaded — previous submissions, precedents, reference materials
- **Look up client cases** from your case management database by client name, file number, case type, or status
- **Find current legal developments** via web search for recent news relevant to a matter
- **Draft court submissions** in proper Ugandan court format and export them as a Word document (.docx)
- **Generate monthly and activity reports** as narrative Word documents from your case log
- **Export your case log** to CSV for a given date range

---

## Architecture

```
Frontend (React + TanStack Router)
        │
        ├── ChatTab  ─────────────▶  /api/chat  ──▶  FastAPI backend (app/main.py)
        │                                                    │
        │                                                    ▼
        │                                            Strands Agents SDK
        │                                                    │
        │                                            root_agent (orchestrator / Sophia)
        │                                                    │
        │                                    ┌───────────────┼───────────────┐
        │                                    ▼               ▼               ▼
        │                            research_agent    case_agent      drafting_agent
        │                                    │               │               │
        │                          search_laws_africa   read_cases_db   generate_docx
        │                          search_legal_corpus   web_search      (python-docx)
        │                          (Laws.Africa API)     (Tavily)             │
        │                                                                write_result
        │                                                              (saves to Supabase)
        │
        └── AgentTab (Excel/Monthly/Activity reports) ──▶ Supabase Edge Functions
                                                                    │
                                                    ┌───────────────┼───────────────┐
                                                    ▼               ▼               ▼
                                            excel-export    monthly-report   activity-report
                                                                    │               │
                                                                    └───────┬───────┘
                                                                            ▼
                                                                     OpenRouter (LLM)
                                                                            │
                                                                   in-function .docx builder

Supabase (PostgreSQL + pgvector)
        ├── profiles          user accounts & subscription tier
        ├── cases             client case management records
        ├── user_documents    uploaded files (stored in Supabase Storage)
        └── legal_corpus_chunks  vectorised document chunks (1024-dim, OpenRouter embeddings)
```

There are two independent LLM-backed surfaces in this app, and it's important not to conflate them:

1. **Chat / drafting agent** (`ChatTab.tsx` → `/api/chat` → `app/main.py` → `app/agent.py`) — a [Strands Agents SDK](https://strandsagents.com) orchestrator running on **Amazon Bedrock** (`deepseek.v3-v1:0`, `eu-north-1`). This is the conversational agent with sub-agents for research, case lookup, and drafting. It is proxied through Vite's dev server (`/api` → `http://backend:8080`) locally, and through whatever reverse proxy fronts the FastAPI container in production.
2. **Report generation** (`AgentTab.tsx` → Supabase Edge Functions `monthly-report` / `activity-report` / `excel-export`) — separate, simpler Deno functions that call **OpenRouter** directly (`deepseek/deepseek-v4-flash`) to write report narratives, then assemble a `.docx` in-function using a small hand-rolled zip/OOXML writer (see `supabase/functions/_shared/report.ts`). These do not go through the Strands agent at all.

Document embeddings (for the private legal corpus / `pgvector` search) are also generated via **OpenRouter** (`baai/bge-m3`, 1024 dimensions) — see `app/lib/embeddings.py` and `scripts/embed_documents.py`

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TanStack Router, Tailwind CSS, shadcn/ui |
| Auth & DB | Supabase (PostgreSQL + pgvector + Row Level Security) |
| Edge functions | Supabase Edge Functions (Deno/TypeScript) — reports & exports |
| Agent framework | [Strands Agents SDK](https://strandsagents.com) |
| Agent runtime | FastAPI (`app/main.py`), containerised via `app/Dockerfile` |
| Chat/drafting LLM | Amazon Bedrock — `deepseek.v3-v1:0` (`eu-north-1`) |
| Report-generation LLM | OpenRouter — `deepseek/deepseek-v4-flash` |
| Embeddings | OpenRouter — `baai/bge-m3` (1024-dim) |
| Web search | Tavily |
| Case law | Laws.Africa Judgments API |
| Document generation | `python-docx` (chat/drafting agent) and an in-function OOXML writer (report edge functions) |
| Package management | Bun (frontend), uv (Python) |

---

## Project structure

```
paralegal/
├── app/                        Python agent backend (FastAPI + Strands)
│   ├── agent.py                Sub-agents and orchestrator definition (Strands, Bedrock)
│   ├── main.py                 FastAPI app — exposes POST /chat, GET /healthz
│   ├── requirements.txt        Python dependencies (strands-agents, boto3, fastapi, ...)
│   ├── Dockerfile              Container definition
│   ├── lib/
│   │   ├── embeddings.py       OpenRouter embedding helper
│   │   ├── request_context.py  Per-request context vars (user_id, run_id, tool tracking)
│   │   └── supabase_client.py  Supabase client singleton
│   └── tools/
│       ├── laws_africa.py      Laws.Africa case law search
│       ├── corpus_search.py    Private corpus vector search
│       ├── case_db.py          Client case database lookup
│       ├── web_search.py       Tavily web search
│       ├── docx_gen.py         Word document generation (drafting agent)
│       └── supabase_writer.py  Result persistence
├── src/                        React frontend
│   ├── routes/                 TanStack Router pages
│   ├── components/app/         ChatTab, AgentTab, LogEntryTab, SettingsTab
│   └── integrations/supabase/ Supabase client & auth
├── supabase/
│   ├── functions/
│   │   ├── chat/                (legacy/unused by ChatTab — see note below)
│   │   ├── monthly-report/      Narrative monthly/quarterly report → .docx (OpenRouter)
│   │   ├── activity-report/     Field activity report → .docx (OpenRouter)
│   │   ├── excel-export/        Case log export → .csv
│   │   ├── court-submission/    Court submission drafting
│   │   └── _shared/             auth.ts, cors.ts, report.ts (shared report/.docx logic)
│   └── migrations/             Database schema
├── scripts/
│   └── embed_documents.py      Document embedding pipeline (OpenRouter)
├── docker-compose.yml           Local dev: frontend + backend containers
├── pyproject.toml              Python project metadata
└── .env.example                Required environment variables
```

---

## Getting started

### Prerequisites

- Node.js 18+ and [Bun](https://bun.sh)
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- AWS credentials with Bedrock access (for the chat/drafting agent)
- A Supabase project
- An OpenRouter API key (for report generation and embeddings)

### 1. Clone and install

```bash
git clone https://github.com/amanyiredanielmasse/paralegal.git
cd paralegal

# Frontend dependencies
bun install

# Python dependencies
uv sync
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (backend only) |
| `LAWS_AFRICA_API_KEY` | Laws.Africa API key |
| `TAVILY_API_KEY` | Tavily search API key |
| `OPENROUTER_API_KEY` | OpenRouter API key (report generation + embeddings) |
| `AWS_ACCESS_KEY_ID` | AWS credentials with Bedrock access (chat/drafting agent) |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials with Bedrock access |
| `AWS_DEFAULT_REGION` | Should match the Bedrock model's region (`eu-north-1`) |
| `VITE_AGENT_API_URL` | URL of the FastAPI backend (e.g. `http://localhost:8080`) |
| `VITE_SUPABASE_URL` | Supabase project URL (frontend) |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Supabase anon/public key (frontend) |

Also set `OPENROUTER_API_KEY` (and the other backend secrets it needs — `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`/anon key) as **Supabase Edge Function secrets**, since `monthly-report`, `activity-report`, and the embedding pipeline call OpenRouter directly and don't read from `.env`:

```bash
supabase secrets set OPENROUTER_API_KEY=sk-or-...
```

### 3. Set up the database

```bash
supabase link --project-ref YOUR_PROJECT_REF
supabase db push
```

### 4. Run locally

```bash
# Frontend
bun run dev

# Agent backend (FastAPI + Strands)
cd app
uvicorn main:app --reload --port 8080
```

Or run both together via Docker Compose:

```bash
docker compose up
```

---

## Deploying

- **Frontend** — build with `bun run build` and deploy per `wrangler.jsonc` / `Dockerfile.frontend`.
- **Agent backend** — build the container from `app/Dockerfile` and deploy anywhere that can run a long-lived FastAPI/uvicorn process (it holds no state itself; all persistence goes through Supabase). Make sure the deploy target has AWS credentials with Bedrock access in `eu-north-1` for `deepseek.v3-v1:0`.
- **Edge functions** — deploy with the Supabase CLI:

```bash
supabase functions deploy monthly-report
supabase functions deploy activity-report
supabase functions deploy excel-export
supabase functions deploy court-submission
```

Make sure `OPENROUTER_API_KEY` is set as a secret on the Supabase project (see above) before deploying — `monthly-report` and `activity-report` will fail at request time (not at deploy time) if it's missing.

### Document embedding

Upload documents as `legal_corpus` kind via the app. To run the embedding pipeline manually:

```bash
uv run python scripts/embed_documents.py
```

This embeds any unembedded `legal_corpus_chunks` rows via OpenRouter (`baai/bge-m3`).

---

## Data privacy

All case records and uploaded documents are scoped to the authenticated user via Supabase Row Level Security. No user data is shared across accounts. Documents are stored in a private Supabase Storage bucket and are not accessible without authentication.

---

## License

See [LICENSE](LICENSE).