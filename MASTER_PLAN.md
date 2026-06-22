# MASTER PLAN — VN Data Job Market Analysis  (v1.1 Final)
> Authoritative roadmap. Updated 2026-06-20 (v1.1 after strict review). **NOT a salary project**
> (dataset has no salary → all salary estimate/predict/forecast is OUT, permanently).
> Centerpiece = a standalone, reusable **Job Family Labeling Engine**. No code until user approves.
> v1.1 principle: keep it a **Data Analytics project**, not MLOps/Software-Engineering — no
> over-engineering (no log-file infra, no perf KPIs, no error-handling framework, no "feature store").

## 0. North star
Analyze the Vietnamese Data/IT recruitment market and produce **insights** for **job seekers**
(which families hire most, which skills/tech to learn) and **recruiters** (skill landscape,
competition by family). Deliverable = report + interactive dashboard + reusable labeling engine.

## 1. Overall architecture
```
RAW (6 sources)  →  SILVER (clean/standardize + dedup)
                      → ⭐ JOB FAMILY LABELING ENGINE (standalone module) → job_family + hierarchy + metadata
                      → integrate into warehouse → GOLD (aggregate by job_family)
                          → NLP (skills/keywords/embeddings)
                          → ANALYSIS (EDA + statistics + insight-ML: association rules · clustering · topic modeling)
                          → RECOMMENDATION (skill / similar-job)
                          → DASHBOARD (Streamlit, drill-down by taxonomy)
                          → REPORT + INSIGHT
[Forecasting = CONDITIONAL: only when ≥ several weekly snapshots exist. 1 snapshot now → excluded.]
```
The labeling engine is the **foundation**: every downstream analysis keys off `job_family`.

## 2-5. Phases (objective · deliverables · dependencies · status)

| Phase | Objective | Key deliverables | Depends on | Status |
|---|---|---|---|---|
| **P0 Data Collection** | crawl 6 VN sources responsibly | `warehouse.duckdb` (jobs, CDC), 1701 jobs + JD | — | ✅ done |
| **P1 Clean/Standardize (Silver)** | normalize skills/seniority/location/company; dedup | `jobs_silver` | P0 | ✅ done (rule role_category → demoted to baseline) |
| **P2 ⭐ Job Family Labeling Engine** | assign every job a hierarchical `job_family` from title+JD+skills via 3-tier cascade (rule→embedding→LLM w/ dynamic failover); standalone reusable module | `job_family_engine/` (`engine.predict(job)`), `job_family` + metadata on every job, engine KPI report | P1 | ✅ **done** — 1701 labeled (100%), integrated → `jobs_silver` + 7 `gold_*` |
| **P3 Feature Eng + NLP** | analysis-ready features; better skill extraction (embedding/keyword/NER), embedding search | enriched `jobs_silver`, skill index | P2 | ⬜ |
| **P4 Market & Statistical Analysis** | EDA + **market share % per family** + geo/company/seniority comparisons | EDA notebooks, stat tables, figures | P2 (job_family), P3 | ⬜ |
| **P5 Insight ML (unsupervised)** | association rules (skill combos), clustering (job/skill/company), topic modeling (JD) | rules/clusters/topics + interpretations | P3, P4 | ⬜ |
| **P6 Recommendation** | skill recommendation, similar-job (embedding similarity) | recommender outputs + eval | P3 | ⬜ |
| **P7 Dashboard** | Streamlit, drill-down Domain→Sub-domain→Family | running dashboard + screenshots | P4, P5, P6 | ⬜ |
| **P8 Report & Insight** | descriptive→diagnostic→prescriptive; seeker & recruiter takeaways | final report + figures | P4–P7 | ⬜ |
| **P9 Forecasting (CONDITIONAL)** | job-count / skill-demand over time | — | needs ≥ several snapshots | ⛔ deferred (1 snapshot) |

**Dependency chain:** P0→P1→**P2**→{P3,P4}→{P5,P6}→P7→P8.  P2 is the gate for all analysis.

