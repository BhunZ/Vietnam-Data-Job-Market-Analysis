# Vietnam Data Job Market Intelligence — Technical Specification

> A reproducible data pipeline that ingests Data-domain job postings from Vietnamese
> job boards, normalizes them into a clean analytical layer, and surfaces skill-demand,
> role-differentiation, and seniority-progression insights for the Vietnamese market.
> Built as a Data Engineering portfolio project.

---

## 1. Objectives

1. Collect Data-domain job postings (Data Engineer / Data Scientist / Data Analyst /
   ML Engineer / BI / Analytics Engineer) from Vietnamese job boards.
2. Build a layered, reproducible ETL pipeline (raw -> cleaned -> serving).
3. Normalize messy fields (skills, role, seniority, location) against curated
   reference dictionaries.
4. Produce a serving layer + dashboard that explains the Vietnamese Data job market:
   what skills are demanded, how roles differ, how requirements escalate with
   seniority, and how demand differs by city and company type.

### Non-goals
- Salary analysis. ~90% of VN Data postings list salary as "Thoa thuan"
  (negotiable), so cross-role comparison is impossible. Salary is OUT OF SCOPE
  entirely; do not parse, model, or report it.
- International / global job markets as a core focus (see optional stretch in §3).
- Real-time ingestion. Batch (per-run / weekly snapshot) is sufficient.
- Scraping sources that prohibit it or actively block (LinkedIn — excluded).

---

## 2. Scope decision: narrow vertical + single geography

Two intentional constraints keep this clean and defensible:

- **Data jobs only** (not all tech): bounds the skill taxonomy to a curated, closed
  set (~100-150 canonical skills), so normalization is a dictionary-mapping problem,
  not open-ended classification.
- **Vietnam only**: keeps the narrative focused and personally relevant; the project
  doubles as market research for the author's own job search.

---

## 3. Data sources

### Primary — Vietnamese job boards (via ScraperAPI; responsible scraping)
| Source | Why |
|---|---|
| ITviec | Highest density of VN Data jobs; structured skill tags |
| TopDev | Complementary VN tech/data jobs |
| VietnamWorks | Broader coverage; more analyst/BI roles |

Optional expansion if volume is thin: TopCV, CareerViet.

**Responsible-scraping rules (enforced in code):**
- Respect robots.txt; throttle (randomized 3-8s delay); rotate User-Agent.
- Route through ScraperAPI; persist raw responses immediately (idempotent, resumable).
- Personal/educational portfolio use only; do not redistribute raw data commercially.
- Prefer a site's internal JSON endpoint over HTML parsing where one exists.

### Excluded
- **LinkedIn** — ToS prohibits scraping, aggressive technical + legal enforcement,
  high ScraperAPI failure/cost, negative portfolio signal. Excluded by design.

### Optional stretch — global benchmark (only if VN volume is too thin)
Pull remote Data roles from an official API (Remotive / Arbeitnow — public, no key,
zero block) ONLY to support a single comparative question: "How does VN skill demand
compare to the global remote market, and what should a VN candidate learn to compete
for remote roles?" This is a benchmark, not a second market. Keep it clearly separated
and optional. Do not let it dilute the VN focus.

---

## 4. Architecture

```
   ITviec / TopDev / VietnamWorks (via ScraperAPI)
                      |
                      v
   Ingestion layer (per-source connectors)
   -> persist raw JSON/HTML, partitioned by source + run date
                      |
                      v
   Bronze: parsed, typed, source-tagged
                      |
                      v
   Silver: normalized + deduplicated
   (skills, role, seniority, location, posted_date)
                      |
                      v
   Gold: aggregates for serving
   (skill_demand, role_differentiation, seniority_progression,
    role_by_location, cooccurrence, run-over-run trend)
                      |
                      v
   Analysis notebooks + Streamlit dashboard
```

**Storage:** DuckDB (single-file analytical DB) + Parquet for raw/bronze partitions.
No external DB server required. Optional: dbt-duckdb for Silver/Gold transforms to
showcase modeling + lineage.

**Orchestration:** Single CLI entrypoint (`python -m pipeline run`) executing stages
in order, plus a GitHub Actions workflow for scheduled weekly snapshots. (Airflow is
overkill; mention it as a documented "scale-up" path.)

---

## 5. Data model

### Bronze (one row per raw posting, per source)
`source, source_job_id, title_raw, company_raw, location_raw, description_raw,
skills_raw, posted_date_raw, url, ingested_at`

### Silver (cleaned, deduplicated)
`job_id (surrogate), source, title_clean, company, role_category, seniority,
city, region, remote_flag, skills (normalized array), language_req,
posted_date, ingested_at`

- `role_category` in {DE, DS, DA, MLE, BI, AE, OTHER} — rule + keyword mapping from title.
- `seniority` in {Intern, Junior, Mid, Senior, Lead, Manager} — derived from title/description.
- `skills` — mapped through `ref/skills_dictionary.yml` (canonical name + aliases).
- `language_req` — detected foreign-language requirement (EN/JP/KO) where present.
- Dedup: fuzzy match on (normalized company + normalized title + city); keep earliest.

### Gold (serving aggregates)
- `skill_demand`: skill, role_category, count, pct_of_role
- `skill_cooccurrence`: skill_a, skill_b, count (learning-path edges)
- `role_skill_matrix`: role_category x skill share (role differentiation)
- `seniority_progression`: seniority, skill, share (what escalates Junior->Senior)
- `role_by_location`: role_category, city, count
- `company_type_demand`: company_type, role_category/skill counts
- `trend`: snapshot_date, skill, count (run-over-run; grows over time)

