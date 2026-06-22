# Data Dictionary

Schema of the tables the teammate's analysis consumes (in `data/warehouse.duckdb`).
`derived` = computed by the pipeline; `raw` = as scraped. No salary field anywhere (by design).

## Table: `jobs_silver` (one row per job, cleaned)
| Field | Type | Null | Src | Description |
|---|---|---|---|---|
| job_id | VARCHAR | no | derived | `source:source_job_id` (primary key) |
| source | VARCHAR | no | raw | vietnamworks/careerviet/itviec/topcv/topdev/glints |
| title_clean | VARCHAR | no | derived | title, bracket-noise stripped |
| company / company_key | VARCHAR | 1% | raw/derived | company; legal-suffix-stripped key (dedup) |
| **job_family** | VARCHAR | no* | derived | ⭐ Job Family Engine label (e.g. DATA_ENGINEER); `OTHER` = not a data role |
| jf_domain / jf_subdomain | VARCHAR | no* | derived | taxonomy roll-up levels (Analytics/Data Engineering/AI-ML/…) |
| jf_confidence | DOUBLE | no* | derived | 0–1 labeling confidence |
| jf_method | VARCHAR | no* | derived | rule / embedding / llm_vote / failed |
| jf_review | VARCHAR | no* | derived | resolved / manual_review |
| role_category | VARCHAR | no | derived | **legacy** rule label (baseline only; superseded by job_family) |
| seniority | VARCHAR | no | derived | Intern/Junior/Mid/Senior/Lead/Manager (Mid = also "unknown") |
| city / region | VARCHAR | 9% | derived | VN city + North/Central/South |
| remote_flag | BOOL | no | derived | remote/hybrid mentioned |
| skills | JSON(list) | no | derived | canonical skills (may be empty; 12% zero-skill) |
| n_skills | INT | no | derived | len(skills) |
| language_req | JSON(list) | no | derived | subset of {EN, JP, KO} |
| company_type | VARCHAR | no | derived | product/outsourcing/bank_finance/… |
| posted_date / effective_date | DATE | no | derived | site date / COALESCE(posted, first_seen) |
| first_seen_date / last_seen_date | DATE | no | derived | CDC observation window |
| is_active | BOOL | no | derived | still seen in latest scrape |
| is_duplicate_of | VARCHAR | yes | derived | survivor job_id if cross-source duplicate (filter IS NULL) |

\* populated after `python -m pipeline integrate`.
**Analysis filter:** `job_family != 'OTHER' AND is_active AND is_duplicate_of IS NULL`.

## Family Gold tables (built by `integrate`; analysis-ready)
| Table | Grain | Key columns |
|---|---|---|
| `gold_jobs` | job | job_id, job_family, jf_domain, jf_subdomain, seniority, city, region, company, company_type |
| `gold_market_share` | family | jf_domain, job_family, n, **pct** (% of Data/AI jobs) |
| `gold_family_skill` | family×skill | job_family, skill, n, share_in_family |
| `gold_company` | company_type×family | company_type, job_family, n |
| `gold_location` | region×city×family | region, city, job_family, n |
| `gold_seniority` | seniority×family | seniority, job_family, n |
| `gold_skill_cooccurrence` | skill pair | skill_a, skill_b, n (learning-path edges) |

## Engine output: `data/labeling/job_family.parquet`
`job_id, job_family, domain, subdomain, confidence_score, labeling_method, llm_votes (JSON), reasoning, review_status, taxonomy_version`.

## Taxonomy: `job_family_engine/taxonomy/taxonomy_v1.yml`
Hierarchical Domain → Sub-domain → Family (21 families). See `docs/TAXONOMY.md`.
