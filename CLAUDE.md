# CLAUDE.md — AcadeMong: Project Specification & Build Guide

> This document is the single source of truth for the AcadeMong capstone project.
> Scope: POC (Proof of Concept). Not production. Cut complexity accordingly.
> All team members must read this before writing a single line of code.

---

## 1. Project Overview

An adaptive AI decision-support system for Thai students applying to universities under the TCAS system. Combines deterministic eligibility validation, hybrid RAG-based advisory, personalized major recommendations, and career path guidance.

**Key constraint**: The system must never hallucinate eligibility criteria (GPAX minimums, subject requirements). These always come from SQL — never from an LLM.

---

## 2. Goals

- Help students identify which majors/universities they are eligible for
- Recommend majors aligned to their academic profile and interests
- Guide career path planning with major → career → salary → license mapping
- Retain user memory across sessions for personalized longitudinal guidance
- Run entirely locally via Docker (no mandatory external API dependency)

---

## 3. Tech Stack

| Layer | Technology | Reason |
|---|---|---|
| Backend | FastAPI (Python) | Async, lightweight, easy to structure |
| Primary LLM | Typhoon2-8b-instruct (Ollama) | Thai language capable, runs locally |
| Fallback LLM | Llama3.1-8b (Ollama) | English reasoning fallback |
| Embeddings | nomic-embed-text (Ollama) | Local, no API cost |
| Vector DB | Qdrant | RAG retrieval, Docker-native |
| Relational DB | PostgreSQL | Structured eligibility data + user memory |
| Session Cache | Redis | Short-term session memory |
| Frontend | React (single page) | Chat UI + profile form + career view |
| Containerization | Docker Compose | All services in one stack |

---

## 4. Architecture

### 4.1 High-Level System Flow

```
User (Web Frontend)
        ↓
FastAPI Backend
        ↓
Auth Middleware (JWT)
        ↓
Long-Term Memory Fetch (PostgreSQL)
        ↓
Session Memory Load (Redis)
        ↓
Request Orchestrator
        ↓
Intent Router
        ↓
Engine Selection (SQL / RAG / Career / Hybrid)
        ↓
Adaptive Prompt Composer
        ↓
Model Router → Ollama (Typhoon2 / Llama3.1)
        ↓
Memory Update (Redis → PostgreSQL summarization)
        ↓
Response
```

### 4.2 Two Subsystems

**Offline Knowledge Engineering** (build once, update periodically)
- TCAS CSV ingestion → PostgreSQL
- PDF parsing + chunking + embedding → Qdrant
- Career data → PostgreSQL `career_paths` table

**Online Adaptive Runtime** (handles every user request)
- Intent routing, engine selection, prompt composition, LLM inference, memory management

---

## 5. Database Schema

### PostgreSQL Tables

```sql
-- Users
users (
  user_id       UUID PRIMARY KEY,
  username      VARCHAR UNIQUE,
  password_hash VARCHAR,
  gpax          FLOAT,
  interests     JSONB,   -- subject strengths, preferred fields
  memory        JSONB,   -- long-term AI memory: explored majors, career interests, history summary
  created_at    TIMESTAMP
)

-- Universities
universities (
  id    UUID PRIMARY KEY,
  name  VARCHAR,
  location VARCHAR
)

-- Faculties
faculties (
  id              UUID PRIMARY KEY,
  university_id   UUID REFERENCES universities(id),
  name            VARCHAR
)

-- Majors
majors (
  id          UUID PRIMARY KEY,
  faculty_id  UUID REFERENCES faculties(id),
  name        VARCHAR,
  field       VARCHAR   -- science, arts, business, etc.
)

-- TCAS Rounds (eligibility core)
tcas_rounds (
  id        UUID PRIMARY KEY,
  major_id  UUID REFERENCES majors(id),
  round     INT,        -- 1, 2, 3, 4
  year      INT,
  gpax_min  FLOAT,
  seats     INT
)

-- Subject Requirements
subject_requirements (
  id        UUID PRIMARY KEY,
  major_id  UUID REFERENCES majors(id),
  subject   VARCHAR,
  min_score FLOAT,
  weight    FLOAT
)

-- Career Paths
career_paths (
  id                UUID PRIMARY KEY,
  major_id          UUID REFERENCES majors(id),
  career_title      VARCHAR,
  salary_min        INT,
  salary_max        INT,
  license_required  VARCHAR,
  demand_level      VARCHAR   -- high, medium, low
)

-- Conversation History
conversation_history (
  id        UUID PRIMARY KEY,
  user_id   UUID REFERENCES users(user_id),
  role      VARCHAR,   -- 'user' or 'assistant'
  content   TEXT,
  timestamp TIMESTAMP
)
```

