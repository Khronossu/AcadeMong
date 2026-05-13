# RAG PDF Ingestion Guide — Phase 6

> **Who is this for:** The team member responsible for collecting มคอ.2 and faculty announcement PDFs and ingesting them into the AcadeMong RAG pipeline.
>
> **Time estimate:** Data collection 4–8 hrs depending on university website accessibility. Ingestion itself takes ~5 minutes per 10 PDFs.

---

## 1. Why This Matters

AcadeMong has two AI flows:

- **Flow A (Career Dreamer)** — explores careers and interests
- **Flow B (TCAS Advisor)** — answers eligibility AND preparation questions

Flow B currently answers eligibility from SQL (TCAS CSV data). But for questions like:
- "ต้องเตรียม portfolio อย่างไรสำหรับคณะสถาปัตย์จุฬา?"
- "หลักสูตรแพทย์มหิดลมีกี่ปี เรียนอะไรบ้าง?"
- "คณะวิทยาศาสตร์เกษตรสมัครรอบ 3 มีเงื่อนไขพิเศษอะไร?"

...the AI currently says "I don't have that information." It needs the actual faculty documents to answer these. That's what this phase does — the pipeline already exists, it just needs real data.

**Without PDFs, Qdrant `tcas_docs` only has 725 vectors from one test file.** After this phase it should have thousands.

---

## 2. What Documents to Collect

### Priority 1 — มคอ.2 (Thai Curriculum Specification)

The official curriculum document every Thai university must publish. Contains: course objectives, structure, subject list, learning outcomes, graduation requirements. These are **stable** (updated every few years, not annually) so they're the highest-value documents to ingest.

### Priority 2 — Admission Announcement PDFs (ประกาศรับสมัคร)

Round-specific announcements published per faculty per year. Contain: portfolio requirements, interview criteria, special admission conditions. These change annually — label them with the year.

### Target Universities (Phase 6 scope)

| University | Thai name (exact — must match DB) |
|---|---|
| Chulalongkorn | `จุฬาลงกรณ์มหาวิทยาลัย` |
| Mahidol | `มหาวิทยาลัยมหิดล` |
| Kasetsart | `มหาวิทยาลัยเกษตรศาสตร์` |
| Thammasat | `มหาวิทยาลัยธรรมศาสตร์` |
| Srinakharinwirot | `มหาวิทยาลัยศรีนครินทรวิโรฒ` |

Verify exact names against the database before building the manifest:
```bash
docker exec -i academong-postgres-1 psql -U admin -d tcas_advisor -c "SELECT name FROM universities;"
```

### Where to Find the Documents

| University | มคอ.2 Location | Announcement Location |
|---|---|---|
| จุฬา | `cuir.car.chula.ac.th` → ค้นหา "มคอ.2" | Faculty websites, `admission.chula.ac.th` |
| มหิดล | `op.mahidol.ac.th` → หลักสูตร | `admission.mahidol.ac.th` |
| เกษตร | `registrar.ku.ac.th` → หลักสูตร | `admission.ku.ac.th` |
| ธรรมศาสตร์ | `registrar.tu.ac.th` → หลักสูตร | `admission.tu.ac.th` |
| ศรีนครินทรวิโรฒ | `registrar.swu.ac.th` → หลักสูตร | Faculty websites |
| ทุกมหาวิทยาลัย | `mytcas.com` → เลือกสาขา → ดูประกาศ | `mytcas.com` |

---

## 3. Recommended Collection Methods

### Method A — Manual Download (simplest, no code)

1. Open each university's curriculum/registrar page
2. Search for "มคอ.2" or the faculty name
3. Download PDFs one by one
4. Rename using the convention below

Best for: small batches, when you need to verify document quality first.

---

### Method B — Firecrawl (recommended for announcements)

