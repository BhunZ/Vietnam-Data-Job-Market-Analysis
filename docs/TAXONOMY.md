# Job Family Taxonomy (v1)

Hierarchical **Domain → Sub-domain → Family** used to label every job. Source of truth:
`job_family_engine/taxonomy/taxonomy_v1.yml` (versioned; edit there, no code change). 21 families.

| Domain | Families |
|---|---|
| **Analytics** | Data Analyst · BI Analyst/Developer · Business Analyst · Product Analyst· · Risk/Fraud/Financial Analyst |
| **Data Engineering** | Data Engineer · Analytics Engineer· · Big Data Engineer· · DataOps· · Database/DBA· |
| **AI / Machine Learning** | Data Scientist · Research Scientist· · ML Engineer · MLOps· · AI Engineer · GenAI/LLM · CV/NLP· |
| **Governance & Architecture** | Data Architect· · Data Governance/Quality/Steward· |
| **Leadership** | Head of Data / Manager / Director / CDO· |
| **OTHER** | not a data/AI role (sales/accounting/ops/generic software) |

`·` = **sparse** (few jobs) → in the report, **roll up to Sub-domain/Domain** for reliable %; show
family-level numbers with a caveat.

## How labels are decided (3-tier cascade)
1. **Rule** (title keyword, high-confidence) → ~30% of jobs.
2. **Embedding similarity** (job vs family prototype) → confident matches only.
3. **Multi-LLM voting** (Cerebras gpt-oss-120b + Mistral-large; Groq llama-3.3-70b tiebreaker) reading
   title+JD+skills → majority vote; disagreement → `review_status = manual_review`.

Each job carries `confidence_score`, `labeling_method`, `llm_votes`, `reasoning`, `review_status`.
Quality KPIs: `docs/labeling_kpi.md`.

## Notes for analysts
- Use `job_family` (not the legacy `role_category`) as the role key.
- **Market share %** is computed over Data/AI families (excludes OTHER).
- Boundary families (AI Engineer ↔ ML Engineer, Business Analyst ↔ Data Analyst) are inherently fuzzy;
  manual-review-flagged jobs are the contested ones.