### Redis Keys (Session)
```
session:{user_id}:active_university   → string
session:{user_id}:active_major        → string
session:{user_id}:comparison_context  → JSON
session:{user_id}:current_window      → JSON array (last N messages)
```

---

## 6. Core Components

### 6.1 Intent Router
Classifies every incoming query into one of:

| Intent | Triggers Engine |
|---|---|
| `general` | LLM only |
| `eligibility` | SQL Eligibility Engine |
| `recommendation` | Major Recommendation Engine |
| `preparation` | RAG Engine |
| `comparison` | SQL + RAG hybrid |
| `career` | Career Path Engine |

Start with rule-based classification (keyword matching). Upgrade to a small classifier model only if accuracy is insufficient.

### 6.2 Eligibility Engine (SQL — No LLM)
```python
# Pseudologic — never hand this to the LLM
if student.gpax < major.gpax_min:
    return {"eligible": False, "reason": "GPAX below threshold"}
if student.subject_score(required_subject) < subject.min_score:
    return {"eligible": False, "reason": f"{subject} score insufficient"}
return {"eligible": True}
```

This is deterministic. No fuzzy logic. No LLM involved at any step.

### 6.3 RAG Engine (Hybrid Retrieval)
Activated only for: preparation guidance, curriculum explanation, portfolio requirements, interview expectations.

Retrieval pipeline:
1. Metadata filter (year, major, university, round)
2. Dense retrieval via nomic-embed-text embeddings in Qdrant
3. BM25 keyword retrieval (sparse)
4. Cross-encoder reranking
5. Top-K context selection → passed to prompt composer

Document hashing on ingestion — only reprocess changed PDFs.

### 6.4 Major Recommendation Engine
- Input: GPAX, subject strengths, declared interests, preferred universities
- Output: ranked list of majors with fit score
- Implementation: rule-based scoring for POC

### 6.5 Career Path Engine
- Input: recommended majors OR declared career interest
- Output: career paths → required licenses → salary range → demand level
- Gap analysis: "to become X, you need to strengthen Y"
- Data source: static JSON → loaded into PostgreSQL `career_paths`

### 6.6 User Memory Layer

**On login:**
```
Fetch long-term memory (PostgreSQL users.memory JSONB)
→ Load into Redis session
```

**Per request:**
```
Pull Redis session context
→ Inject into prompt composer
→ Update Redis after response
```

**On session end (or every N turns):**
```
Prompt Typhoon2 to summarize conversation
→ Extract structured fields (explored majors, career interests, GPAX updates)
→ Write back to PostgreSQL users.memory JSONB
```

### 6.7 Adaptive Prompt Composer
Final prompt = layered composition:

```
[Master Prompt]           ← static, never changes
+ [User Profile Memory]   ← from PostgreSQL / Redis
+ [Behavior Signals]      ← detected from session patterns
+ [Intent Template]       ← per-intent prompt template
+ [Retrieved Context]     ← from RAG engine (if activated)
= Final Prompt
```

**Behavior-based tone adaptation:**

| Pattern | Adaptation |
|---|---|
| Frequent comparison queries | Analytical, structured table output |
| Repeated preparation queries | Coaching tone, step-by-step |
| Low GPAX + competitive major | Realistic advisory, suggest alternatives |
| Short factual queries | Concise, no elaboration |

---

## 7. Model Config

```python
MODEL_CONFIG = {
    "primary": {
        "model": "typhoon2-8b-instruct",
        "intents": ["general", "eligibility", "recommendation", "career"],
        "temperature": 0.3,
        "top_p": 0.9,
        "max_tokens": 1000
    },
    "rag": {
        "model": "typhoon2-8b-instruct",
        "intents": ["preparation", "comparison"],
        "temperature": 0.2,   # lower — needs to stay grounded to retrieved context
        "top_p": 0.85,
        "max_tokens": 1500
    },
    "embedding": {
        "model": "nomic-embed-text"
    },
    "fallback": {
        "model": "llama3.1-8b",
        "trigger": "primary_model_failure"
    }
}
```

