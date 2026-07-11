# Skill Clustering Findings

Milestone P5 deliverable: clustering skill profiles to test whether Data/AI jobs form natural skill groups, then compare those groups with `job_family`.

## Business Question

Do Vietnamese Data/AI job postings naturally separate into skill-profile clusters, and where do those clusters align or blur across labeled job families?

## Metric

| Metric | Meaning |
|---|---|
| `silhouette_cosine` | Cluster separation on normalized skill vectors; higher is better |
| `dominant_family_share` | Share of the largest `job_family` inside a cluster |
| `top_skills` | Skills with high within-cluster share, with lift versus the overall clustered population |

## Table

Input table: `jobs_silver`

Official analysis filter:

```sql
job_family IS NOT NULL
AND job_family != 'OTHER'
AND is_active
AND is_duplicate_of IS NULL
```

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

- Official analysis base: 852 jobs
- Clustered jobs with usable skills after `min_skill_n=10`: 806
- Selected k: 8

### K Selection

| k | silhouette_cosine | calinski_harabasz | davies_bouldin |
|---:|---:|---:|---:|
| 3 | 0.1387 | 64.14 | 3.0509 |
| 4 | 0.1534 | 59.87 | 2.9561 |
| 5 | 0.1669 | 56.99 | 2.6739 |
| 6 | 0.1835 | 53.61 | 2.6429 |
| 7 | 0.1885 | 50.09 | 2.4693 |
| 8 | 0.1905 | 47.68 | 2.3026 |

### Cluster Summary

| Cluster | Jobs | % | Dominant family | Dominant family share | Top skills |
|---:|---:|---:|---|---:|---|
| 2 | 192 | 23.8 | `DATA_ENGINEER` | 61.5 | SQL (71%, lift 1.5); Data Warehouse (53%, lift 2.9); Python (51%, lift 1.2); ETL (48%, lift 2.9); Big Data (39%, lift 2.4); Reporting (39%, lift 1.0) |
| 4 | 180 | 22.3 | `AI_ENGINEER` | 61.7 | Machine Learning (75%, lift 2.6); Python (75%, lift 1.8); AI (73%, lift 3.7); LLM (59%, lift 4.0); English (41%, lift 1.1); Deep Learning (36%, lift 4.1) |
| 3 | 159 | 19.7 | `DATA_ANALYST` | 40.3 | Power BI (84%, lift 3.4); SQL (81%, lift 1.7); Data Analysis (78%, lift 1.7); Reporting (73%, lift 1.9); Tableau (55%, lift 4.0); Python (52%, lift 1.2) |
| 1 | 80 | 9.9 | `BUSINESS_ANALYST` | 43.8 | Excel (100%, lift 6.2); Data Analysis (65%, lift 1.4); Reporting (48%, lift 1.2); English (44%, lift 1.2); SQL (35%, lift 0.8); Power BI (34%, lift 1.4) |
| 0 | 59 | 7.3 | `BUSINESS_ANALYST` | 30.5 | English (100%, lift 2.8); Data Analysis (44%, lift 1.0); Reporting (24%, lift 0.6); SQL (19%, lift 0.4); Python (14%, lift 0.3); Data Governance (7%, lift 0.7) |
| 7 | 59 | 7.3 | `BUSINESS_ANALYST` | 47.5 | Data Analysis (100%, lift 2.2); Statistics (5%, lift 0.3); Business Intelligence (3%, lift 0.5); SQL (3%, lift 0.1); C++ (2%, lift 0.7); Data Governance (2%, lift 0.2) |
| 6 | 40 | 5.0 | `BUSINESS_ANALYST` | 75.0 | Agile (100%, lift 10.6); English (75%, lift 2.1); SQL (35%, lift 0.8); Data Analysis (30%, lift 0.7); Azure (18%, lift 1.5); Reporting (15%, lift 0.4) |
| 5 | 37 | 4.6 | `BUSINESS_ANALYST` | 40.5 | Reporting (100%, lift 2.6); Data Analysis (68%, lift 1.5); SQL (8%, lift 0.2); Data Governance (5%, lift 0.5); Oracle (5%, lift 0.5); Big Data (5%, lift 0.3) |

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
