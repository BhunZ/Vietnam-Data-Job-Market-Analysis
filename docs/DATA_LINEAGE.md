# Data Lineage

Milestone 4 deliverable: lineage from source files to warehouse serving tables.

```mermaid
flowchart LR
    sources["Job boards\nITviec / VietnamWorks / CareerViet / TopDev / Glints / TopCV"]
    bronze["Bronze files\n/data/bronze/<source>/latest.jsonl"]
    jobs["jobs\nGrain: source + source_job_id"]
    obs["job_observations\nGrain: source + source_job_id + snapshot_date"]
    silver["jobs_silver\nGrain: job_id"]
    label["job_family.parquet (engine.py tạo, refine.py cập nhật 30 dòng)\nGrain: job_id"]
    engine["Job Family Engine\nrule -> embedding -> LLM"]
    silver_family["jobs_silver + job_family columns\nGrain: job_id"]

    legacy["Legacy Gold\njob_family-based"]
    skill_demand["skill_demand\nskill"]
    role_skill["role_skill_matrix\njob_family x skill"]
    seniority["seniority_progression\nseniority x skill"]
    role_location["role_by_location\njob_family x region x city"]
    company_role["company_type_demand\ncompany_type x job_family"]
    skill_cooc["skill_cooccurrence\nskill_a x skill_b"]
    trend["trend\nsnapshot_date x skill"]

    family["Family Gold\njob_family-based"]
    gold_jobs["gold_jobs\njob"]
    market["gold_market_share\njf_domain x job_family"]
    family_skill["gold_family_skill\njob_family x skill"]
    gold_company["gold_company\ncompany_type x job_family"]
    gold_location["gold_location\nregion x city x job_family"]
    gold_seniority["gold_seniority\nseniority x job_family"]
    gold_cooc["gold_skill_cooccurrence\nskill_a x skill_b"]

    sources --> bronze
    bronze --> jobs
    bronze --> obs
    jobs --> silver
    silver --> legacy
    obs --> trend
    silver --> trend

    silver --> engine
    engine --> label
    label --> silver_family
    silver --> silver_family
    silver_family --> family

    legacy --> skill_demand
    legacy --> role_skill
    legacy --> seniority
    legacy --> role_location
    legacy --> company_role
    legacy --> skill_cooc

    family --> gold_jobs
    family --> market
    family --> family_skill
    family --> gold_company
    family --> gold_location
    family --> gold_seniority
    family --> gold_cooc
```

## Evidence

- `jobs` and `job_observations` are created by `pipeline/transform/load.py`.
- `jobs_silver` is created by `pipeline/transform/silver.py`.
- Legacy Gold tables are created by `pipeline/transform/gold.py`.
- Family Gold tables are created by `job_family_engine/integrate.py`.
- `job_family.parquet (engine.py tạo, refine.py cập nhật 30 dòng)` is created by `job_family_engine/engine.py`.