---

## 8. Auth

- **Register**: hash password with bcrypt → store in `users` table
- **Login**: verify password → return JWT token (python-jose)
- **Protected routes**: JWT middleware on all `/api/*` endpoints
- **Session**: token carries `user_id`, used to scope all Redis keys and DB queries

No OAuth. No email verification. No password reset. POC only.

---

## 9. Docker Compose

```yaml
services:
  fastapi:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [postgres, redis, qdrant, ollama]

  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: tcas_advisor
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: password
    volumes: ["pgdata:/var/lib/postgresql/data"]

  redis:
    image: redis:7
    ports: ["6379:6379"]

  qdrant:
    image: qdrant/qdrant
    ports: ["6333:6333"]
    volumes: ["qdrant_storage:/qdrant/storage"]

  ollama:
    image: ollama/ollama
    ports: ["11434:11434"]
    volumes: ["ollama_models:/root/.ollama"]

  frontend:
    build: ./frontend
    ports: ["3000:3000"]

volumes:
  pgdata:
  qdrant_storage:
  ollama_models:
```

**After first start, pull models:**
```bash
docker exec -it ollama ollama pull typhoon2-8b-instruct
docker exec -it ollama ollama pull nomic-embed-text
docker exec -it ollama ollama pull llama3.1:8b
```

---

## 10. Project Structure

```
tcas-advisor/
├── backend/
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # model config, env vars
│   ├── routers/
│   │   ├── auth.py                # register, login endpoints
│   │   ├── chat.py                # main chat endpoint
│   │   └── profile.py             # user profile CRUD
│   ├── engines/
│   │   ├── intent_router.py
│   │   ├── eligibility_engine.py
│   │   ├── recommendation_engine.py
│   │   ├── rag_engine.py
│   │   └── career_engine.py
│   ├── memory/
│   │   ├── session_memory.py      # Redis operations
│   │   └── long_term_memory.py    # PostgreSQL JSONB operations
│   ├── prompts/
│   │   ├── master_prompt.py       # static master prompt
│   │   ├── intent_templates.py    # per-intent templates
│   │   └── prompt_composer.py     # dynamic composition
│   ├── models/
│   │   ├── model_router.py
│   │   └── ollama_client.py
│   ├── ingestion/
│   │   ├── tcas_csv_ingestion.py
│   │   ├── pdf_parser.py
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   └── career_data_loader.py
│   └── db/
│       ├── postgres.py
│       └── schema.sql
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── ChatInterface.jsx
│   │   │   ├── ProfileForm.jsx
│   │   │   ├── MajorComparison.jsx
│   │   │   └── CareerPathView.jsx
│   └── Dockerfile
├── data/
│   ├── tcas_csvs/                 # raw MYTCAS downloads
│   ├── pdfs/                      # มคอ.2 and announcement PDFs
│   └── career/                    # career JSON mapping files
├── docker-compose.yml
├── .env
└── CLAUDE.md                      # this file
```

---

## 11. Data Sources

| Data | Source | Format | Used In |
|---|---|---|---|
| TCAS admission criteria | MYTCAS (mytcas.com) | CSV | PostgreSQL |
| มคอ.2 documents | University websites | PDF | Qdrant (RAG) |
| Faculty announcements | University websites | PDF | Qdrant (RAG) |
| Occupational standards | TPQI (tpqi.go.th) | PDF/Web | career_paths table |
| Job market data | DOE (doe.go.th) | PDF/Web | career_paths table |
| Job postings + salaries | Jobsdu, JobThai | Web scrape | career_paths table |
| Licensing requirements | Regulatory body websites | Web scrape | career_paths table |

**Target universities for initial data collection:**
- Chulalongkorn University
- Mahidol University
- Kasetsart University
- Thammasat University
- Srinakharinwirot University

---

## 12. Build Order (Phases)

