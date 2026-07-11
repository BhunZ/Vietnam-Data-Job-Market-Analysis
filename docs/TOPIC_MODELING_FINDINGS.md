# Topic Modeling Findings

Milestone P5 deliverable: NMF topic modeling on job-description text to surface hidden technology, task, and requirement themes beyond normalized skill tags.

## Business Question

Beyond normalized skill tags, what hidden technology, task, or requirement themes appear in Vietnamese Data/AI job descriptions?

## Metric

| Metric | Meaning |
|---|---|
| `topic_id` | Exploratory NMF topic identifier |
| `top_terms` | Highest-weight TF-IDF terms for the topic |
| `dominant_topic` | Topic with the largest NMF weight for a job |
| `topic_weight` | NMF weight of the dominant topic for a job |
| `pct_jobs` | Share of modeled jobs whose dominant topic is this topic |
| `dominant_family_share` | Share of the largest `job_family` inside the topic |

## Table

Input tables: `jobs_silver` joined with `jobs` on `(source, source_job_id)`.

Official analysis filter:

```sql
job_family IS NOT NULL
AND job_family != 'OTHER'
AND is_active
AND is_duplicate_of IS NULL
```

Text input: `title_clean` + normalized `skills` + `jobs.description_raw`, with light boilerplate trimming. `job_family` is used only after modeling for interpretation.

## Pipeline

Script: `analysis/topic_modeling.py`

Outputs:

| Artifact | Purpose |
|---|---|
| `analysis/outputs/topic_terms.csv` | Top terms per topic |
| `analysis/outputs/job_topics.csv` | One row per modeled job with dominant topic |
| `analysis/outputs/topic_summary.csv` | Topic size, dominant family/domain, representative terms |
| `analysis/outputs/topic_k_selection.csv` | Evidence for selected topic count |

## Run Evidence

- Official analysis base: 852 jobs
- Modeled jobs with usable text: 775
- Dropped for short/empty text: 77
- TF-IDF features: 2380
- Selected topics: 5

### Topic Count Selection

`selection_score` is a lightweight interpretability proxy: topic diversity plus mean dominant-topic share, with a small penalty for larger k. It is used for reproducible exploratory reporting, not as a formal benchmark.

| k | reconstruction_error | topic_diversity | mean_dominant_topic_share | selection_score |
|---:|---:|---:|---:|---:|
| 5 | 25.3916 | 0.9600 | 0.7712 | 0.8345 |
| 6 | 25.1428 | 0.9667 | 0.7594 | 0.8238 |
| 7 | 24.9852 | 0.9714 | 0.7237 | 0.8023 |
| 8 | 24.8824 | 0.9750 | 0.6915 | 0.7816 |
| 9 | 24.7825 | 0.9556 | 0.6659 | 0.7497 |
| 10 | 24.6774 | 0.9500 | 0.6497 | 0.7299 |

### Topic Summary

| Topic | Jobs | % | Dominant family | Dominant family share | Top terms |
|---:|---:|---:|---|---:|---|
| 1 | 256 | 33.0 | `BUSINESS_ANALYST` | 30.5 | gia; ngan; te; vi; so; chi; hinh; quy; pham; hanh |
| 4 | 197 | 25.4 | `BUSINESS_ANALYST` | 25.4 | business; analytics; development; analysis; systems; performance; science; product; across; technical |
| 2 | 131 | 16.9 | `AI_ENGINEER` | 58.0 | ai; learning; machine learning; machine; llm; engineer ai; ai engineer; llm machine; python; pytorch |
| 3 | 101 | 13.0 | `DATA_ANALYST` | 56.4 | power bi; power; bi; reporting sql; reporting; data analysis; bi python; tableau; sql; analysis |
| 0 | 90 | 11.6 | `DATA_ENGINEER` | 78.9 | etl; data warehouse; warehouse; data engineer; sql; lake; spark; data lake; elt; modeling data |

## Interpretation

Topic modeling shows recurring JD themes that are not fully captured by simple market-share tables. A topic with a high dominant-family share is close to one family. A mixed topic means the same language or work theme crosses multiple job families.

## Recommendation

Use these topics as supporting evidence for learning paths and report narrative:

1. Pair topic themes with skill clustering to name practical tracks, such as BI/reporting, data engineering/cloud, and AI/ML delivery.
2. Use mixed topics to explain why some postings blur across BA, DA, DE, and AI roles.
3. Keep `job_family` as the main reporting unit; use topics only as exploratory text evidence.

## Limitations

- Topic labels are model-derived themes, not official job labels.
- JD text is bilingual and noisy; some terms may reflect generic recruiting language despite stop-word filtering.
- The model uses one snapshot only, so topics cannot be interpreted as increasing or decreasing trends.
- Salary is not available in this repo, so topics cannot imply compensation differences.
- This is unsupervised exploration, not a supervised classifier and not a replacement for `job_family`.
