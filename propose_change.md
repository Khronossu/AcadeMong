# Proposed Changes — Data & RAG Scope Rework

> **Status**: Draft for team discussion.
> **Author**: Purin.
> **Scope**: Phase 5 (Structured Knowledge) and Phase 6 (RAG Pipeline). Adjacent impact on Phase 3 schema, Phase 7 Career, Phase 8 Orchestrator.
> **Trigger**: Comparing `user_interaction_and_tcas_guide.md` against the current schema and Phase 5/6 plan surfaced real gaps — several of which the current plan cannot serve. This document records what we're changing, what we're explicitly **not** doing, and why.

---

## 1. Problem Statement

The interaction guide defines four user modes (Portfolio Builder, Score Matcher, Last-Minute Strategist, Undecided Explorer) and ten student stereotypes. The current Phase 3 schema and Phase 5/6 data plan were designed before that guide existed. The mismatch:

- **`user_profiles.gpax` is the only score field** → the Score Matcher mode cannot compare user TGAT/TPAT/A-Level scores against `subject_requirements.min_score`. The eligibility engine (#25) has nothing to match on.
- **`subject_requirements.min_score` stores rubric floors, not historical cutoffs** → no "safety margin" calculation possible.
- **Round 1 (Portfolio) and Round 2 (Quota) have no structured representation** → `admission_projects.specific_conditions` is free-text. Any R1/R2 answer would be LLM-generated, which violates the core "never hallucinate eligibility" rule.
- **มคอ.2 documents are curriculum, not admission criteria** — and are frequently 5–20 years stale. Using them as RAG sources for admission questions is not just unhelpful, it's misleading.
- **No major↔career link** → the guide repeatedly says "connect the major to a tangible career path" but the schema has no join between `majors` and `career_catalog`.

These are not small issues. They determine whether Phase 5/6 produces a useful product or a demo.

---

## 2. Hard Constraints We're Working Around

| Constraint | Implication |
|---|---|
| **Capstone timeline (weeks, 4 people)** | Cannot scrape 5 universities × ~100 programs × per-program Round 1/2 rubrics. Must pick what's achievable. |
| **TCAS R1/R2 data chaos** | Rubrics scattered per university, per faculty, per program. Some published, most not. One major often has 5–10 sub-programs with different R1/R2 criteria (e.g. Chula Engineering: Regular / Inter / ChPE / BSAC / CEDT / etc.). |
| **มคอ.2 staleness** | Revised every 4–5 years by curriculum committee; some published documents on university sites haven't been updated in 15–20 years. The document often does not reflect what's currently taught, let alone how students are admitted. |
| **Never hallucinate eligibility** (CLAUDE.md §14) | If we don't have authoritative data, we must refuse to answer rather than guess. |

These constraints don't just shrink ambition — they reshape the schema and RAG strategy.

---

## 3. Scope Decisions

| Item | Decision | Rationale |
|---|---|---|
| **TCAS Round 3 (Admission)** | ✅ **Primary focus.** Full data collection, full eligibility engine, full RAG context. | Data is centrally available from MYTCAS. Test-score-driven, so structured and matchable. Covers ~70% of applicants. |
| **TCAS Round 4 (Direct Admission)** | 🟡 **Stretch.** Schema supports it. Remaining-seats data via scrape only if time permits. | Data is public on MYTCAS during Round 4 window. Scraper is cheap but adds maintenance burden. |
| **TCAS Round 1 (Portfolio)** | 🔴 **Placeholder only.** Schema stays. Tables stay empty. System returns *"Round 1 criteria vary per program and are not available in our data. Please contact the faculty admissions office directly."* | Rubrics are scattered, program-specific, often secret. Curating this is multiple person-months. Out of capstone scope. |
| **TCAS Round 2 (Quota)** | 🔴 **Placeholder only.** Same treatment as Round 1. | Quota eligibility requires per-project geographic/school partnership enumeration. Same data problem. |
| **มคอ.2 documents** | ✅ **Keep in RAG with mandatory year citation.** Tagged `authority_level='curriculum_only'`, `doc_type='mko2'`. Retrieved ONLY for curriculum questions ("what will I study?"), NEVER for admission questions ("can I get in?"). **Every answer grounded in a มคอ.2 chunk must cite the publication year inline** so the user sees "this is from the 20XX curriculum document." | Keeps the "what's the curriculum" use case. The year citation is the mitigation for staleness — the user decides how much to trust it based on the age, rather than the system hiding the age. **Decided — see §9 Q1.** |
| **Annual admission announcements (ประกาศรับสมัคร)** | ✅ **New primary RAG source.** Yearly documents with authoritative admission info. Tagged `doc_type='announcement'`, `authority_level='authoritative'`, `year=YYYY`. | These ARE updated yearly. They contain actual Round 3 criteria, subject weights, dates. Should be the backbone of RAG, not มคอ.2. |
| **Portfolio rubrics** | 🔴 **Deferred.** | Per-program, often confidential. Same as R1 problem. |
| **Cutoff-score history** | ✅ **New data source.** From MYTCAS annual reports and university-published stats, where available. | Enables the "safety margin" calculation the Score Matcher mode needs. Without this, we can only say "you meet the minimum" — not "you're competitive." |

**Key mental model:** the system's answer quality is bounded by its data. We're choosing to do Round 3 thoroughly rather than all four rounds badly.

---

## 4. Schema Changes

### 4.1 NEW: `user_test_scores`

```sql
CREATE TABLE IF NOT EXISTS user_test_scores (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    test_code   VARCHAR(30) NOT NULL,  -- 'TGAT1', 'TGAT2', 'TGAT3', 'TPAT1'..'TPAT5',
                                       -- 'A_LEVEL_MATH1', 'A_LEVEL_PHYSICS', etc.
    score       NUMERIC(6,2) NOT NULL,
    exam_year   INTEGER NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, test_code, exam_year)
);

CREATE INDEX IF NOT EXISTS idx_user_test_scores_user ON user_test_scores(user_id);
```

**Why:** The Score Matcher mode needs to match user scores per subject against `subject_requirements.min_score`. A denormalized column-per-test approach (e.g. `user_profiles.tgat1`, `tgat2`, ...) would explode to ~20 columns, break every time TCAS adds a test, and make "show me all my scores" queries awkward. Long format (one row per score) is the standard relational answer.

**Why NUMERIC(6,2):** TGAT max is 100; A-Level max is 100. NUMERIC avoids float rounding in eligibility comparisons.

**Why `exam_year`:** students sometimes retake and hold scores from multiple years. The eligibility engine should use the best (or most recent, depending on rule) — we need the year to decide.

**`test_code` as string, not enum:** Postgres enums require a migration to add new test codes. TCAS changes test names regularly (TGAT/TPAT was introduced in 2023, replacing GAT/PAT). A lookup table or app-side validation is more flexible. Open question: do we need a `test_catalog` table? Leaning no — string with app-layer validation is cheaper for capstone.

### 4.2 NEW: `historical_cutoffs`

```sql
CREATE TABLE IF NOT EXISTS historical_cutoffs (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    admission_project_id UUID REFERENCES admission_projects(id) ON DELETE CASCADE,
    year                 INTEGER NOT NULL,
    score_type           VARCHAR(30) NOT NULL,  -- 'composite_weighted' | 'TGAT_total' |
                                                -- 'TPAT1' | 'A_LEVEL_MATH1' | etc.
                                                -- Identifies WHICH score the min/max/median refer to.
    min_admitted_score   NUMERIC(6,2),
    max_admitted_score   NUMERIC(6,2),
    median_score         NUMERIC(6,2),
    applicants_count     INTEGER,
    accepted_count       INTEGER,
    source_url           TEXT,
    -- SCD Type 2: preserve full history of restatements
    effective_from       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    effective_to         TIMESTAMP WITH TIME ZONE,  -- NULL = still current
    is_current           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Enforce: at most one CURRENT row per (project, year, score_type).
-- Superseded rows (is_current=FALSE) are unconstrained so history can accumulate.
CREATE UNIQUE INDEX IF NOT EXISTS uq_historical_cutoffs_current
    ON historical_cutoffs(admission_project_id, year, score_type)
    WHERE is_current;
```

**Why `score_type`:** Round 3 admissions use per-project composite scores computed from multiple tests with different weights. "Minimum admitted score = 72.5" is meaningless without saying *72.5 of what*. A project may publish both the composite cutoff AND per-subject sub-cutoffs — those are different rows with different `score_type` values.

**Why SCD Type 2 (not a natural `year` key alone):** `year` time-stamps *which admission cycle* a cutoff belongs to; it does not time-stamp *when we observed the value*. Universities restate cutoff statistics — preliminary numbers published shortly after Round 3 closes are often revised later (waitlist activity, appeals, late reporting). Without version history, re-ingesting overwrites the original observation and we lose audit trail. SCD Type 2 keeps both versions:

- Current reads filter `WHERE is_current`.
- Audit / "what did we tell students in June 2025?" reads filter `WHERE effective_from <= $1 AND (effective_to IS NULL OR effective_to > $1)`.

**Ingestion flow** (when a new value arrives for an existing (`project`, `year`, `score_type`)):
```sql
UPDATE historical_cutoffs
   SET is_current = FALSE, effective_to = CURRENT_TIMESTAMP
 WHERE admission_project_id = $1 AND year = $2 AND score_type = $3 AND is_current;

INSERT INTO historical_cutoffs (admission_project_id, year, score_type, ...)
VALUES ($1, $2, $3, ...);  -- is_current defaults TRUE, effective_from defaults now()
```
Wrap both in a transaction to keep the partial-unique-index invariant safe.

**Why:** The guide's Score Matcher mode says *"Provide the minimum, maximum, and safe-margin scores for their target majors."* That is empirical cutoff data, not rubric minimums. `subject_requirements.min_score` answers *"you're eligible to apply"*; `historical_cutoffs` answers *"you're likely to be accepted."* These are different questions.

**Why separate from `admission_projects`:** an admission project is a current-year entity; cutoffs are a history. Putting them in the same row would require widening the current table every year. A child table with `year` is cleaner and enables "show me 5-year cutoff trend" queries trivially.

**Limitation to document:** cutoff data exists primarily for Round 3 (MYTCAS publishes it). Round 1/2 have it sparsely, Round 4 not at all. This table will be sparsely populated outside Round 3 — that's fine, it's the honest state of the data.

### 4.3 EXTEND: `admission_projects`

Add two fields:

```sql
ALTER TABLE admission_projects ADD COLUMN round_type VARCHAR(30);
-- values: 'portfolio' (R1), 'quota' (R2), 'admission' (R3), 'direct' (R4)
-- redundant with tcas_rounds.round_number but gives semantic name for filtering

ALTER TABLE admission_projects ADD COLUMN round_metadata JSONB;
-- flexible structured data that varies per round:
-- R1 example: {"required_portfolio_items": ["certificates", "essay"], "min_extracurricular_count": 3}
-- R2 example: {"eligible_provinces": ["BKK", "CM"], "partner_schools": [...]}
-- R3 example: {"score_weights": {"TGAT1": 0.2, "TGAT2": 0.3, ...}}
-- R4 example: {"application_url": "...", "rolling_deadline": true}
-- R1/R2 will be mostly empty or null during capstone — that's expected.
```

**Why JSONB over typed columns:** the fields that matter per round are fundamentally different (geographic codes for R2, portfolio items for R1, score weights for R3). Adding per-round tables is cleaner in theory but eight-times the ingestion work. JSONB gives us per-round flexibility with one column; we can later promote to typed columns if a field proves stable and universal.

**Why `round_type` as a name alongside the existing `round_number`:** app code filters by semantic name ("get all Portfolio projects") more often than by number. Costs one VARCHAR, saves join to `tcas_rounds` on every query.

**Consistency guard (CHECK constraint).** `round_type` and the linked `tcas_rounds.round_number` carry the same information in two places. Ingestion bugs could easily desync them (e.g. `round_type='admission'` on a `round_number=1` project). Add a CHECK that forces the two to agree:

```sql
ALTER TABLE admission_projects
ADD CONSTRAINT admission_projects_round_type_matches_round_number
CHECK (
    round_type IS NULL
    OR (round_type = 'portfolio'  AND EXISTS (SELECT 1 FROM tcas_rounds r WHERE r.id = tcas_round_id AND r.round_number = 1))
    OR (round_type = 'quota'      AND EXISTS (SELECT 1 FROM tcas_rounds r WHERE r.id = tcas_round_id AND r.round_number = 2))
    OR (round_type = 'admission'  AND EXISTS (SELECT 1 FROM tcas_rounds r WHERE r.id = tcas_round_id AND r.round_number = 3))
    OR (round_type = 'direct'     AND EXISTS (SELECT 1 FROM tcas_rounds r WHERE r.id = tcas_round_id AND r.round_number = 4))
);
```

> **Implementation note:** Postgres **unconditionally forbids subqueries inside CHECK constraints** (all versions — the SQL above will always fail to create). The CHECK syntax is shown to document the *intent*; the actual implementation must be a `BEFORE INSERT/UPDATE` trigger on `admission_projects` that performs the lookup into `tcas_rounds` and raises on mismatch. Do not spend time trying to make the CHECK form work. The *requirement* is that the two fields cannot desync; the mechanism is the trigger.

**Weight authority — JSONB vs. `subject_requirements`.** Two places now hold score weights: `round_metadata.score_weights` (JSONB, raw from the announcement PDF) and `subject_requirements.weight_percent` (normalized, per-row). These are **not redundant**; they have different roles:

| Field | Role | Source of truth for |
|---|---|---|
| `round_metadata.score_weights` (JSONB) | Raw parsed intermediate from announcement PDF table extraction. Preserves the document's exact shape for debugging/audit. | Nothing the app queries directly. |
| `subject_requirements.weight_percent` | Normalized, query-shaped. One row per subject per project. | **All eligibility and score-matching queries.** |

The ingestion flow is: parse announcement PDF → write raw JSONB to `round_metadata.score_weights` → normalize into `subject_requirements` rows. If the two ever disagree, `subject_requirements` wins and the JSONB is considered stale parse output. Nothing in the runtime reads the JSONB for computation.

### 4.4 DEFERRED (not building now): `major_career_mapping`

My earlier suggestion was a dedicated `major_career_mapping` table with hand-curated `directness` labels (direct/common/possible). **Withdrawing this.**

**Why:** the mapping for 500+ majors × dozens of careers is person-months of manual work, and the labels are judgment calls that teammates will disagree on. Phase 7's JobsDB scrape already collects `education_requirements` per career (which majors typically fill these jobs). The mapping can be derived as a SQL query or materialized view, not a maintained table.

**Replacement plan (Phase 7):**

```sql
-- After Phase 7 has populated career_catalog with education_requirements,
-- derive the mapping. education_requirements.majors is a JSONB array of
-- major-name strings (e.g. ["Computer Engineering", "Software Engineering"]).
-- JSONB's `?` operator checks object-KEY containment, not array-VALUE
-- containment — so we use `@> to_jsonb(m.name)` to test array membership.
CREATE MATERIALIZED VIEW major_career_derived AS
SELECT
    m.id   AS major_id,
    c.id   AS career_id,
    TRUE   AS is_direct_fit
FROM majors m
JOIN career_catalog c
  ON (c.education_requirements -> 'majors') @> to_jsonb(m.name);
```

The `JOIN` (not `CROSS JOIN`) keeps the result small — only (major, career) pairs that actually match are emitted, which is the useful shape for the app. The `is_direct_fit` column is a placeholder for future extension (e.g. weighted match scores); for now it's always `TRUE` because every row represents a confirmed match.

**Refresh on career data reload — use `CONCURRENTLY`:**
```sql
-- Requires a UNIQUE index on the view (below) — CONCURRENTLY won't work without it.
CREATE UNIQUE INDEX IF NOT EXISTS uq_major_career_derived
    ON major_career_derived(major_id, career_id);

REFRESH MATERIALIZED VIEW CONCURRENTLY major_career_derived;
```

Without `CONCURRENTLY`, `REFRESH` takes an `ACCESS EXCLUSIVE` lock and blocks all reads for the refresh duration. Since Phase 7 career scrapes will run while the system is live, a non-concurrent refresh is effectively a brief outage. The `CONCURRENTLY` variant holds only a lighter lock and lets reads continue.

### 4.5 DEFERRED: `admission_project_quotas`

A table for Round 2 quota eligibility. Schema stub only — not populated during capstone.

```sql
-- Stub only; left empty until R2 data collection is feasible.
-- Intentionally NOT created in schema.sql for now — we'd rather have
-- no table than an empty table that implies completeness.
```

**Why not create the empty table:** an empty table signals "feature exists, no data yet." For a capstone demo, that's misleading. Better to omit and say "R2 not supported in this version."

---

## 5. Data Collection Changes

### 5.1 PRIMARY — MYTCAS annual Round 3 data (already planned, #23)

CSVs of all Round 3 admission projects across the 5 target universities, plus cutoff statistics.

**Changes to #23:**
- Scope explicitly limited to Round 3 (was ambiguous before).
- Add "download annual cutoff reports" as part of the same ticket — same source, same cadence.
- Collect data for the last 3 years (2024–2026) to support 3-year cutoff trend.

### 5.2 NEW PRIMARY — Annual admission announcement PDFs (ประกาศรับสมัคร)

**What:** Per-faculty or per-project admission announcements published yearly by each university.

**Why this is the biggest change:** these are the documents that actually tell students *"to apply to this project you need TGAT1 ≥ X, TPAT3 ≥ Y, with weights A/B/C."* They are timestamped, authoritative, and updated every year. **They, not มคอ.2, should be the backbone of Phase 6 RAG.**

**New issue to open:** `[Phase 6] Collect annual admission announcement PDFs for 5 target universities, Round 3`. Children of #27.

### 5.3 SECONDARY — มคอ.2 curriculum PDFs

**Keep with mandatory year citation.** Decision resolved in §9 Q1.

- Tag every chunk: `doc_type='mko2'`, `authority_level='curriculum_only'`, `year=<publication year>`, `possibly_stale=true`.
- RAG router filters these OUT for admission-intent queries (§6.2).
- Retrieved only for curriculum-intent queries ("what courses will I take in Computer Engineering at Chula?").
- **Year citation is not optional.** Every LLM response grounded in a มคอ.2 chunk must surface the publication year inline — e.g. *"According to the Computer Engineering curriculum document published in 2018 ..."* The user sees the age and decides how much weight to give it. This is preferable to silently serving stale data.
- **Prompt-level enforcement:** the Flow B prompt template must include an instruction like *"When citing curriculum_only sources, always include the source publication year. If the year is older than 5 years, add a note: 'This is older curriculum reference; current courses may differ.'"* The model's compliance with this becomes part of Phase 11 test acceptance.

### 5.4 DEFERRED sources

- Portfolio rubrics (R1)
- Quota lists (R2)
- Round 4 remaining-seats dashboard
- Interview example corpora

These can be added post-capstone without schema changes, since R1/R2 fields are JSONB-flexible.

---

## 6. RAG Pipeline Changes

### 6.1 Document metadata — new required fields

Every chunk stored in Qdrant must have these metadata fields:

```python
{
  "university": str,
  "faculty": str | None,
  "major": str | None,
  "round_number": int | None,
  "year": int,                  # publication year, NOT TCAS admission year
  "doc_type": str,              # 'announcement' | 'mko2' | 'cutoff_report' | ...
  "authority_level": str,       # 'authoritative' | 'curriculum_only' | 'historical'
  "source_url": str,
  "doc_hash": str               # from Phase 6 hashing step
}
```

**Why `authority_level`:** lets the retrieval layer make routing decisions based on what the query is asking. A "can I get in?" query filters to `authority_level='authoritative'`. A "what will I study?" query allows `curriculum_only`.

### 6.2 Retrieval routing (new — not in current Phase 6 plan)

Before retrieving, classify query intent (lightweight — keyword rules or short LLM classification):

| Intent | Qdrant filter |
|---|---|
| **Admission question** ("can I get in?", "what's the cutoff?") | `doc_type='announcement' OR 'cutoff_report'`, `authority_level='authoritative'`, `year >= current - 1` |
| **Curriculum question** ("what will I study?", "what courses?") | any `doc_type`, but prefer `announcement` over `mko2` if both match |
| **Portfolio/prep question** | `doc_type='announcement' OR 'prep_guide'` |

**Never**: retrieve `authority_level='curriculum_only'` for an admission question. The system must refuse to cite curriculum docs as admission evidence.

**Ambiguous / unclassifiable queries — safe default.** The classifier will sometimes fail to confidently assign an intent (short query, mixed wording, user asking in unusual terms). In that case we must not silently widen retrieval to everything, because that lets curriculum docs leak into admission answers.

**Default on ambiguity:** treat the query as admission-intent and apply the admission filter (`authority_level='authoritative'`, exclude `curriculum_only`). Rationale: admission is the higher-stakes failure mode — hallucinating a cutoff is worse than missing a curriculum detail. Users asking curriculum questions whose classifier confidence is low will get a narrower result set; they can rephrase. Users asking admission questions never see curriculum content masquerading as authoritative.

**Implementation:** classifier returns `(intent, confidence)`. If `confidence < threshold`, force `intent='admission'`. Log these events for later tuning.

### 6.3 Year-scoped retrieval with recency preference

For admission queries, hard-filter `year >= current_tcas_year - 1`. Within that window, boost the most recent year in reranking.

**Why not a harder recency filter:** edge case — announcements for TCAS 2026 may not all be published yet during a 2026 applicant's prep in 2025. Need a 1-year grace window.

### 6.4 Table extraction (new)

**The highest-value data in announcement PDFs is in tables** (subject weight tables, cutoff tables). Generic PDF parsers flatten these into unreadable text.

**Plan:** use Camelot or pdfplumber's table-detection to extract tables directly. Two uses:
1. Cutoff tables → parse and load into `historical_cutoffs` (structured, not RAG).
2. Subject-weight tables → parse into `admission_projects.round_metadata.score_weights` JSONB.

What remains in RAG text is prose explanation.

### 6.5 Thai tokenization before chunking

Thai has no spaces between words. Naive character-based chunking splits words mid-syllable, degrading embedding quality.

**Plan:** use PyThaiNLP's `word_tokenize` to establish word boundaries before chunking. Chunk to a target token count rather than character count.

### 6.6 Document hashing — adapted for unreliable timestamps

The original Phase 6 plan: hash PDF content to skip unchanged documents. This still applies, but for มคอ.2 specifically we cannot trust publication dates. Store the hash *and* the last-seen date separately. If a university site shows the same hash for 3 years running, tag those chunks with `possibly_stale=true` regardless of the document's stated year.

---

## 7. Mode Selector Reconsidered

CLAUDE.md §6.1 defines two top-level modes: Career Dreamer (Flow A) and TCAS RAG (Flow B). The guide §4 defines four user interaction modes.

**Proposal:** keep the 2-flow top-level split (simple, clean UI, prevents context bleed as CLAUDE.md §14 intends). Within Flow B, detect the four sub-modes from the user's message content and switch prompt templates.

| Top-level flow | Sub-mode detection | Prompt template |
|---|---|---|
| Flow A (Career Dreamer) | single mode | `prompts/dreamer.txt` |
| Flow B (TCAS RAG) | Portfolio Builder (R1 keywords) | `prompts/tcas_portfolio.txt` |
| Flow B | Score Matcher (score/GPAX keywords, R3) | `prompts/tcas_score.txt` |
| Flow B | Last-Minute Strategist (R4, deadline keywords) | `prompts/tcas_lastminute.txt` |
| Flow B | Undecided Explorer (vague keywords) | `prompts/tcas_explorer.txt` |

**Caveat:** Portfolio Builder and Last-Minute sub-modes will be degraded by the R1/R4 data gaps. The prompts should explicitly say *"I have limited data on Round 1 — here's what I can confirm from current TCAS data, and what you should verify with the faculty directly."*

---

## 8. What We're Explicitly NOT Doing

Making these refusals explicit is part of the contract with users.

- ❌ **No Round 1 Portfolio rubric advice** — "I don't have structured data on Round 1 rubrics. These vary per program and are best confirmed with the faculty admissions office directly."
- ❌ **No Round 2 Quota eligibility check** — "Round 2 Quota eligibility depends on specific geographic and school-partnership criteria that aren't in our data. Please check the university's Round 2 announcement directly."
- ❌ **No live Round 4 remaining-seats lookup** — unless stretch scope is taken.
- ❌ **No citing of มคอ.2 as admission criteria** — enforced by RAG router filter.
- ❌ **No hand-curated major↔career mapping** — derived from Phase 7 scraped data instead.
- ❌ **No guaranteeing mkอ.2 content reflects current teaching** — all มคอ.2-sourced answers carry a staleness disclaimer.

---

## 9. Open Questions / Points for Team Debate

### Q1. Should มคอ.2 be dropped from RAG entirely?

**✅ RESOLVED: Keep with mandatory year citation.**

**Rationale:** call is roughly 50/50 on value vs. staleness risk. Keeping มคอ.2 is justified as long as the staleness is visible to the user — which means every answer grounded in a มคอ.2 chunk must cite the source's publication year inline (e.g. *"According to the 2018 curriculum document ..."*). The user, seeing the age, decides how much to trust it; the system stops pretending the content is current.

**Enforcement:** prompt-level requirement (always cite year) + Phase 11 acceptance test (a query expecting a มคอ.2-sourced answer fails the test if the year isn't surfaced).

**What this does NOT change:**
- มคอ.2 is still filtered OUT for admission-intent queries by §6.2 routing.
- Staleness tagging (`possibly_stale=true`) still applied.

### Q2. Round 4 stretch — worth scraping or skip entirely?

MYTCAS Round 4 dashboard updates daily during the Round 4 window (a few weeks per year). A scraper is ~1 day of work, but it needs ongoing maintenance across TCAS site redesigns. Value: enables the "Last-Minute Strategist" mode to actually work.

**My lean:** build it only if Phases 5/6 finish ahead of schedule. Otherwise document the absence and move on.

### Q3. Cutoff data source — MYTCAS only or also university-published?

MYTCAS centralizes Round 3 cutoffs but at a summarized level. Some universities publish more detailed breakdowns (e.g. "of 200 admitted, 5th percentile was X, 95th was Y"). Collecting both is more data work.

**My lean:** MYTCAS only for capstone. University-specific as a stretch.

### Q4. `test_catalog` lookup table — yes or no?

Alternatives:
- **A:** hand-validate test codes in app (fast; breaks silently if we typo).
- **B:** add `test_catalog` table with all valid codes (catches errors, one more table).
- **C:** Postgres CHECK constraint with enumerated values (fast; requires migration to add codes).

**My lean:** A for capstone. B if we later need i18n labels ("English Communication" in English/Thai) for the UI.

### Q5. How do we handle users who retake tests? — **Phase 5 blocker**

`user_test_scores` allows multiple rows per user per test code across years. Before the eligibility engine ships, this must be settled — the engine's SELECT cannot remain ambiguous about which row to read.

**Decision required before Phase 5 coding starts.** Options:
- Use only the most recent score (simple, correct for the common case).
- Use the highest score (what students hope for, not always what admission rules allow).
- Let the user pick which score to apply (transparent, more UI work).

**My lean — and proposed default for Phase 5:** most recent. Eligibility engine's SQL uses `ORDER BY exam_year DESC LIMIT 1`. A "pin specific year" UI option can come later; it does not block the engine.

**Why this is a blocker, not an open debate:** #25 (eligibility engine) cannot be merged without a decision — any SELECT will make one of these choices implicitly. Better to make it explicitly, document it, and test against it.

### Q6. How aggressive should the "insufficient data" response be?

When a user asks about R1 and we refuse to answer from data, what do we say?

- **Terse:** "Round 1 criteria aren't in our data."
- **Helpful:** "Round 1 criteria aren't in our data, but here's what's generally true about Round 1 [...from a small static knowledge base...]. For program-specific rubrics, please contact [faculty admissions URL]."

The terse version is safer but frustrates users. The helpful version needs a small curated static knowledge base (outside RAG) for general-TCAS-knowledge answers, otherwise the model will invent.

**My lean:** helpful, with a small static knowledge base covering the info in `user_interaction_and_tcas_guide.md` §1–2 (round descriptions, test descriptions). This is a tiny curated corpus — a few hundred lines of reviewed Thai prose. Feed it into the prompt as static context for Flow B, not RAG.

---

## 10. Suggested Issue Changes

### Existing issues to update

- **#23** *"Download TCAS CSVs from MYTCAS"* → retitle and expand scope: *"Download TCAS Round 3 CSVs and annual cutoff reports from MYTCAS (2024–2026)."*
- **#24** *"Build TCAS CSV ingestion script"* → ingests into 3 more tables now (`user_test_scores` is user-facing; `historical_cutoffs`; extended `admission_projects.round_metadata`).
- **#25** *"Build deterministic eligibility engine"* → explicit note: Round 3 only. R1/R2 return "data unavailable."
- **#26** *"Test eligibility engine against 10+ sample profiles"* → profiles now include realistic per-test score sets, not just GPAX.
- **#27** *"Build PDF parser for มคอ.2 and announcement PDFs"* → retitle: *"Build PDF parser for annual admission announcements (primary) and มคอ.2 (secondary, tagged non-authoritative)."*
- **#28** *"Build hierarchical chunker"* → add Thai word tokenization (PyThaiNLP) before chunking.
- **#29** *"Generate embeddings and store in Qdrant"* → enforce metadata schema from §6.1 of this doc.
- **#30** *"Implement BM25 + dense hybrid retrieval"* → add query-intent classifier + metadata filter (§6.2).

### New issues to open

- `[Phase 3] Schema extension — user_test_scores, historical_cutoffs, admission_projects metadata fields` (blocks #24, #25)
- `[Phase 6] Collect annual admission announcement PDFs for 5 target universities (Round 3)` (child of #27)
- `[Phase 6] Table extraction from announcement PDFs → historical_cutoffs + score_weights JSONB` (child of #27)
- `[Phase 6] Query-intent classifier + metadata-aware retrieval router` (extends #30)
- `[Phase 8] Sub-mode detection within Flow B (Portfolio / Score / Last-Minute / Explorer)` (extends #36)
- `[Phase 8] Static TCAS knowledge base for out-of-data-scope questions` (new — see §9 Q6)

### Issues to close or deprioritize

None yet — these stay open but get scope-adjusted after team discussion.

---

## 11. Sequencing

1. **Land schema extension first** (new `user_test_scores`, `historical_cutoffs`, `admission_projects` alters). This blocks all Phase 5 ingestion.
2. **Narrow #23 + #24 to Round 3.** Ingest CSVs and cutoff reports.
3. **Build eligibility engine #25 against the new schema.** Round 3 only.
4. **Phase 6 in parallel with the above** — collect annual announcements, build parser, tag metadata correctly from day one.
5. **Once RAG returns correct chunks, integrate retrieval router.**
6. **Sub-mode detection and static knowledge base come in Phase 8**, not Phase 5/6.

---

## 12. Summary Table (the change at a glance)

| Area | Before | After |
|---|---|---|
| User scores | Only GPAX on `user_profiles` | `user_test_scores` table, per subject × year |
| Cutoff data | Nothing (rubric min only) | `historical_cutoffs` table, per project × year |
| R1/R2 representation | `specific_conditions` free text | `round_metadata` JSONB; empty during capstone |
| Major → career | No link | Derived from Phase 7 scraped data (materialized view) |
| RAG primary source | มคอ.2 + announcements (equal weight) | Annual announcements (primary, authoritative); มคอ.2 (secondary, curriculum-only, tagged) |
| RAG retrieval | Single filter by dense similarity | Query-intent classifier → metadata-filtered retrieval |
| PDF parsing | Generic text extraction | + Thai tokenization + table extraction (Camelot) |
| Mode Selector | 2 top-level modes (A, B) | 2 top-level + 4 Flow B sub-modes |
| R1/R2 answers | (not designed) | Explicit "data unavailable" refusal, not LLM guess |

---

*Open for team debate. Once agreed, the relevant sections will be merged into CLAUDE.md and the issue-list adjustments will be actioned.*