```
Phase 1  → Infrastructure: Docker Compose, all services running, /health endpoint
Phase 2  → Model config + router + Ollama client
Phase 3  → PostgreSQL schema + migrations
Phase 4  → Auth: register, login, JWT middleware
Phase 5  → TCAS CSV ingestion + eligibility engine (SQL only, test with sample profiles)
Phase 6  → PDF parser + chunker + Qdrant ingestion + hybrid retrieval
Phase 7  → Career data collection + career_paths table + career engine
Phase 8  → Online runtime: intent router + orchestrator + memory layer
Phase 9  → Prompting system: master prompt + dynamic composer + behavior adaptation
Phase 10 → Frontend: chat UI + profile form + career view
Phase 11 → End-to-end testing with golden query set
```

**Rule: Do not start Phase 8 until Phases 5 and 6 are returning correct results.**
The orchestrator is useless without a working knowledge base.

---

## 13. Full POC Checklist

### Phase 1 — Infrastructure
- [ ] Git repo with monorepo structure
- [ ] `docker-compose.yml` with all 5 services
- [ ] All containers start and communicate
- [ ] Typhoon2 + nomic-embed-text + Llama3.1 pulled into Ollama
- [ ] FastAPI `/health` endpoint running

### Phase 2 — Model Config
- [ ] `MODEL_CONFIG` dict in `config.py`
- [ ] `model_router.py` — selects model given intent + query
- [ ] `ollama_client.py` — unified client for all Ollama calls
- [ ] Per-model temperature/top_p/max_tokens config
- [ ] Fallback trigger on primary model failure

### Phase 3 — Database Schema
- [ ] All tables defined in `schema.sql`
- [ ] Migrations run cleanly
- [ ] Foreign keys verified

### Phase 4 — Auth
- [ ] `POST /register` — bcrypt hash, store user
- [ ] `POST /login` — verify, return JWT
- [ ] JWT middleware protecting `/api/*`
- [ ] On login: fetch PostgreSQL memory → push to Redis
- [ ] On session end: summarize → write back to PostgreSQL

### Phase 5 — Structured Knowledge
- [ ] TCAS CSVs downloaded
- [ ] Ingestion script: clean → validate → PostgreSQL
- [ ] Deterministic eligibility SQL logic
- [ ] Tested against 10+ sample student profiles

### Phase 6 — RAG Pipeline
- [ ] PDF parser for มคอ.2 and announcement PDFs
- [ ] Hierarchical chunker with section-based segmentation
- [ ] Metadata tagging per chunk (university, major, round, year)
- [ ] Document hashing — skip unchanged PDFs
- [ ] Embeddings generated via nomic-embed-text
- [ ] Chunks + embeddings stored in Qdrant
- [ ] BM25 + dense retrieval implemented
- [ ] Cross-encoder reranking implemented
- [ ] Retrieval tested — correct chunks returned for sample queries

### Phase 7 — Career Layer
- [ ] Career data collected (TPQI, DOE, Jobsdu, JobThai)
- [ ] Static JSON mapping: major → careers → licenses → salary
- [ ] Loaded into `career_paths` table
- [ ] Career-major alignment scoring implemented
- [ ] Gap analysis logic implemented

### Phase 8 — Online Runtime
- [ ] Intent router classifying all 6 intent types correctly
- [ ] Major Recommendation Engine (rule-based, ranked output)
- [ ] Redis session memory: read + write per request
- [ ] PostgreSQL long-term memory: fetch on login, update on session end
- [ ] Memory injected into every prompt composition
- [ ] Request Orchestrator wiring all engines together
- [ ] Conversation summarizer (Typhoon2 → structured memory fields)

### Phase 9 — Prompting System
- [ ] Static Master Prompt written and frozen
- [ ] Dynamic Prompt Composer assembling all layers
- [ ] Behavior-based adaptation rules implemented
- [ ] Per-intent prompt templates for each model
- [ ] All 6 intent types tested end-to-end

### Phase 10 — Frontend
- [ ] React single page app
- [ ] Profile input form (GPAX, subjects, interests, target universities)
- [ ] Chat interface with session continuity
- [ ] Major comparison view
- [ ] Career path display

### Phase 11 — Testing
- [ ] Golden query set: 20-30 queries with expected answers
- [ ] Each intent type covered in golden set
- [ ] Eligibility engine: 10+ student profile tests
- [ ] RAG retrieval: verified correct chunks for preparation queries
- [ ] End-to-end: full conversation flow from login to recommendation to career guidance