### Reference data (versioned in repo)
- `ref/skills_dictionary.yml` — canonical skills + aliases (React.js->React, etc.)
- `ref/role_keywords.yml` — title patterns -> role_category
- `ref/seniority_rules.yml` — patterns -> seniority
- `ref/company_type.yml` — heuristics -> {product, outsourcing, startup, bank_fintech, other}

---

## 6. Cleaning & normalization rules

- **Skills:** lowercase, strip, map via alias dictionary; drop tokens not in dictionary
  (logged for dictionary expansion). Closed canonical set keeps trends clean.
- **Role/seniority:** keyword + regex mapping from title and description.
- **Location:** map to canonical city + region; flag remote.
- **Language requirement:** detect EN/JP/KO requirement mentions.
- **Company type:** heuristic classification for diagnostic comparisons.
- **Dates:** parse relative ("3 ngay truoc") and absolute formats to ISO date.
- **Dedup:** cross-source fuzzy matching as in §5.
- **NO salary handling of any kind.**

---

## 7. Analysis & modeling (salary-free insight catalog)

| Layer | Output |
|---|---|
| Descriptive | Top skills overall and per role; role/city/company-type distribution; posting volume by role |
| Diagnostic | Skill mix DE vs DS vs DA vs MLE vs BI; HN vs HCM vs Da Nang; product vs outsourcing vs bank/fintech; foreign-language requirements |
| Predictive | Role classification model (skills + title -> role_category) with proper eval; trend extrapolation across snapshots; emerging-skill detection (e.g. GenAI/LLM/vector-DB appearing in Data roles) |
| Prescriptive | Skill co-occurrence -> recommended learning paths; gap analysis for a target role/seniority; "what to learn to move Junior -> Senior" |

- **Model:** TF-IDF + Logistic Regression / LightGBM for role classification; report
  precision/recall per class + confusion matrix; feature importance / SHAP for
  interpretability. NOTE: validate sample size in phase 1; if some classes are tiny,
  merge classes or accumulate more snapshots before training.

---

## 8. Tech stack
- Python 3.11+, requests/httpx, pydantic (schema validation), pandas/polars
- duckdb, optional dbt-duckdb
- rapidfuzz (dedup), pyyaml (reference data)
- scikit-learn / lightgbm, shap
- streamlit (dashboard), plotly/altair
- python-dotenv, pytest, ruff + black, pre-commit

---

## 9. Repository structure
```
vn-data-job-market/
├── README.md
├── pyproject.toml
├── .env.example              # SCRAPERAPI_KEY=  (no real values)
├── .gitignore                # .env, data/, *.duckdb
├── config/
│   └── sources.yml           # per-source endpoints, params, rate limits
├── ref/
│   ├── skills_dictionary.yml
│   ├── role_keywords.yml
│   ├── seniority_rules.yml
│   └── company_type.yml
├── pipeline/
│   ├── __main__.py           # CLI: ingest | bronze | silver | gold | all
│   ├── ingest/               # one connector per source
│   ├── transform/            # bronze->silver->gold
│   ├── quality/              # validation checks
│   └── utils/
├── analysis/                 # notebooks
├── dashboard/                # streamlit app
├── tests/
├── data/                     # gitignored: raw/ bronze/ silver/ gold/
└── .github/workflows/pipeline.yml
```

---

## 10. Secrets & reproducibility
- All credentials via environment variables, loaded from `.env` (gitignored).
  Commit only `.env.example` with empty placeholders. Never hardcode keys.
- Pin dependencies; set random seeds in modeling.
- Pipeline is idempotent and resumable: raw responses cached so re-runs don't re-fetch.

---

## 11. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Low VN Data-job volume (few hundred active) | High | Accumulate weekly snapshots; include all seniorities + adjacent roles; expand to TopCV/CareerViet; merge sparse model classes; activate global benchmark only if needed |
| ScraperAPI fails on a VN board | Medium | Cache raw; retry w/ backoff; modular per-source parsers |
| Site HTML/endpoint changes | Medium | Prefer JSON endpoints; schema validation; isolated parsers |
| Skill dictionary gaps | Medium | Log unmapped tokens each run; review and extend dictionary |
| Cross-source duplicates | High | Fuzzy dedup on company+title+city |
| Short trend window | Medium | Snapshot each run; supplement with posted_date |

---

## 12. Build phases

1. **Spike / data inspection.** Start with ITviec via ScraperAPI. Pull a small sample,
   persist raw, print the data shape (fields, types, example values, null rates, how
   skills/role/location are represented) AND the approximate count of available Data
   postings. Goal: understand data shape AND validate volume before committing to
   schema and before deciding whether the global benchmark is needed.
2. **Ingestion + Bronze.** All VN connectors, raw persistence, parsing to typed Bronze.
3. **Silver + reference data.** Normalization, dedup, dictionaries, role/seniority/
   company-type derivation, data-quality checks.
4. **Gold + analysis + dashboard.** Aggregates, role classification model + SHAP,
   Streamlit dashboard, README with findings.

---

## 13. Deliverables
- [ ] Public GitHub repo with README (problem, architecture diagram, how-to-reproduce, key findings)
- [ ] Reproducible pipeline (`python -m pipeline all`)
- [ ] Reference dictionaries versioned in repo
- [ ] Analysis notebook + Streamlit dashboard
- [ ] Tests + CI workflow
