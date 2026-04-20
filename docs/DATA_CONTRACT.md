# DATA_CONTRACT.md

> Contract between **AcadeMong** (this repo, consumer) and **[AcadeMong-data](https://github.com/Khronossu/academong-data)** (producer).
> Any change to this document requires a PR on the main repo and a matching update in the data repo.

---

## 1. What this document is

The data repo produces scraped + extracted data. The main repo ingests it into Postgres and Qdrant. This document defines exactly what the producer must emit so that the consumer's ingestion script (issue #24) can load it without guesswork.

If the contract is broken, the build breaks. Any schema change here is a coordinated PR across both repos.

---

## 2. Scope

**In scope (v1):**
- TCAS **Round 3 (Admission)** data for the 5 target universities: Chulalongkorn, Mahidol, Kasetsart, Thammasat, Srinakharinwirot.
- Years: 2024, 2025, 2026.
- Annual admission announcement PDFs + structured extractions.
- มคอ.2 curriculum PDFs (with year citation).

**Out of scope (v1):**
- TCAS Round 1 (Portfolio), Round 2 (Quota), Round 4 (Direct). Placeholder tables only; see `propose_change.md` §3.
- Career / JobsDB data — separate Phase 7 pipeline, different contract.
- Portfolio rubrics, interview corpora, quota lists.

---

## 3. Release mechanism

The data repo publishes a **tagged GitHub Release** per scrape run.

- Tag format: `vYYYY.MM.DD` (e.g. `v2026.04.21`). If multiple tags in one day, append `-n`: `v2026.04.21-2`.
- Release asset: one tarball `academong-data-vYYYY.MM.DD.tar.gz` containing the full layout below.
- Releases are immutable. A bad release is superseded by a new tag, never rewritten.
- Main repo pins a specific tag in its ingestion config. Upgrading data = bumping the tag in one config file.

---

## 4. File layout inside the tarball

```
academong-data-vYYYY.MM.DD/
├── manifest.json                         # index of everything in this release
├── csv/
│   ├── universities.csv
│   ├── faculties.csv
│   ├── majors.csv
│   ├── tcas_rounds.csv
│   ├── admission_projects.csv
│   ├── subject_requirements.csv
│   └── historical_cutoffs.csv
├── pdfs/
│   ├── announcements/
│   │   └── {university_slug}/{year}/{faculty_slug}__{project_slug}.pdf
│   ├── mko2/
│   │   └── {university_slug}/{faculty_slug}__{major_slug}__{publication_year}.pdf
│   └── pdf_manifest.json                 # SHA-256 + source URL per PDF
└── README.md                             # free-text notes for this release
```

**Slug rules:** lowercase ASCII, `-` between words, transliterate Thai to ASCII (e.g. `จุฬาลงกรณ์` → `chulalongkorn`). Slugs must be stable across releases — same major = same slug.

---

## 5. CSV schemas

All CSVs are:
- UTF-8 encoded, **no BOM**.
- RFC 4180 quoted (`"` around values containing `,`, `"`, or newlines; embedded `"` doubled).
- Header row required, column order must match the spec below.
- Empty cell = `NULL`. Do not emit literal strings `"NULL"`, `"None"`, `"N/A"`, `""`.
- Dates: `YYYY-MM-DD`. Timestamps: ISO 8601 with timezone.
- Numbers: `.` as decimal separator, no thousands separator, no currency symbols.

### 5.1 `universities.csv`

| Column | Type | Required | Notes |
|---|---|---|---|
| `university_slug` | string | ✅ | Stable natural key. |
| `name` | string | ✅ | Full Thai name preferred. |
| `location` | string |  | Province / city. |

### 5.2 `faculties.csv`

| Column | Type | Required | Notes |
|---|---|---|---|
| `university_slug` | string | ✅ | FK → `universities.university_slug`. |
| `faculty_slug` | string | ✅ | Unique *within* a university. |
| `name` | string | ✅ | |

### 5.3 `majors.csv`

| Column | Type | Required | Notes |
|---|---|---|---|
| `university_slug` | string | ✅ | |
| `faculty_slug` | string | ✅ | |
| `major_slug` | string | ✅ | Unique within `(university, faculty)`. |
| `name` | string | ✅ | |
| `field` | string |  | Broad category, e.g. `engineering`, `health_science`. |

### 5.4 `tcas_rounds.csv`

| Column | Type | Required | Notes |
|---|---|---|---|
| `university_slug` | string | ✅ | |
| `faculty_slug` | string | ✅ | |
| `major_slug` | string | ✅ | |
| `round_number` | integer | ✅ | **Only `3` valid in v1.** |
| `year` | integer | ✅ | TCAS admission cycle year. |

### 5.5 `admission_projects.csv`

| Column | Type | Required | Notes |
|---|---|---|---|
| `university_slug` | string | ✅ | |
| `faculty_slug` | string | ✅ | |
| `major_slug` | string | ✅ | |
| `round_number` | integer | ✅ | Must be `3` in v1. |
| `year` | integer | ✅ | |
| `project_slug` | string | ✅ | Stable within `(university, faculty, major, round, year)`. |
| `project_name` | string | ✅ | Full Thai name of the project. |
| `round_type` | string | ✅ | Must be `admission` in v1 (= R3). |
| `seats` | integer |  | |
| `gpax_min` | decimal(3,2) |  | `0.00`–`4.00`. |
| `accepts_ged` | boolean |  | `true`/`false` lowercase. Default `false`. |
| `specific_conditions` | string |  | Free text. |
| `source_url` | string | ✅ | Canonical announcement URL. |
| `round_metadata_json` | JSON string |  | Single-line JSON; see §5.5.1. |

#### 5.5.1 `round_metadata_json` for Round 3

Raw parse intermediate. `subject_requirements.csv` is the authoritative source for computation — this column is for debugging/audit. Shape:

```json
{"score_weights": {"TGAT1": 0.2, "TGAT2": 0.3, "A_LEVEL_MATH1": 0.5}}
```

Weights may but need not sum to 1.0; keep whatever the document states.

### 5.6 `subject_requirements.csv`

| Column | Type | Required | Notes |
|---|---|---|---|
| `university_slug` | string | ✅ | |
| `faculty_slug` | string | ✅ | |
| `major_slug` | string | ✅ | |
| `round_number` | integer | ✅ | |
| `year` | integer | ✅ | |
| `project_slug` | string | ✅ | |
| `subject` | string | ✅ | Must match the controlled vocabulary in §7. |
| `min_score` | decimal |  | |
| `weight_percent` | decimal |  | `0`–`100` (percent), not `0`–`1`. |

One row per subject-per-project. Normalized version of `round_metadata.score_weights`.

### 5.7 `historical_cutoffs.csv`

| Column | Type | Required | Notes |
|---|---|---|---|
| `university_slug` | string | ✅ | |
| `faculty_slug` | string | ✅ | |
| `major_slug` | string | ✅ | |
| `round_number` | integer | ✅ | |
| `year` | integer | ✅ | Admission cycle year the cutoff refers to. |
| `project_slug` | string | ✅ | |
| `score_type` | string | ✅ | Identifies *what score* the row describes. Values: `composite_weighted`, `TGAT_total`, `TPAT1`, `A_LEVEL_MATH1`, etc. (§7 for full list). |
| `min_admitted_score` | decimal |  | |
| `max_admitted_score` | decimal |  | |
| `median_score` | decimal |  | |
| `applicants_count` | integer |  | |
| `accepted_count` | integer |  | |
| `source_url` | string | ✅ | Where this statistic was read from. |

**Important:** the main repo's `historical_cutoffs` table is SCD Type 2. The ingestion script handles versioning — the producer just emits the current value. One row per `(project, year, score_type)` per release.

---

## 6. `manifest.json` (top-level index)

```json
{
  "release_tag": "v2026.04.21",
  "generated_at": "2026-04-21T14:03:00+07:00",
  "producer_commit_sha": "abc1234567...",
  "scope": {
    "rounds": [3],
    "years": [2024, 2025, 2026],
    "universities": ["chulalongkorn", "mahidol", "kasetsart", "thammasat", "swu"]
  },
  "row_counts": {
    "universities": 5,
    "faculties": 42,
    "majors": 310,
    "admission_projects": 580,
    "subject_requirements": 2100,
    "historical_cutoffs": 1740
  },
  "notes": "optional free-text"
}
```

## 6.1 `pdf_manifest.json` (per-PDF provenance)

Required by CLAUDE.md §17 Layer 3 (source allowlist + SHA-256 manifest). One entry per PDF.

```json
{
  "release_tag": "v2026.04.21",
  "pdfs": [
    {
      "path": "pdfs/announcements/chulalongkorn/2026/engineering__computer_engineering.pdf",
      "doc_type": "announcement",
      "authority_level": "authoritative",
      "university_slug": "chulalongkorn",
      "faculty_slug": "engineering",
      "major_slug": "computer_engineering",
      "project_slug": "regular",
      "year": 2026,
      "source_url": "https://www.eng.chula.ac.th/.../tcas66_r3.pdf",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "downloaded_at": "2026-04-20T09:12:00+07:00"
    },
    {
      "path": "pdfs/mko2/chulalongkorn/engineering__computer_engineering__2018.pdf",
      "doc_type": "mko2",
      "authority_level": "curriculum_only",
      "university_slug": "chulalongkorn",
      "faculty_slug": "engineering",
      "major_slug": "computer_engineering",
      "publication_year": 2018,
      "source_url": "https://...",
      "sha256": "...",
      "downloaded_at": "2026-04-20T09:15:00+07:00"
    }
  ]
}
```

**Fields:**
- `doc_type`: `announcement` | `mko2` | `cutoff_report`
- `authority_level`: `authoritative` (announcements, cutoff reports) | `curriculum_only` (มคอ.2)
- For มคอ.2, `publication_year` is the year the document was published, **not** the current TCAS cycle — drives the staleness warning.
- `project_slug` is optional on announcements that cover the whole faculty (no single project).

---

## 7. Controlled vocabularies

### 7.1 `subject` values (for `subject_requirements.subject`)

TCAS 2023+ names. Use exactly these strings — case-sensitive.

- `TGAT1`, `TGAT2`, `TGAT3`, `TGAT` (total)
- `TPAT1`, `TPAT2`, `TPAT3`, `TPAT4`, `TPAT5`
- `A_LEVEL_MATH1`, `A_LEVEL_MATH2`
- `A_LEVEL_PHYSICS`, `A_LEVEL_CHEMISTRY`, `A_LEVEL_BIOLOGY`, `A_LEVEL_GENERAL_SCIENCE`
- `A_LEVEL_THAI`, `A_LEVEL_ENGLISH`, `A_LEVEL_SOCIAL_STUDIES`
- `A_LEVEL_FRENCH`, `A_LEVEL_GERMAN`, `A_LEVEL_JAPANESE`, `A_LEVEL_CHINESE`, `A_LEVEL_ARABIC`, `A_LEVEL_PALI`, `A_LEVEL_KOREAN`, `A_LEVEL_SPANISH`
- `GPAX` (for projects that include GPAX as a weighted component, not just `gpax_min`)

If a scraped document uses a subject name not in this list, **file an issue** before inventing a new code. The controlled vocabulary is enforced by the main repo's ingestion — unknown codes are rejected.

### 7.2 `score_type` values (for `historical_cutoffs.score_type`)

- `composite_weighted` — the per-project weighted composite score
- Any value from §7.1 — when the row describes a per-subject sub-cutoff

---

## 8. Validation the producer should run before release

Before tagging a release, run at least:

1. **CSV parse** — every file loads as RFC 4180; header matches spec exactly.
2. **Cross-file FKs** — every `(university_slug, faculty_slug, major_slug, round_number, year, project_slug)` referenced in `subject_requirements.csv` or `historical_cutoffs.csv` exists in `admission_projects.csv`.
3. **Controlled vocabulary** — every `subject` is in §7.1; every `score_type` is in §7.2.
4. **PDF manifest integrity** — every file in `pdfs/` is listed in `pdf_manifest.json`; every listed SHA-256 matches the file on disk.
5. **Slug stability vs previous release** — produce a diff report of renamed/deleted slugs; significant changes need a README note.

A validation script that runs all the above lives in the data repo at `scripts/validate_release.py`.

---

## 9. Consumption on the main-repo side

For reference — the main repo will:

1. Download the pinned release tarball.
2. Verify SHA-256 of the tarball against a value checked into the main repo.
3. Extract and run ingestion (`#24`) which:
   - Inserts/upserts reference tables (`universities`, `faculties`, `majors`).
   - Inserts `tcas_rounds`, `admission_projects`, `subject_requirements` for the current cycle.
   - Applies SCD Type 2 flow for `historical_cutoffs`.
   - Registers PDFs + metadata in Qdrant (handled by `#27`, not `#24`).

---

## 10. Changing this contract

- Additive changes (new optional column, new controlled-vocab code) — minor bump, backward compatible.
- Breaking changes (renamed column, new required field, changed semantics) — requires:
  1. PR on main repo updating this file.
  2. PR on data repo updating the producer.
  3. Coordinated release — new data repo tag is produced *only after* the main repo change is merged.
- Never break the contract in a hotfix. Breaking a release tag breaks every environment that pinned it.
