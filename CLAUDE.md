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

### 4.1 High-Level System Flow (2 AI Agents)

```
User (Web Frontend)
↓
Google OAuth Login
↓
FastAPI Backend
↓
Mode Selector (User explicitly chooses flow)
├── Flow A: Thai Career Dreamer (AI 1)
│       ↓
│   Semantic Career Matcher (Qdrant + JobsDB Catalog)
│       ↓
│   Typhoon2 generates Personalized Career Profile
│       ↓
│   Update user_career_profiles (PostgreSQL)
│
└── Flow B: TCAS RAG & Comparator (AI 2)
↓
Fetch Career Goal / GPAX from Profile
↓
Hybrid RAG (Qdrant PDF chunks + SQL Admission Projects)
↓
Typhoon2 provides factual eligibility & comparisons
↓
User saves preferred faculties (user_saved_majors)
```

### 4.2 Two Subsystems

**Offline Knowledge Engineering** (build once, update periodically)
- TCAS Deep Ingestion: CSV → PostgreSQL (Hierarchy: Round → Project → Subjects)
- PDF parsing + chunking + embedding → Qdrant
- Career Catalog Scraping (e.g., JobsDB) → PostgreSQL `career_catalog` + Qdrant Embeddings

**Online Adaptive Runtime** (handles every user request)
- Two distinct AI engines (`dreamer` and `tcas_rag`) with separated chat session memory to prevent context bleeding.

---

## 5. Database Schema

### PostgreSQL Tables

```sql
-- 1. CORE SYSTEM & ANALYTICS (Firebase Auth)
CREATE TABLE IF NOT EXISTS users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email         VARCHAR UNIQUE NOT NULL,
  firebase_uid  VARCHAR UNIQUE NOT NULL, 
  username      VARCHAR UNIQUE,          -- User-defined handle
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_login_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_profiles (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,
  first_name     VARCHAR,
  last_name      VARCHAR,
  date_of_birth  DATE,
  avatar_url     VARCHAR,
  address        VARCHAR,                 -- Home address details
  sub_district   VARCHAR,
  district       VARCHAR,
  province       VARCHAR,
  postal_code    VARCHAR,
  current_school VARCHAR,
  gpax           NUMERIC(3, 2)            -- Precision: 0.00 to 9.99, for eligibility accuracy
);

-- 2. AI 1: THAI CAREER DREAMER & CATALOG
CREATE TABLE IF NOT EXISTS user_career_profiles (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,
  personality_summary TEXT,
  strengths           JSONB,
  updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS industry_groups (
  id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR UNIQUE NOT NULL           -- e.g., 'งานไอที', 'งานวิศวกรรม'
);

CREATE TABLE IF NOT EXISTS career_catalog (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  industry_group_id      UUID REFERENCES industry_groups(id) ON DELETE SET NULL,
  title                  VARCHAR NOT NULL,
  overview_description   TEXT,
  avg_salary_thb         INT,
  active_job_openings    INT,            -- From real-time scraping
  responsibilities       JSONB,          -- Scraped from JobsDB
  education_requirements JSONB,
  top_skills             JSONB,
  last_scraped_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_recommended_careers (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
  career_id       UUID REFERENCES career_catalog(id) ON DELETE CASCADE,
  match_score     FLOAT,
  ai_reasoning    TEXT,
  created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, career_id)
);

-- 3. TCAS KNOWLEDGE GRAPH (Deep Structure)
CREATE TABLE IF NOT EXISTS universities (
  id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name     VARCHAR NOT NULL UNIQUE,
  location VARCHAR
);

CREATE TABLE IF NOT EXISTS faculties (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  university_id UUID REFERENCES universities(id) ON DELETE CASCADE,
  name          VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS majors (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  faculty_id UUID REFERENCES faculties(id) ON DELETE CASCADE,
  name       VARCHAR NOT NULL,
  field      VARCHAR                 -- e.g., 'Engineering', 'Health Science'
);

CREATE TABLE IF NOT EXISTS tcas_rounds (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  major_id     UUID REFERENCES majors(id) ON DELETE CASCADE,
  round_number INT NOT NULL,
  year         INT NOT NULL
);

CREATE TABLE IF NOT EXISTS admission_projects (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tcas_round_id       UUID REFERENCES tcas_rounds(id) ON DELETE CASCADE,
  project_name        VARCHAR NOT NULL, -- e.g., 'โครงการจุฬาฯ-ชนบท'
  seats               INT,
  gpax_min            NUMERIC(3, 2),    -- Precision: 0.00 to 9.99, no hallucination
  accepts_ged         BOOLEAN,
  specific_conditions TEXT,
  source_url          VARCHAR
);

CREATE TABLE IF NOT EXISTS subject_requirements (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  admission_project_id UUID REFERENCES admission_projects(id) ON DELETE CASCADE,
  subject              VARCHAR NOT NULL, -- e.g., 'TGAT', 'A-Level Math'
  min_score            FLOAT,
  weight_percent       FLOAT
);

-- 4. AI 2: TCAS RAG & COMPARATOR
CREATE TABLE IF NOT EXISTS user_saved_majors (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID REFERENCES users(id) ON DELETE CASCADE,
  major_id   UUID REFERENCES majors(id) ON DELETE CASCADE,
  notes      TEXT,                   -- Personal student annotations
  saved_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, major_id)
);
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

### 6.1 Mode Selector (Replaces Intent Router)
Instead of relying on LLM intent classification (which is prone to errors), the system uses explicit mode selection from the frontend UI:
- **Mode A (Career Dreamer):** Activates AI 1 to extract user strengths and search `career_catalog`.
- **Mode B (TCAS RAG):** Activates AI 2 to evaluate eligibility and compare faculties.

### 6.2 Eligibility Engine (SQL — No LLM)
Matches user's `USER_PROFILES.gpax` and subjects against the deep hierarchy: `tcas_rounds` → `admission_projects` → `subject_requirements`. Ensures 100% deterministic accuracy.

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

### 6.5 Semantic Career Matcher (Replaces Career Path Engine)
- **Input:** User conversation from AI 1.
- **Process:** LLM extracts JSON profile → Embeds profile → Vector search against `career_catalog` in Qdrant.
- **Output:** Writes Top-K matches to `user_recommended_careers` with `ai_reasoning`.

### 6.6 User Memory Layer
Chat history is strictly partitioned by `session_id` and `ai_mode` in `chat_messages`. This prevents AI 2 from hallucinating TCAS criteria based on a previous chat about career dreams.

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
        "model": "scb10x/llama3.1-typhoon2-8b-instruct",
        "intents": ["dreamer_chat", "tcas_chat"],
        "temperature": 0.3,
        "top_p": 0.9,
        "max_tokens": 1000
    },
    "rag": {
        "model": "scb10x/llama3.1-typhoon2-8b-instruct",
        "intents": ["tcas_rag_retrieval"],
        "temperature": 0.1,   # lower — strict grounding
        "top_p": 0.85,
        "max_tokens": 1500
    },
    "embedding": {
        "model": "nomic-embed-text"
    },
    "fallback": {
        "model": "llama3.1:8b",
        "trigger": "primary_model_failure"
    }
}
```

