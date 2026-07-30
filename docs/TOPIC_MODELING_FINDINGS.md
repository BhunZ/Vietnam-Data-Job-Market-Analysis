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
AND COALESCE(jf_review, 'resolved') NOT IN ('manual_review', 'domain_only')
```

The last clause holds out postings the labeling engine could not settle. It currently excludes 0 rows
(every posting was resolved, 30 of them via the stage-2 `refine` pass), but it is executed, so it is
printed here — the filter shown must be the filter run.

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

- Official analysis base: 720 jobs
- Modeled jobs with usable text: 720
- Dropped for short/empty text: 0
- TF-IDF features: 2500
- Selected topics: 9

### Topic Count Selection

`k` is selected on **NPMI topic coherence** (mean pairwise normalised PMI over each topic's top terms) — higher is better. `reconstruction_error` and `mean_dominant_topic_share` fall monotonically as `k` grows by construction, so they are reported for transparency but are NOT selection criteria; an earlier version selected on a weighted mix of them and could therefore only ever return the smallest `k` in the search range.

| k | npmi_coherence | reconstruction_error | topic_diversity | mean_dominant_topic_share |
|---:|---:|---:|---:|---:|
| 5 | 0.3629 | 24.6575 | 0.9600 | 0.6880 |
| 6 | 0.3832 | 24.5110 | 0.9500 | 0.6597 |
| 7 | 0.4150 | 24.3627 | 0.9429 | 0.6024 |
| 8 | 0.4341 | 24.2499 | 0.9625 | 0.5885 |
| 9 | 0.4479 | 24.1598 | 0.9556 | 0.5722 |
| 10 | 0.4374 | 24.0418 | 0.9500 | 0.5602 |

### Topic Summary

| Topic | Jobs | % | Dominant family | Dominant family share | Top terms |
|---:|---:|---:|---|---:|---|
| 1 | 183 | 25.4 | `BUSINESS_ANALYST` | 23.0 | business; systems; technical; development; performance; across; ensure; design; solutions; communication |
| 2 | 136 | 18.9 | `AI_ENGINEER` | 64.0 | ai; learning; llm; machine; machine learning; python; engineer; ai engineer; vision; pytorch |
| 3 | 95 | 13.2 | `DATA_ENGINEER` | 76.8 | lake; data warehouse; warehouse; data lake; etl; data engineer; elt; spark; lake data; airflow |
| 4 | 69 | 9.6 | `BUSINESS_ANALYST` | 94.2 | business analyst; business; analyst; business analysis; agile; erp; analyst domain; expertise business; office business; agile business |
| 7 | 64 | 8.9 | `DATA_ANALYST` | 56.2 | bi; power bi; power; tableau; data analyst; excel; sql; analyst; dashboard; reporting |
| 0 | 60 | 8.3 | `BUSINESS_ANALYST` | 25.0 | phap; thuat; tang; tao; huong; nhu; lap; cuu; nghien cuu; nghien |
| 5 | 55 | 7.6 | `RISK_FRAUD_ANALYST` | 36.4 | rui; ngan; khoi; chung; tuan; soat; thieu; khoa; data science; risk |
| 8 | 42 | 5.8 | `DATA_ENGINEER` | 31.0 | oracle; sql server; server; sql; mysql; postgresql; sql sql; database; etl; oracle postgresql |
| 6 | 16 | 2.2 | `AI_ENGINEER` | 25.0 | thoai; email; ngay; sinh gioi; chuong; ai trung; lich hen; hen; email truong; truong bat |

### Topic vs JD language and source board — READ THIS BEFORE NAMING ANY TOPIC

| topic | n | VI% | careerviet | glints | itviec | topcv | topdev | vietnamworks | nguồn lớn nhất |
|---|--:|--:|--:|--:|--:|--:|--:|--:|---|
| 0 | 60 | **100%** | 12 | 12 | 6 | 11 | 1 | 18 | vietnamworks 30% |
| 1 | 183 | **10%** | 25 | 7 | 37 | 11 | 8 | 95 | vietnamworks 52% |
| 2 | 136 | **50%** | 16 | 18 | 68 | 5 | 2 | 27 | itviec 50% |
| 3 | 95 | 68% | 19 | 7 | 21 | 27 | 4 | 17 | topcv 28% |
| 4 | 69 | **62%** | 2 | 1 | 38 | 0 | 0 | 28 | itviec 55% |
| 5 | 55 | **98%** | 15 | 0 | 2 | 1 | 1 | 36 | vietnamworks 65% |
| 6 | 16 | **100%** | 0 | 0 | 10 | 2 | 3 | 1 | itviec 62% |
| 7 | 64 | 80% | 10 | 6 | 1 | 25 | 4 | 18 | topcv 39% |
| 8 | 42 | 83% | 11 | 0 | 7 | 9 | 0 | 15 | vietnamworks 36% |

Bold = the topic is >=90% or <=10% Vietnamese, or one job board supplies >=50% of it. Those topics are
substantially an artifact of **which language the JD was written in** or **which board it came from**, not
a theme in the labour market. NMF works on a bag of words and the NPMI coherence score does not penalise a
language split, so this table is the only thing standing between a language artifact and a "finding".
Do not name a bold topic as a market theme.

## Interpretation

Topic modeling shows recurring JD themes that are not fully captured by simple market-share tables. A topic with a high dominant-family share is close to one family. A mixed topic means the same language or work theme crosses multiple job families.

## Recommendation

Use these topics as supporting evidence for learning paths and report narrative:

1. Pair topic themes with skill clustering to name practical tracks, such as BI/reporting, data engineering/cloud, and AI/ML delivery.
2. Use mixed topics to explain why some postings blur across BA, DA, DE, and AI roles.
3. Keep `job_family` as the main reporting unit; use topics only as exploratory text evidence.

## Limitations

- Topic labels are model-derived themes, not official job labels.
- **Several topics separate by JD LANGUAGE rather than by content** — see the topic-vs-language table
  above and check it before quoting any topic. This is measured, not hypothetical.
- JD text is bilingual and noisy; some terms may reflect generic recruiting language despite stop-word filtering.
- The model uses one snapshot only, so topics cannot be interpreted as increasing or decreasing trends.
- Salary is not available in this repo, so topics cannot imply compensation differences.
- This is unsupervised exploration, not a supervised classifier and not a replacement for `job_family`.
