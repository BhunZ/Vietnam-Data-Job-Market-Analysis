# Data Quality Report — `jobs_silver`

> Generated from `warehouse.duckdb` (Silver layer). Snapshot: 1 (point-in-time). No salary field.

## Volume & source contribution
- **Total rows:** 1701 (1 snapshot, all active).
- **By source:** VietnamWorks 790 (46%) · CareerViet 382 (22%) · ITviec 286 (17%) · TopCV 99 (6%) · TopDev 82 (5%) · Glints 62 (4%).
- ⚠️ **Selection bias:** convenience sample of scrapable sources (VNW dominates). Not a census of the VN market — state this in the report.

## Missing / coverage
| Field | Missing | Note |
|---|--:|---|
| title_clean | 0% | always present |
| company | 1.1% (19) | |
| city | 8.9% (152) | remote/unspecified; `city resolved` 1549/1701 |
| seniority | 0% | derived (default Mid when no signal — read as "Mid/unknown") |
| company_type | 0% | rule-classified |
| posted_date | 0% | `effective_date` = posted_date or first_seen (see PROJECT_STATUS §11) |
| skills | **12.4% (211) zero-skill** | some sources/JDs lack explicit skill tags; extracted from JD where possible |

## Duplicates & dedup
- **Cross-source duplicates:** 112 (6.6%) flagged via `is_duplicate_of` (rapidfuzz on company+title+city). Analysis filters `is_duplicate_of IS NULL`.
- **Within-source dedup:** by `source_job_id` at ingest (CDC).

## Normalization coverage
- Skills → canonical via bilingual dictionary (`ref/skills_dictionary.yml`); unmapped tokens logged to `data/quality/unmapped_skills.csv`.
- Location → 14 VN cities + region (North/Central/South) + remote flag.
- Seniority → {Intern, Junior, Mid, Senior, Lead, Manager} (title + source label).
- Company → legal-suffix stripped key + type {product, outsourcing, bank/finance, …}.

## Known limitations (carry into report)
- **No salary** (not in data). **1 snapshot** → no temporal trend/forecast.
- `posted_date` semantics differ by source (absolute vs "N days ago" vs "updated").
- Partial fields NOT used for analysis: years-experience, education, employment_type (only some sources).
- Role labels: now from the **Job Family Labeling Engine** (LLM consensus) — see `docs/labeling_kpi.md`; legacy rule `role_category` kept as baseline.