## ⭐ P2 — Job Family Labeling Engine (standalone product)
Designed as a reusable module, decoupled from this project's data:
```
job_family_engine/
  taxonomy/   taxonomy_v1.yml (hierarchical domain→subdomain→family; VERSIONED) + CHANGELOG.md
  rules/      rules_v1.yml  (per-family keyword config — in YAML, NOT in code)
  embeddings/ prototypes.py (family prototype vectors from taxonomy + example skills/titles)
  llm/        providers.py (modular adapters: cerebras/mistral/groq + GPT/Claude/Gemini pluggable)
              classify.py  (per-LLM → {job_family, confidence, reasoning})
  voting/     vote.py       (majority / weighted voting; tie → manual review)
  confidence/ score.py      (combine tier signals → confidence_score)
  reviewer/   queue.py      (export low-confidence to review_queue, ingest decisions)
  engine.py   cascade orchestrator → `engine.predict(job) -> {domain, subdomain, job_family,
              confidence_score, labeling_method, llm_votes, reasoning, review_status}`
  evaluate.py KPI report
```
**Cascade (cheap→expensive; only escalate when unsure):**
1. **Tier-1 Rule/Keyword** (title+skills, YAML config) → accept if very high confidence (`method=rule`).
2. **Tier-2 Embedding similarity** (title+skills+JD vs family prototypes) → accept if above threshold (`method=embedding`).
3. **Tier-3 LLM ensemble** (reads title+JD+responsibilities+requirements+skills); each LLM returns
   {family, confidence, reasoning} → **majority/weighted voting** → `method=llm_vote`. Strong
   disagreement → `review_status=manual_review`.
**Taxonomy:** versioned (`taxonomy_v1/v2/…`), hierarchical (Domain → Sub-domain → Family), **family
count NOT hardcoded** — derived from corpus title/skill frequency + market references (ESCO, O*NET,
WEF, ITviec/VNW/TopCV/LinkedIn). Starting domains: Analytics · Engineering · AI/ML · Platform ·
Governance · Leadership · Other. Adding/editing families = edit YAML, **no code change**.
**Metadata stored per job:** domain, subdomain, job_family, confidence_score, labeling_method,
llm_votes, reasoning, review_status.
**Engine KPIs (evaluate.py):** coverage, confidence distribution, inter-LLM agreement, unknown rate,
manual-review rate, label distribution, **spot-check accuracy** (human-verified sample).

## 6. Removed (permanently / from scope)
- ❌ **All salary** (estimate/predict/infer/approximate/trend) — dataset has no salary.
- ❌ **Supervised role classifier as a deliverable** (`train_eval.py`/`splits.py`) — we LABEL this
  dataset, not train a predictor; optional only as a future cheap fast-labeler (distillation).
- ❌ **Benchmark formalism** (golden split, IAA/Krippendorff/MASI, bias-audit, multi-setting eval) — research overhead.
- ❌ **Forecasting now** — deferred until multiple snapshots exist.
- ❌ **(v1.1) Over-engineering rejected:** dedicated log-file infra (`logs/*.log`); performance KPIs
  (dashboard load time, pipeline runtime, cache-hit); an error-handling framework section; a 4-file
  config "system"; the "Feature Store" concept; a heavy integration/e2e test harness; redundant docs
  (Architecture/Pipeline/Dashboard/API.md). Reason: this is a Data Analytics course project — these
  add software-engineering complexity without serving the North Star.

## 7. Added (new vs old plan)
- ⭐ Standalone **Job Family Labeling Engine** (`engine.predict(job)`), hierarchical versioned taxonomy,
  3-tier cascade, multi-LLM voting + confidence + reviewer, engine KPIs.
- NLP layer (skill extraction/embedding/keyword), Recommendation (skill/similar-job), drill-down Dashboard.
- Market-share-by-family analysis as a first-class output.

## 8. Technical risks
- **Sparsity:** ~1700 jobs ÷ many families → family-level % noisy. Mitigate: report at Domain/Sub-domain
  (robust), drill to family with caveats + min-support thresholds.
- **LLM cost/quota/rate-limits** (Mistral ~1 RPS, OpenRouter ~50/day). Mitigate: cascade (LLM only on
  the unsure remainder) + caching + modular providers + Groq tiebreaker.
- **Boundary disagreement/bias** (AIE↔MLE, BA↔DA): consensus + confidence + manual-review queue.
- **Field reliability:** experience/education/employment_type exist only on SOME sources → do NOT build
  ML on weak/partial labels (same trap as salary). Use only reliable fields (title/JD/skills/location/seniority/company/posted_date).
- **Embeddings cluster by language/source not role** → labeling must read content (LLM), not rely on clusters.
- **Representativeness:** scraped convenience sample → document sampling bias in the report.
- **Taxonomy drift:** market evolves (GenAI/LLM roles) → versioned taxonomy.

## 9. Project assumptions
- Dataset ≈ 1701 jobs, **1 snapshot**, no salary. Reliable fields: title, company, location/city/region,
  skills, JD/description, seniority(derived), work_model/remote, language_req, company_type, posted_date.
  Partial/unreliable: years-experience, education, employment_type (source-dependent).
- LLM APIs available via `.env` (Cerebras/Mistral/Groq now; GPT/Claude/Gemini pluggable). Keys not committed.
- `job_family` (+hierarchy) is the analytical unit for all downstream work.
- VN-market focus; international taxonomies (ESCO/O*NET/WEF) as reference only.

