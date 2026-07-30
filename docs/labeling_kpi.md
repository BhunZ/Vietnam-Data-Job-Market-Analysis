# Job Family Labeling — KPI report

- jobs: 1701 | coverage: 100.0%
- method mix: {'rule': 489, 'vote:github+groq': 40, 'vote:groq+qwen': 40, 'vote:github+qwen': 125, 'vote:cerebras+groq': 34, 'vote:cerebras+cloudflare+groq+qwen': 1, 'vote:github+groq+qwen': 3, 'vote:cerebras+cloudflare+github+groq': 1, 'vote:cerebras+groq+qwen': 1, 'vote:cloudflare+github+groq+qwen': 2, 'vote:cerebras+qwen': 155, 'vote:cerebras+github': 35, 'vote:cerebras+github+qwen': 12, 'vote:cerebras+github+mistral': 4, 'vote:cerebras+cloudflare+github+qwen': 5, 'vote:cerebras+mistral': 600, 'vote:cerebras+mistral+qwen': 24, 'vote:cerebras+groq+mistral': 6, 'vote:cloudflare+github+mistral+qwen': 1, 'vote:cloudflare+github+groq+mistral': 1, 'vote:mistral+qwen': 2, 'vote:cerebras+cloudflare+mistral+qwen': 11, 'vote:cloudflare+groq+mistral+qwen': 1, 'vote:cloudflare+groq+mistral': 1, 'vote:cerebras+cloudflare+mistral': 69, 'vote:cloudflare+mistral+qwen': 3, 'vote:cloudflare+mistral': 5, 'refine:cloudflare+groq+mistral': 3, 'refine:cerebras+cloudflare+mistral': 23, 'refine-knockout:cerebras+cloudflare+mistral': 3, 'refine:cerebras+cloudflare+groq': 1}
- manual-review rate: 0.0% | OTHER rate: 51.9%
- LLM-decided jobs: 1212 | base-LLM agreement: 86.8
- **verified by >=2 judges: 1209** | single vote only: 0 | no majority: 0 | rule/embedding (no LLM read the JD): 489
- confidence distribution: {'0.85-1.0': 1639, '0.66-0.85': 58, '0.5-0.66': 4, '<0.5': 0}

> `confidence_score` mixes three incommensurable scales (a constant 0.9 for rules, raw cosine for embeddings, self-reported LLM numbers for tier-3) and LLM self-confidence is poorly calibrated — treat it as provenance, NOT as an accuracy estimate.

## Family distribution (all jobs)
- OTHER: 882
- BUSINESS_ANALYST: 155
- DATA_ENGINEER: 139
- AI_ENGINEER: 128
- DATA_ANALYST: 124
- RISK_FRAUD_ANALYST: 52
- BI: 47
- DATA_SCIENTIST: 36
- DATA_GOVERNANCE: 35
- DATA_LEADERSHIP: 19
- DATA_ARCHITECT: 14
- CV_NLP: 13
- GENAI_LLM: 12
- DBA_DATABASE: 11
- ML_ENGINEER: 10
- PRODUCT_ANALYST: 6
- ANALYTICS_ENGINEER: 5
- MLOPS: 4
- DATAOPS: 4
- BIG_DATA_ENGINEER: 3
- RESEARCH_SCIENTIST: 2

## Market share % (non-OTHER = Data/AI jobs)
- BUSINESS_ANALYST: 18.9%
- DATA_ENGINEER: 17.0%
- AI_ENGINEER: 15.6%
- DATA_ANALYST: 15.1%
- RISK_FRAUD_ANALYST: 6.3%
- BI: 5.7%
- DATA_SCIENTIST: 4.4%
- DATA_GOVERNANCE: 4.3%
- DATA_LEADERSHIP: 2.3%
- DATA_ARCHITECT: 1.7%
- CV_NLP: 1.6%
- GENAI_LLM: 1.5%
- DBA_DATABASE: 1.3%
- ML_ENGINEER: 1.2%
- PRODUCT_ANALYST: 0.7%
- ANALYTICS_ENGINEER: 0.6%
- MLOPS: 0.5%
- DATAOPS: 0.5%
- BIG_DATA_ENGINEER: 0.4%
- RESEARCH_SCIENTIST: 0.2%

## Domain roll-up
- Analytics: 384
- AI / Machine Learning: 205
- Data Engineering: 162
- Governance & Architecture: 49
- Data Leadership: 19

> Spot-check 40 jobs (stratified) in `data/labeling/spot_check.csv` — fill `human_family` to measure accuracy.