### Data Collection Checklist
- [ ] MYTCAS TCAS CSVs
- [ ] มคอ.2 PDFs — all 5 target universities
- [ ] Faculty admission announcement PDFs
- [ ] TPQI occupational standards
- [ ] DOE job market reports
- [ ] Jobsdu / JobThai job postings
- [ ] Professional licensing requirements (medical, engineering, accounting, law)

---

## 14. Key Design Decisions & Rationale

| Decision | Rationale |
|---|---|
| Eligibility is always SQL, never LLM | LLMs hallucinate thresholds. This is the most critical correctness requirement. |
| PostgreSQL JSONB for user memory | Flexible schema without adding MongoDB. Already in the stack. |
| Qdrant for vectors | Docker-native, no managed service needed |
| Typhoon2 as primary model | Thai language capability is non-negotiable for Thai student users |
| Hybrid BM25 + dense retrieval | Dense alone misses exact numeric matches (score thresholds, subject codes) |
| Redis for session, PostgreSQL for long-term | Redis is fast for in-session reads; PostgreSQL persists across sessions |
| No CI/CD | POC scope. Not production. |
| No MongoDB | PostgreSQL JSONB covers flexible schema. Adding MongoDB adds a 6th service with no POC benefit. |
| Static JSON for career data (initial) | Fast to build. Load into PostgreSQL for querying. Upgrade to scraped data if time permits. |

---

## 15. Team Workflow (GitHub Issues + Git Standards)

> 4 people on this project. These rules exist so nobody blocks anyone else and the repo stays clean.

---

### 15.1 Team Roles & Phase Ownership

| Member | Primary Ownership |
|---|---|
| Member 1 | Phase 1 (Infra) + Phase 2 (Model Config) + Phase 9 (Prompting) |
| Member 2 | Phase 3 (Schema) + Phase 4 (Auth) + Phase 8 (Runtime/Orchestrator) |
| Member 3 | Phase 5 (TCAS Ingestion) + Phase 6 (RAG Pipeline) |
| Member 4 | Phase 7 (Career Layer) + Phase 10 (Frontend) + Phase 11 (Testing) |

> Adjust ownership based on your actual team strengths. This is a starting point.

---

### 15.2 GitHub Labels

Set these up once. Go to **Issues → Labels → Edit labels**, delete all defaults, create:

| Label | Color | Purpose |
|---|---|---|
| `phase-1` | `#0052cc` | Infrastructure |
| `phase-2` | `#0075ca` | Model Config |
| `phase-3` | `#0099ff` | Database Schema |
| `phase-4` | `#00b4d8` | Auth |
| `phase-5` | `#00c49f` | Structured Knowledge |
| `phase-6` | `#00b300` | RAG Pipeline |
| `phase-7` | `#80b300` | Career Layer |
| `phase-8` | `#e6b800` | Online Runtime |
| `phase-9` | `#ff9900` | Prompting System |
| `phase-10` | `#cc4400` | Frontend |
| `phase-11` | `#990000` | Testing |
| `backend` | `#f4a261` | Backend work |
| `frontend` | `#a8dadc` | Frontend work |
| `data` | `#52b788` | Data collection/ingestion |
| `blocked` | `#e63946` | Waiting on dependency |
| `bug` | `#9d0208` | Something broken |

---

### 15.3 Milestones

Create one milestone per phase in **Issues → Milestones → New milestone**.

Name format: `Phase N — <Description>`
Example: `Phase 1 — Infrastructure`

Set a target date for each based on your capstone deadline. Work backwards from demo day.

---

### 15.4 Creating Issues via GitHub CLI

Install GitHub CLI: https://cli.github.com

Authenticate:
```bash
gh auth login
```

Issue creation template:
```bash
gh issue create \
  --title "[Phase N] Short description of task" \
  --body "What needs to be done and acceptance criteria" \
  --label "phase-N,backend" \
  --milestone "Phase N — Description" \
  --assignee "github-username"
```

