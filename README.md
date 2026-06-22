# Vietnam Data Job Market Analysis

A **Data Analyst** project that collects Vietnamese **Data/IT job postings**, standardizes them,
**labels each job into a job family**, and mines the market for **insights** — which roles hire most,
which skills/technologies are in demand, how cities and company types differ, and what a job seeker
should learn.

> **No salary.** The dataset has no salary field, so the project does **not** estimate, predict, or
> forecast salary. The focus is **understanding the job market**, not prediction.
> Authoritative roadmap: [`MASTER_PLAN.md`](MASTER_PLAN.md) (v1.1). Handoff: [`PROJECT_STATUS.md`](PROJECT_STATUS.md), [`WORK_DIVISION.md`](WORK_DIVISION.md).

## What it does
```
6 sources → warehouse (CDC) → Silver (clean/standardize)
   → ⭐ Job Family Labeling Engine → job_family + hierarchy + metadata
   → Gold (aggregate by family) → NLP → Analysis (EDA + statistics + insight-ML)
   → Recommendation → Dashboard (Streamlit) → Report
```
The **Job Family Labeling Engine** is the foundation: every analysis keys off the `job_family` label.

## ⭐ Job Family Labeling Engine (the core problem)
Job titles alone are not enough — many data roles don't say "data" in the title, and titles like
"Specialist/Executive/Consultant" are ambiguous. So we read **title + JD + skills** and assign a
**hierarchical job family** (Domain → Sub-domain → Family) via a 3-tier cascade:

1. **Rule/keyword** (config in YAML) — accept if high confidence (~31% of jobs).
2. **Embedding similarity** vs family prototypes (multilingual-e5) — for the unsure remainder.
3. **LLM tier with dynamic failover** — one judge per job, routed across multiple free-tier providers
   (Groq, Cerebras, Mistral, OpenRouter, Gemini). A provider that hits its rate/daily limit is marked
   exhausted and its jobs are **automatically rerouted** to one with capacity, so the run never stalls;
   responses are disk-cached so it is fully **resumable** (no quota wasted on a rerun). Low confidence
   → manual review. (Multi-judge voting is supported/modular, but a single strong judge per job is used
   at scale to fit free-tier limits.)

Designed as a **standalone, reusable module** (`engine.predict(job)`), versioned taxonomy, rich
metadata (`domain, subdomain, job_family, confidence, labeling_method, llm_votes, reasoning,
review_status`), and quality KPIs (coverage, agreement, unknown/review rate, spot-check accuracy).

## Status
| Phase | Scope | State |
|---|---|---|
| P0 Data Collection | 6 VN sources → warehouse (CDC) | ✅ done |
| P1 Clean/Standardize (Silver) | skills/seniority/location/company + dedup | ✅ done |
| **P2 ⭐ Job Family Labeling Engine** | hierarchical taxonomy (20 families) + 3-tier cascade + failover | ✅ **done** — 1701 jobs labeled, integrated into `jobs_silver` + 7 `gold_*` tables |
| P3 Feature/NLP · P4 Market & Statistical Analysis | EDA, market share %, comparisons | ⬜ **next (teammate, Luồng B)** |
| P5 Insight-ML · P6 Recommendation | association rules · clustering · topic modeling · recommenders | ⬜ |
| P7 Dashboard · P8 Report | Streamlit drill-down + insights | ⬜ |
| P9 Forecasting | job/skill demand over time | ⛔ deferred (only 1 snapshot) |

**P2 result (market share over 852 active Data/AI jobs):** Business Analyst 21% · Data Engineer 17.5% ·
Data Analyst 15% · AI Engineer 14% · Risk/Fraud 6% · BI 5% · Data Scientist 4% · … (20 families).
100% labeled, 0 manual-review. See [`docs/labeling_kpi.md`](docs/labeling_kpi.md) and [`docs/TAXONOMY.md`](docs/TAXONOMY.md).

## Sources (per snapshot, ~1,700 distinct postings, full JD)
| Source | ~Count | Access |
|---|--:|---|
| VietnamWorks | 790 | public JSON API (direct) |
| CareerViet | 382 | server-rendered HTML (direct) |
| ITviec | 286 | HTML via ScraperAPI |
| TopCV | 99 | Cloudflare → Claude-in-Chrome |
| TopDev | 82 | JSON API (robots-override, personal use) |
| Glints | 62 | GraphQL (direct) |

Responsible scraping: robots.txt, randomized 3–8s delays, UA rotation, raw cache, credit guard.

## Layout
```
pipeline/           ingest/ · transform/ (load·silver·gold) · dataset/ · utils/ · __main__.py (CLI)
job_family_engine/  taxonomy/taxonomy_v1.yml · rules.py · embed_match.py · llm_judge.py ·
                    engine.py (dynamic-failover cascade) · evaluate.py (KPIs) · integrate.py (→ silver+Gold)
analysis/           EDA + statistics + insight-ML (P4–P5, teammate)
dashboard/          Streamlit app (P7)
ref/                reference dictionaries (skills, seniority, company type) + taxonomy/
docs/               DATA_DICTIONARY.md · quality_report.md · TAXONOMY.md · labeling_kpi.md
tests/              pytest (45 tests)
data/               warehouse.duckdb IS shipped (13 MB, the data layer); raw/bronze/labeling/dataset gitignored
```

## Quick start
```bash
python -m pip install -e .                 # core deps  (add: pip install -e ".[dataset]" for embeddings/LLM)
cp .env.example .env                       # ScraperAPI + LLM keys (gitignored) — only needed to (re)build data
# --- Data layer (P0–P2): rebuild from scratch (needs keys + time), or use a shipped warehouse (see below) ---
python -m pipeline scrape                  # crawl → bronze
python -m pipeline enrich --source <src>   # fill JD where listing-only
python -m pipeline load                    # bronze → warehouse (incremental CDC)
python -m pipeline silver                  # normalize + dedup → jobs_silver
python -m pipeline label                   # ⭐ Job Family Engine → data/labeling/job_family.parquet (resumable)
python -m pipeline label-kpi               # labeling KPIs + spot-check sample
python -m pipeline integrate               # job_family → jobs_silver + 7 gold_* tables + market share
python -m pytest -q                        # 45 tests
```

## For the analysis teammate (Luồng B — P3+)
The repo **ships `data/warehouse.duckdb`** (13 MB) — already containing the labeled **`jobs_silver`**
(with `job_family`, `jf_domain`, `jf_subdomain`, `jf_confidence`) + all **7 `gold_*`** tables — so you can
start analysing right after cloning, no rebuild needed:
```python
import duckdb
con = duckdb.connect("data/warehouse.duckdb", read_only=True)
con.sql("SELECT job_family, n, pct FROM gold_market_share ORDER BY n DESC").show()
con.sql("SELECT * FROM jobs_silver WHERE job_family <> 'OTHER' LIMIT 5").show()
```
Your work keys off `jobs_silver.job_family` + the `gold_*` tables — you do **not** need the engine
internals. Read [`WORK_DIVISION.md`](WORK_DIVISION.md) for the split and
[`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) for every column. (Other `data/` artifacts —
raw/bronze/embeddings/labeling cache — stay local and are gitignored; the warehouse is all you need.
Note: the warehouse also contains raw scraped JD in the `jobs` table — keep the repo access controlled.)

## Constraints
🚫 No salary (not in data) · 🚫 No LinkedIn · 🚫 No forecasting yet (1 snapshot) · VN + Data only ·
Secrets only via `.env` (never hardcoded) · This is a **Data Analytics** project, not an ML/MLOps product.
