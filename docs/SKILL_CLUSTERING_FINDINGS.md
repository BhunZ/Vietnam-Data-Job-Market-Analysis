# Skill Clustering Findings

Milestone P5 deliverable: clustering skill profiles to test whether Data/AI jobs form natural skill groups, then compare those groups with `job_family`.

## Business Question

Do Vietnamese Data/AI job postings naturally separate into skill-profile clusters, and where do those clusters align or blur across labeled job families?

## Metric

| Metric | Meaning |
|---|---|
| `silhouette_cosine` | Cluster separation on normalized skill vectors; higher is better |
| `dominant_family_share` | Share of the largest `job_family` inside a cluster |
| `most_common_skills` | Highest within-cluster share — what these postings ask for |
| `most_distinctive_skills` | Highest lift versus the whole clustered population (share >= 20% floor) — what makes the cluster different. A skill can be common WITHOUT being distinctive, and vice versa |
| `mean_silhouette` | Cluster cohesion, cosine. Below ~0.10 the members sit as close to another centroid as to their own |
| `pct_negative_silhouette` | % of members actually closer to a different cluster |
| `mean_n_skills` | Mean tag count. Near 1-2 means the cluster is grouping thinly-tagged postings, not roles |
| `quality_flag` | `low_confidence` when `mean_silhouette` < 0.10 or `mean_n_skills` < 3 — do not narrate these as market findings |

## Table

Input table: `jobs_silver`

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

Feature input: `skills` only. `job_family` is used after clustering for interpretation, not as a feature.

## Pipeline

Script: `analysis/skill_clustering.py`

Outputs:

| Artifact | Purpose |
|---|---|
| `analysis/outputs/skill_clusters.csv` | One row per clustered job |
| `analysis/outputs/skill_cluster_summary.csv` | Cluster size, dominant family, top skills |
| `analysis/outputs/skill_cluster_k_selection.csv` | Evidence for selected k |

## Run Evidence

- Official analysis base: 720 jobs
- Clustered jobs with usable skills after `min_skill_n=10`: 709
- k used for this report: 8

> **How much structure is really there:** Silhouette (cosine) stays within 0.125-0.174 across k=2..20 — conventionally **no substantial cluster structure**. argmax(silhouette) = k=20. argmax sits at the edge of the search range, so it reflects where the search stopped, not an optimum. Clusters below are therefore a descriptive summary of skill-tag co-occurrence, NOT evidence that the market separates into that many natural roles. This report uses k=8 for interpretability.

### K Selection

| k | silhouette_cosine | calinski_harabasz | davies_bouldin |
|---:|---:|---:|---:|
| 2 | 0.1246 | 51.93 | 3.6785 |
| 3 | 0.1488 | 51.26 | 3.0500 |
| 4 | 0.1648 | 48.17 | 3.0639 |
| 5 | 0.1585 | 42.54 | 2.8841 |
| 6 | 0.1647 | 39.01 | 2.6758 |
| 7 | 0.1609 | 35.51 | 2.5301 |
| 8 | 0.1571 | 33.32 | 2.8431 |
| 9 | 0.1580 | 32.21 | 2.8111 |
| 10 | 0.1659 | 31.12 | 2.5811 |
| 11 | 0.1559 | 29.08 | 2.5947 |
| 12 | 0.1641 | 28.11 | 2.6772 |
| 13 | 0.1678 | 27.26 | 2.5396 |
| 14 | 0.1674 | 26.80 | 2.6392 |
| 15 | 0.1687 | 25.86 | 2.5808 |
| 16 | 0.1725 | 25.00 | 2.4841 |
| 17 | 0.1661 | 23.86 | 2.5450 |
| 18 | 0.1604 | 23.39 | 2.5395 |
| 19 | 0.1740 | 22.87 | 2.4922 |
| 20 | 0.1741 | 22.13 | 2.4576 |

### Cluster Summary

