# Job Family Labeling Engine

A standalone, reusable engine that labels a job posting with a hierarchical **job family**
(Domain → Sub-domain → Family) from `title + JD + skills`, via a 3-tier cascade with confidence
and review status. Decoupled from this project's warehouse — reusable on any job dataset.

## Usage
```python
from job_family_engine.engine import predict

job = {
    "job_id": "x:1",
    "content_hash": "abc",            # stable id for caching (any unique string)
    "title": "Senior Data Engineer",
    "skills": ["SQL", "Spark", "Airflow"],
    "jd": "Build and operate ETL pipelines, data warehouse on AWS ...",
    "role_view": "...",               # optional: title+skills+JD text (for embedding)
}
result = predict(job)
# {job_family, domain, subdomain, confidence_score, labeling_method,
#  llm_votes, reasoning, review_status, taxonomy_version}
```
Label a whole corpus (`data/dataset/text/jobs_text.parquet`):
```bash
python -m pipeline label        # → data/labeling/job_family.parquet
python -m pipeline label-kpi    # → docs/labeling_kpi.md + spot_check.csv
python -m pipeline integrate    # → jobs_silver.job_family + family Gold tables
```

## Cascade (cheap → expensive; escalate only when unsure)
1. **`rules.py`** — high-confidence title keyword match (config: taxonomy aliases). Title-only (no
   skill↔role collision); separators normalized.
2. **`embed_match.py`** — multilingual-e5 cosine vs family prototypes; accept only if confident + clear margin.
3. **`llm_judge.py`** — multi-LLM ensemble (providers in `pipeline/dataset/llm_clients.py`), each returns
   {job_family, confidence, reasoning}; `engine.py` does majority/weighted voting + confidence + reviewer.

## Configuration (no hardcoding)
- **Taxonomy:** `taxonomy/taxonomy_v1.yml` (versioned; families + aliases + skills). Add/edit families here.
- **LLM providers/keys:** `pipeline/dataset/llm_clients.py` + `.env` (Cerebras/Mistral/Groq; pluggable GPT/Claude/Gemini).
- **Thresholds:** `embed_match.py` (ACCEPT_THRESHOLD/MARGIN), `engine.py` (RULE_MIN_CONF).

## Metadata & KPIs
Every label carries provenance (method, votes, reasoning, review_status). `evaluate.py` reports
coverage, method mix, manual-review rate, inter-LLM agreement, confidence distribution, family
distribution, and emits a spot-check sample for human accuracy verification.

> This engine produces LABELS for analysis. It is **not** a trained classifier (no train/test/macro-F1)
> — that is intentionally out of scope (Data Analytics project). See `MASTER_PLAN.md`.