**Real examples from the checklist:**
```bash
# Phase 1
gh issue create \
  --title "[Phase 1] Write docker-compose.yml with all 5 services" \
  --body "Services: FastAPI, PostgreSQL, Qdrant, Ollama, Redis. All must start and communicate." \
  --label "phase-1,backend" \
  --milestone "Phase 1 — Infrastructure" \
  --assignee "member1-username"

gh issue create \
  --title "[Phase 1] Pull Ollama models on container start" \
  --body "Models: typhoon2-8b-instruct, nomic-embed-text, llama3.1:8b" \
  --label "phase-1,backend" \
  --milestone "Phase 1 — Infrastructure" \
  --assignee "member1-username"

# Phase 5
gh issue create \
  --title "[Phase 5] Build TCAS CSV ingestion script" \
  --body "Clean → validate → load into PostgreSQL. Source: MYTCAS. Must pass schema validation." \
  --label "phase-5,data,backend" \
  --milestone "Phase 5 — Structured Knowledge" \
  --assignee "member3-username"
```

---

### 15.5 Branch Naming Convention

Every issue gets its own branch. No direct commits to `main`.

Format:
```
phase-{N}/{short-description}
```

Examples:
```
phase-1/docker-compose-setup
phase-3/postgres-schema
phase-6/pdf-parser
phase-8/intent-router
phase-10/chat-ui
```

Create branch and link to issue:
```bash
# Create branch from main
git checkout main
git pull origin main
git checkout -b phase-1/docker-compose-setup

# After finishing work, push
git push origin phase-1/docker-compose-setup

# Open PR via CLI, reference the issue number
gh pr create \
  --title "[Phase 1] Docker Compose setup" \
  --body "Closes #1" \
  --base main
```

`Closes #N` in the PR body automatically closes the linked issue when the PR merges.

---

### 15.6 Commit Message Format

Keep it simple. One line, present tense, reference issue number.

Format:
```
[phase-N] short description (#issue-number)
```

Examples:
```
[phase-1] add docker-compose with all 5 services (#1)
[phase-3] add users and universities tables to schema (#8)
[phase-6] implement BM25 + dense retrieval pipeline (#19)
[phase-8] wire intent router to engine selector (#27)
```

---

### 15.7 Pull Request Rules

- **Never merge your own PR** — at least one other team member must review
- **PR must reference an issue** — use `Closes #N` in the body
- **PR must not break existing work** — run `docker compose up` and verify health endpoint still works before merging
- **Keep PRs small** — one issue per PR, not 5 issues in one PR
- **No direct commits to `main`** — always branch, always PR

PR body template:
```markdown
## What this does
Brief description of the change.

## Issue
Closes #N

## How to test
Steps to verify this works locally.

## Notes
Anything the reviewer should know.
```

---

### 15.8 Daily Workflow for Each Team Member

```
1. Pull latest main before starting
   git checkout main && git pull origin main

2. Check your assigned issues
   gh issue list --assignee @me

3. Create/switch to your branch
   git checkout -b phase-N/your-task

4. Work on your task

5. Commit with proper message
   git commit -m "[phase-N] description (#issue-number)"

6. Push and open PR
   git push origin phase-N/your-task
   gh pr create --title "..." --body "Closes #N" --base main

7. Request review from a teammate
   gh pr edit --add-reviewer teammate-username
```

---

### 15.9 When You're Blocked

1. Add `blocked` label to your issue
2. Comment on the issue explaining what you're blocked on
3. Tag the relevant person in the comment (`@username`)
4. Pick up another issue from your backlog while waiting — don't sit idle

---

### 15.10 Issue Status Convention

| Status | Meaning |
|---|---|
| Open, unassigned | Not started, needs owner |
| Open, assigned | In progress |
| Open + `blocked` label | Waiting on dependency |
| Closed via merged PR | Done |

Do not close issues manually. Close them by merging a PR with `Closes #N`.

---

## 16. Environment Variables (.env)

```env
# PostgreSQL
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=tcas_advisor
POSTGRES_USER=admin
POSTGRES_PASSWORD=password

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Qdrant
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# Ollama
OLLAMA_HOST=ollama
OLLAMA_PORT=11434

# Auth
JWT_SECRET=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRY_HOURS=24

# Models
PRIMARY_MODEL=typhoon2-8b-instruct
EMBEDDING_MODEL=nomic-embed-text
FALLBACK_MODEL=llama3.1:8b

# RAG
TOP_K_RETRIEVAL=5
RERANKER_TOP_K=3
```

---

---

*Last updated: based on full design discussion. Scope is POC/capstone. Revisit for production hardening if project is extended.*
*Project name: AcadeMong | Repo: Khronossu/AcadeMong | Team size: 4*