---

## 8. Auth

- **Provider:** Firebase Authentication (replaces custom JWT logic).
- **Methods:**
  1. Google OAuth (Primary)
  2. Email & Password (Secondary/Manual)
- **Flow:**
  1. Frontend (React) uses Firebase SDK to authenticate
  2. Frontend sends Firebase `idToken` to Backend via `Authorization: Bearer <token>` header
  3. Backend uses `firebase-admin` SDK to verify the token signature and expiry
  4. Backend maps `firebase_uid` → internal `users.id` from PostgreSQL
  5. On successful verification: fetch user profile from PostgreSQL → load into Redis session cache
  6. On session end: serialize user memory → write back to PostgreSQL
- **Rationale:** Production-grade security, easy user management, no password hashing burden, instant access to Google profiles without manual OAuth boilerplate.

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
docker exec -it ollama ollama pull scb10x/llama3.1-typhoon2-8b-instruct
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
│   │   ├── mode_selector.py           # Explicit UI-driven mode: Flow A or Flow B
│   │   ├── eligibility_engine.py      # SQL-only eligibility matching
│   │   ├── recommendation_engine.py   # Rule-based major recommendation
│   │   ├── rag_engine.py              # Hybrid retrieval + reranking
│   │   ├── career_matcher.py          # Semantic career matching (Qdrant)
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
| Occupational standards | TPQI (tpqi.go.th) | PDF/Web | career_catalog + Qdrant embeddings |
| Job market data | DOE (doe.go.th) | PDF/Web | career_catalog + Qdrant embeddings |
| Job postings + salaries | Jobsdu, JobThai | Web scrape | career_catalog + Qdrant embeddings |
| Licensing requirements | Regulatory body websites | Web scrape | career_catalog + Qdrant embeddings |

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
Phase 4  → Auth: Firebase authentication, idToken verification, user storage
Phase 5  → TCAS CSV ingestion + eligibility engine (SQL only, test with sample profiles)
Phase 6  → PDF parser + chunker + Qdrant ingestion + hybrid retrieval
Phase 7  → Career data collection + career_catalog table + semantic career matcher
Phase 8  → Online runtime: Mode Selector (explicit UI routing) + orchestrator + memory layer
Phase 9  → Prompting system: master prompt + dynamic composer + behavior adaptation
Phase 10 → Frontend: chat UI (Flow A/B selector) + profile form + career view
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