[Firecrawl](https://firecrawl.dev) scrapes JavaScript-heavy university websites and returns clean markdown or downloads files. Much faster than manual.

Install the CLI:
```bash
npm install -g firecrawl-cli
# or use the API directly
```

**Scrape a faculty page to find PDF links:**
```bash
firecrawl scrape "https://admission.chula.ac.th/round3" --format markdown
```

**Crawl an entire admission section:**
```bash
firecrawl crawl "https://admission.mahidol.ac.th" \
  --include-paths "/curriculum/*,/announcement/*" \
  --output ./scraped/
```

**Map all URLs on a site first (find where PDFs are):**
```bash
firecrawl map "https://registrar.ku.ac.th" --search "มคอ"
```

Firecrawl handles Thai character URLs, JavaScript rendering, and pagination automatically. The Claude Code IDE extension also has a built-in Firecrawl skill — just type the URL in the chat.

---

### Method C — Python bulk downloader (for known URL patterns)

Some universities follow predictable URL patterns for their PDFs. This script finds and downloads them:

```python
import requests
from pathlib import Path
import time

# Example: Chula curriculum PDFs follow a pattern
BASE_URLS = [
    "https://cuir.car.chula.ac.th/handle/123456789/...",
    # Add more known PDF URLs here
]

OUT_DIR = Path("data/pdfs")
OUT_DIR.mkdir(exist_ok=True)

headers = {"User-Agent": "Mozilla/5.0 (research bot — contact: your@email.com)"}

for url in BASE_URLS:
    filename = url.split("/")[-1]
    if not filename.endswith(".pdf"):
        filename += ".pdf"
    out_path = OUT_DIR / filename
    if out_path.exists():
        print(f"Skip (exists): {filename}")
        continue
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code == 200 and "pdf" in resp.headers.get("content-type", ""):
        out_path.write_bytes(resp.content)
        print(f"Downloaded: {filename}")
    else:
        print(f"Failed ({resp.status_code}): {url}")
    time.sleep(1)  # be polite — 1 request/sec
```

---

### Method D — mytcas.com scraper (best for announcements)

mytcas.com lists all admission announcements with direct PDF links. Use Firecrawl or requests to extract them:

```python
import requests
from bs4 import BeautifulSoup

# Example: get announcement PDFs for a specific round
url = "https://www.mytcas.com/programs?round=3&year=2567"
resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(resp.text, "html.parser")

pdf_links = [a["href"] for a in soup.find_all("a", href=True) if a["href"].endswith(".pdf")]
print(f"Found {len(pdf_links)} PDFs")
```

---

## 4. File Naming Convention

Use a consistent, readable naming scheme:

```
{university_short}_{faculty_short}_{type}_{year}.pdf

Examples:
  chula_science_math_mko2_2566.pdf
  chula_engineering_computer_mko2_2566.pdf
  mahidol_medicine_announcement_round3_2567.pdf
  tu_law_mko2_2566.pdf
  ku_agri_announcement_round3_2567.pdf
```

University short codes:
- `chula` — จุฬาลงกรณ์
- `mahidol` — มหิดล
- `ku` — เกษตรศาสตร์
- `tu` — ธรรมศาสตร์
- `swu` — ศรีนครินทรวิโรฒ

---

## 5. Check PDFs Are Text-Selectable (Critical)

The parser extracts the **text layer** of PDFs. Scanned image PDFs (common for older มคอ.2) have no text layer and will produce empty chunks.

**Test before adding to manifest:**
1. Open the PDF in any viewer
2. Try to click and drag to select text
3. If you can select text → ✅ good to go
4. If nothing selects → ❌ scanned PDF, skip it (or run OCR first)

**Quick batch test using Python:**
```python
import fitz  # pip install pymupdf

def has_text(pdf_path):
    with fitz.open(pdf_path) as doc:
        for page in doc:
            if page.get_text().strip():
                return True
    return False

from pathlib import Path
for pdf in Path("data/pdfs").glob("*.pdf"):
    status = "✅ text" if has_text(pdf) else "❌ scanned — skip"
    print(f"{pdf.name}: {status}")
```

---

## 6. Build the manifest.json

**Every PDF needs an entry.** The manifest tells the system which university/major/round the document belongs to so RAG search can filter correctly.

File location: `data/pdfs/manifest.json`

Format:
```json
[
  {
    "filename": "chula_science_math_mko2_2566.pdf",
    "university": "จุฬาลงกรณ์มหาวิทยาลัย",
    "major": "คณิตศาสตร์",
    "round": 3,
    "year": 2566,
    "source_url": "https://science.chula.ac.th/..."
  },
  {
    "filename": "mahidol_medicine_mko2_2566.pdf",
    "university": "มหาวิทยาลัยมหิดล",
    "major": "แพทยศาสตร์",
    "round": 3,
    "year": 2566,
    "source_url": "https://op.mahidol.ac.th/..."
  }
]
```

**Rules:**
- `university` must **exactly** match the `universities.name` column in PostgreSQL (check with the SQL above)
- `year` is Buddhist Era (พ.ศ.) — e.g., 2566 not 2023
- `round` is the TCAS round number (1–4), or `null` for มคอ.2 that aren't round-specific
- `source_url` is the original URL — important for citation enforcement
- PDFs without a manifest entry are still ingested but with null metadata (weaker search filtering)

---

## 7. Run the Ingestion

### Prerequisites

Make sure Docker services are running:
```bash
docker compose up -d postgres redis qdrant ollama fastapi
```

Confirm `nomic-embed-text` is pulled in Ollama:
```bash
curl http://localhost:11434/api/tags
# should show nomic-embed-text in the list
```

If not:
```bash
docker exec academong-ollama-1 ollama pull nomic-embed-text
```

### Run

From the `backend/` directory:

```bash
# Windows
.venv\Scripts\python.exe -m ingestion.ingest_pdfs --pdf-dir ../data/pdfs

# Mac / Linux
.venv/bin/python -m ingestion.ingest_pdfs --pdf-dir ../data/pdfs
```

### What it does (step by step)

1. Reads `manifest.json` to load metadata
2. For each `.pdf` file: computes SHA-256 hash → checks if already in Qdrant → skips if unchanged
3. Extracts text page by page using PyMuPDF
4. Splits into 400-character overlapping chunks (80-char overlap) — tuned for Thai text density
5. Generates dense embedding via `nomic-embed-text` (768 dimensions)
6. Generates sparse BM25 vector via `fastembed`
7. Stores both vectors + metadata in Qdrant collection `tcas_docs`

The script is **idempotent** — safe to re-run. Documents that haven't changed are skipped automatically.

### Expected output

```
Collection ready. Processing 12 PDF(s)...

chula_science_math_mko2_2566.pdf → 47 chunks (new)
chula_engineering_computer_mko2_2566.pdf → 83 chunks (new)
mahidol_medicine_mko2_2566.pdf → 61 chunks (new)
tu_law_mko2_2566.pdf → 55 chunks (new)
...

Done. 12 PDFs processed, 640 chunks upserted.
```

---

## 8. Verify It Worked

```bash
# Check vector count in Qdrant
curl http://localhost:6333/collections/tcas_docs
# "points_count" should be much higher than 725 (the test baseline)

# Test a search via the API (requires auth token — get one by logging in to the app)
curl -X POST http://localhost:8000/api/chat/{session_id}/message \
  -H "Authorization: Bearer {your_token}" \
  -H "Content-Type: application/json" \
  -d '{"content": "หลักสูตรคณิตศาสตร์จุฬาเรียนกี่ปี มีวิชาอะไรบ้าง"}'
```

If RAG is working, the AI response will cite specific curriculum details from the PDF. If it says "ไม่มีข้อมูล", the chunks didn't make it into Qdrant or the search isn't matching.

---

## 9. Gotchas and Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `Empty chunks` for a PDF | Scanned image PDF, no text layer | Skip it or run OCR (Tesseract) first |
| `university not found` warning | `manifest.json` university name doesn't match DB | Run the SQL to get exact names |
| Embedding hangs | Ollama not running or nomic-embed-text not pulled | `docker compose up -d ollama` then pull model |
| Chunks inserted but search returns nothing | Metadata filter mismatch | Check that `university` field in manifest matches DB exactly |
| Thai characters garbled | Manifest saved as wrong encoding | Save `manifest.json` as UTF-8 (no BOM) |
| PDF downloads from university sites blocked | Bot detection | Add `User-Agent` header, add `time.sleep(1)` between requests |

---

## 10. Do Not Commit PDFs to Git

`data/pdfs/*.pdf` is gitignored. Share PDFs with the team via:
- Google Drive shared folder
- A `tar.gz` bundle uploaded to the project's release assets

Only `data/pdfs/manifest.json` should be committed to git.

---

## 11. Quick Checklist

- [ ] Collect มคอ.2 PDFs for all 5 universities (at least key faculties)
- [ ] Collect admission announcement PDFs for Round 3, year 2567
- [ ] Verify all PDFs have selectable text (not scanned)
- [ ] Build `data/pdfs/manifest.json` with correct Thai university names
- [ ] Run ingestion script and confirm chunk count > 1000
- [ ] Test a preparation question in the chat and verify AI cites PDF content
- [ ] Commit `manifest.json` (not the PDFs)