| Cluster | Jobs | % | Dominant family | Dominant family share | Top skills |
|---:|---:|---:|---|---:|---|
| 5 | 144 | 20.3 | `DATA_ENGINEER` | 68.1 | 0.089 | 14.74 | low_confidence | SQL (77%); Data Warehouse (58%); Python (56%); Database (53%); ETL (53%); Data Management (51%) | dbt (22%, lift 4.2); Hadoop (22%, lift 4.1); Airflow (33%, lift 4.1); Kafka (27%, lift 4.0); Spark (44%, lift 3.9); ELT (34%, lift 3.8) |
| 6 | 124 | 17.5 | `DATA_ANALYST` | 38.7 | 0.053 | 10.62 | low_confidence | SQL (80%); Power BI (77%); Reporting (73%); Data Analysis (69%); Python (55%); Statistics (50%) | Looker (21%, lift 4.0); Tableau (49%, lift 3.8); Data Visualization (40%, lift 3.7); Power BI (77%, lift 3.1); Statistics (50%, lift 3.0); Business Intelligence (20%, lift 2.5) |
| 7 | 113 | 15.9 | `AI_ENGINEER` | 60.2 | 0.064 | 9.31 | low_confidence | AI (73%); LLM (67%); Python (66%); Machine Learning (65%); API (60%); Database (39%) | JavaScript (22%, lift 5.2); LLM (67%, lift 4.0); AI (73%, lift 3.5); NLP (21%, lift 3.1); API (60%, lift 3.1); Git (27%, lift 2.6) |
| 0 | 93 | 13.1 | `BUSINESS_ANALYST` | 84.9 | 0.3 | 3.63 | ok | Business Analysis (88%); English (45%); Agile (38%); ERP (26%); SQL (25%); Data Analysis (20%) | Business Analysis (88%, lift 5.0); Agile (38%, lift 3.7); ERP (26%, lift 3.2); English (45%, lift 1.3); SQL (25%, lift 0.5); Data Analysis (20%, lift 0.5) |
| 2 | 78 | 11.0 | `DATA_ANALYST` | 39.7 | 0.215 | 6.79 | ok | Excel (100%); Data Analysis (73%); Reporting (69%); Power BI (59%); SQL (56%); English (38%) | Excel (100%, lift 6.8); Power BI (59%, lift 2.4); Data Analysis (73%, lift 1.8); Reporting (69%, lift 1.8); Tableau (23%, lift 1.8); Statistics (22%, lift 1.3) |
| 3 | 63 | 8.9 | `AI_ENGINEER` | 60.3 | 0.274 | 13.68 | ok | Python (97%); PyTorch (92%); TensorFlow (87%); Machine Learning (86%); AI (68%); Deep Learning (65%) | PyTorch (92%, lift 11.1); TensorFlow (87%, lift 10.9); scikit-learn (44%, lift 9.3); Computer Vision (48%, lift 7.3); Deep Learning (65%, lift 7.2); NLP (33%, lift 4.9) |
| 1 | 55 | 7.8 | `BUSINESS_ANALYST` | 36.4 | 0.261 | 2.55 | low_confidence | Data Analysis (89%); Reporting (49%); English (22%); SQL (13%); Data Management (11%); Statistics (9%) | Data Analysis (89%, lift 2.2); Reporting (49%, lift 1.3); English (22%, lift 0.6) |
| 4 | 39 | 5.5 | `DATA_GOVERNANCE` | 48.7 | 0.217 | 6.08 | ok | Data Governance (90%); Data Quality (54%); Data Analysis (49%); Data Science (33%); Data Management (31%); SQL (28%) | Data Governance (90%, lift 8.3); Data Quality (54%, lift 3.3); Data Science (33%, lift 1.6); Data Warehouse (26%, lift 1.3); Data Analysis (49%, lift 1.2); Data Management (31%, lift 1.1) |

## Interpretation

Clustering is used as an unsupervised check, not a replacement for the Job Family Engine. A high dominant-family share means a cluster's skill profile is close to one family. A mixed cluster means the market asks for overlapping skills across families.

## Recommendation

Use the cluster summary together with association rules:

1. Treat repeated top skills inside large clusters as learning bundles.
2. Use mixed clusters to explain why some roles are hard to separate by title alone.
3. Keep `job_family` as the reporting unit, and use clusters as supporting evidence for skill pathways.

## Limitations

- Skill tags record whether a JD mentions a skill, not required proficiency.
- Jobs without usable skill tags after vocabulary filtering are excluded from clustering.
- KMeans forces every job into a cluster, so small or hybrid clusters should be interpreted cautiously.
- This is one snapshot only; do not interpret clusters as a market trend or forecast.
- Salary is not present in the repo, so clusters cannot imply compensation differences.