### Phase 4 — Auth (Firebase)
- [ ] Firebase project created and credentials configured in `.env`
- [ ] `firebase-admin` SDK initialized in `config.py`
- [ ] `POST /register` — accept email/password or direct OAuth, store `firebase_uid` + `username` in PostgreSQL
- [ ] `POST /login` — accept Firebase `idToken`, verify signature, return session cookie or token
- [ ] Firebase token verification middleware protecting `/api/*`
- [ ] On login: fetch user profile from PostgreSQL → cache in Redis session
- [ ] On session end: summarize memory → write back to PostgreSQL `user_career_profiles` and `user_profiles`
- [ ] Test: sign up via Google OAuth → login → verify JWT-equivalent token issued

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
- [ ] Career entries loaded into `career_catalog` with `industry_group_id` links
- [ ] Career title embeddings generated and stored in Qdrant under "careers" collection
- [ ] Career-to-major mapping logic implemented
- [ ] Semantic career matching tested with sample user profiles

### Phase 8 — Online Runtime (Orchestrator & Mode Selector)
- [ ] Mode Selector properly routing to Flow A or Flow B based on Frontend UI selection
- [ ] Flow A (Career Dreamer): Extract user strengths → call Semantic Career Matcher → vectorize → search Qdrant → write to `user_recommended_careers`
- [ ] Flow B (TCAS RAG): Fetch GPAX/subjects → run Eligibility Engine → hybrid RAG retrieval → pass to Typhoon2 → return structured comparison
- [ ] Major Recommendation Engine (rule-based, ranked output with fit scores)
- [ ] Redis session memory: read on request start, write after AI response
- [ ] PostgreSQL long-term memory: fetch on login, update on session end via conversation summarizer
- [ ] Memory injected into every prompt composition (user profile, saved majors, career interests)
- [ ] Request Orchestrator wiring Mode Selector → engines → memory layer → prompt composer
- [ ] Conversation summarizer: Typhoon2 extracts structured fields → update PostgreSQL

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
| GPAX precision: NUMERIC(3, 2) | Fixes FLOAT rounding errors (e.g., 3.99 vs 4.00). Eligibility logic demands exact matches. No ambiguity. |
| Mode Selector (explicit UI routing) | Avoids LLM intent classification errors. User explicitly chooses Flow A (Career) or Flow B (TCAS). Clear, deterministic, testable. |
| Firebase Authentication | Production auth, no password hashing burden, easy Google OAuth integration, session token verification is fast. |
| Two separate AI agents (Dreamer + RAG) | Prevents context bleeding. Career dreams don't confuse TCAS criteria engine. Session memory partitioned by `ai_mode`. |
| PostgreSQL JSONB for user memory | Flexible schema without adding MongoDB. Already in the stack. Supports arbitrary profile extensions. |
| Qdrant for vectors | Docker-native, no managed service needed. Metadata filtering for efficient retrieval. |
| Typhoon2 as primary model | Thai language capability is non-negotiable for Thai student users. Local, no API cost. |
| Hybrid BM25 + dense retrieval | Dense alone misses exact numeric matches (score thresholds, subject codes). Hybrid ensures both semantic and lexical correctness. |
| Redis for session, PostgreSQL for long-term | Redis is fast for in-session reads; PostgreSQL persists across sessions and supports complex queries. |
| industry_groups as master table | Enables career categorization reuse across job market data sources. Normalized structure avoids duplication. |
| Semantic Career Matcher (Qdrant search) | Replaces hard-coded mapping. Scalable to new careers via embeddings. JobsDB catalog embedded + indexed. |
| No CI/CD | POC scope. Not production. Team is small (4). Manual PR review sufficient. |
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
phase-8/mode-selector-orchestrator
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
[phase-8] wire mode selector to engine orchestrator (#27)
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

# Firebase Auth
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_PRIVATE_KEY=your-firebase-private-key
FIREBASE_CLIENT_EMAIL=your-firebase-client-email

# Models
PRIMARY_MODEL=scb10x/llama3.1-typhoon2-8b-instruct
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