## 10. Implementation roadmap (small steps; code only after approval)
- **B1** Taxonomy research → `taxonomy_v1.yml` (data-informed: corpus title/skill freq + market refs); user approves.
- **B2** Tier-1 rule engine (`rules_v1.yml` + `rules/`); measure % auto-labeled high-confidence.
- **B3** Tier-2 embedding similarity for the unsure remainder.
- **B4** Tier-3 LLM ensemble (modular providers) → {family,confidence,reasoning}.
- **B5** Voting + confidence + reviewer queue; `engine.predict(job)` API + metadata.
- **B6** `evaluate.py` KPIs + human spot-check → quality report.
- **B7** Integrate `job_family` into `jobs_silver` → re-build GOLD by family → **market-share %**.
- **B8** NLP layer (skill extraction/embedding search).
- **B9** Analysis: EDA + statistics; Insight-ML (association rules, clustering, topic modeling).
- **B10** Recommendation (skill/similar-job).
- **B11** Dashboard (Streamlit) + Report.
- *(B12 Forecasting — only if ≥ several snapshots later.)*

## 11. Conventions, artifacts & process (v1.1 — kept/modified from review)
**Engine ↔ Project boundary:** `job_family_engine/` is a self-contained software component (`engine.predict(job)`),
decoupled from this dataset and reusable elsewhere. The analysis project only **consumes** its output
(`job_family` + hierarchy + metadata) — it never reaches into engine internals.

**Gold layer (family-centric spec):** `gold_jobs` (job-level w/ job_family), `gold_market_share`
(family/domain share %), `gold_family_skill` (skill share per family), `gold_company`, `gold_location`,
`gold_seniority`. (Re-shape the existing 7 Gold tables around `job_family`; don't add redundant ones.)

**NLP outputs (only what analysis uses):** normalized skills, key-phrases, TF-IDF, skill frequency,
skill co-occurrence matrix, skill/JD embeddings. Stored as **feature-engineering outputs** (a folder of
artifacts — NOT a "feature store").

**P4 analysis menu:** descriptive stats · cross-tabs · distributions · **market share %** · company ·
location (HN/HCM/ĐN) · seniority · skill/technology **ranking** *(snapshot ranking, NOT a temporal trend
— only 1 snapshot)*.

**Statistical testing (only when assumptions hold):** chi-square / Fisher (categorical), Mann-Whitney /
Kruskal-Wallis (non-parametric), ANOVA (if valid); always report **effect size + confidence interval**.
Never force a test; no p-hacking.

**Insight Framework (every report insight):** Observation → Evidence → Visualization → Interpretation →
Business meaning → Recommendation → Limitation. (Operationalizes "every insight must state value to a
job-seeker or recruiter.")

**Recommendation scope:** (1) Job-Seeker — skill recommendation + similar-job (embedding similarity) +
skill-gap view; (2) Recruiter — skill landscape per family. *(Career-transition recommendation = deferred:
heavier, weaker signal.)*

**Dashboard pages (~8):** Overview · Job Family & Market Share · Skills · Companies · Locations ·
Recommendation · Engine Quality (KPIs) · About Dataset. Drill-down Domain→Sub-domain→Family.

**KPIs (analysis-quality only):** labeling coverage, unknown rate, manual-review rate, inter-LLM
agreement, label distribution, **spot-check accuracy**. *(No performance/ops KPIs.)*

**Config & reproducibility (light):** taxonomy/rules/providers/thresholds in **YAML/.env (no hardcode)** —
reuse existing `ref/` + `.env`; pinned deps in `pyproject.toml`; `.env.example`; **fixed random seeds**
for sampling/clustering; run commands in README. *(Makefile optional.)*

**Project structure (lean):** `pipeline/` (ingest/transform/utils), `job_family_engine/`, `analysis/`,
`dashboard/`, `reports/`, `docs/`, `data/`, `tests/`. (No separate `feature_store/`/`configs/`/`logs/`.)

**Docs (lean set):** `MASTER_PLAN.md`, `docs/DATA_DICTIONARY.md`, `docs/quality_report.md`,
`docs/TAXONOMY.md`, `job_family_engine/README.md` (engine usage). Architecture/Pipeline live in MASTER_PLAN.

**Testing (right-sized):** keep existing 21 pytest + add **unit tests for the engine's deterministic
parts** (rule matching, voting, taxonomy parse, metadata schema). No integration/e2e harness.

**Dev workflow (per phase):** Design → Review → **Approval** → Implement → Validate → Document.
No phase is coded before approval.

> After approval: update PROJECT_STATUS.md + WORK_DIVISION.md to match this Master Plan, then implement phase by phase.
