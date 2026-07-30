# Job Family Taxonomy (v1)

## Cấu trúc 3 tầng (tầng giữa trước đây không được ghi ở đâu cả)

`Domain → Sub-domain → Family`. 6 domain, **10 sub-domain**, 20 family + `OTHER`.

| Domain (`jf_domain`) | Sub-domain (`jf_subdomain`) |
|---|---|
| Analytics | Data Analysis & BI · Business / Domain Analysis |
| Data Engineering | Pipelines & Platform · Database / DBA |
| AI / Machine Learning | Data / Decision Science · ML Engineering · AI / GenAI Engineering |
| Governance & Architecture | Governance & Architecture |
| Data Leadership | Leadership |
| Not a Data/AI role | Other |

⚠️ Giá trị thật trong DB là **`Data Leadership`** và **`Not a Data/AI role`** (không phải `Leadership` /
`OTHER`) — lọc sai tên sẽ ra 0 dòng.

## Cascade hiện tại (đã đổi 25/07/2026)

1. **Tier-1 rule** — chỉ đọc **TITLE**, không đọc JD; chỉ khớp alias đặc thù, conf ≥ 0.9 → ~489 job.
2. **Tier-2 embedding** — ngưỡng đã siết lên `0.88` / margin `0.08`; **hiện nhận 0 job** (ở margin cũ
   `0.02` người thắng chỉ là nhiễu số thực và tầng này từng gán *Software Engineer → BIG_DATA_ENGINEER*).
3. **Tier-3 LLM consensus** — mọi job còn lại cần **≥2 judge đồng thuận**, lệch thì judge thứ 3 phân xử.
4. **Stage-2 `refine`** — nếu vẫn không có đa số: thu hẹp lựa chọn về đúng các family đang tranh chấp +
   JD đầy đủ + buộc trích dẫn bằng chứng; cuối cùng là **đấu loại nhị phân**. `manual_review` hiện = 0.

Judge đã tham gia: cerebras gpt-oss-120b · mistral-large · openrouter qwen-2.5-72b · github gpt-4o-mini ·
groq llama-3.3-70b · cloudflare llama-3.3-70b. Job tranh chấp tra bằng `labeling_method LIKE 'refine%'`.

---


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
