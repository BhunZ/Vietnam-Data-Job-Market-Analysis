# Job Family Labeling — KPI report

- jobs: 1701 | coverage: 100.0%
- method mix: {'rule': 527, 'embedding': 58, 'llm:cerebras': 358, 'llm:groq': 102, 'llm:mistral': 154, 'llm:groq8b': 476, 'llm:qwen': 26}
- manual-review rate: 0.0% | OTHER rate: 45.8%
- LLM-decided jobs: 1116 | base-LLM agreement: n/a (single judge per job)
- confidence distribution: {'0.85-1.0': 1483, '0.66-0.85': 213, '0.5-0.66': 5, '<0.5': 0}

## Family distribution (all jobs)
- OTHER: 779
- BUSINESS_ANALYST: 191
- DATA_ENGINEER: 161
- DATA_ANALYST: 137
- AI_ENGINEER: 134
- RISK_FRAUD_ANALYST: 59
- BI: 45
- DATA_SCIENTIST: 36
- DATA_GOVERNANCE: 32
- DATA_LEADERSHIP: 25
- PRODUCT_ANALYST: 23
- DBA_DATABASE: 13
- CV_NLP: 13
- ML_ENGINEER: 12
- DATA_ARCHITECT: 12
- GENAI_LLM: 10
- ANALYTICS_ENGINEER: 8
- RESEARCH_SCIENTIST: 5
- DATAOPS: 3
- MLOPS: 2
- BIG_DATA_ENGINEER: 1

## Market share % (non-OTHER = Data/AI jobs)
- BUSINESS_ANALYST: 20.7%
- DATA_ENGINEER: 17.5%
- DATA_ANALYST: 14.9%
- AI_ENGINEER: 14.5%
- RISK_FRAUD_ANALYST: 6.4%
- BI: 4.9%
- DATA_SCIENTIST: 3.9%
- DATA_GOVERNANCE: 3.5%
- DATA_LEADERSHIP: 2.7%
- PRODUCT_ANALYST: 2.5%
- DBA_DATABASE: 1.4%
- CV_NLP: 1.4%
- ML_ENGINEER: 1.3%
- DATA_ARCHITECT: 1.3%
- GENAI_LLM: 1.1%
- ANALYTICS_ENGINEER: 0.9%
- RESEARCH_SCIENTIST: 0.5%
- DATAOPS: 0.3%
- MLOPS: 0.2%
- BIG_DATA_ENGINEER: 0.1%

## Domain roll-up
- Analytics: 455
- AI / Machine Learning: 212
- Data Engineering: 186
- Governance & Architecture: 44
- Data Leadership: 25

> Spot-check 40 jobs (stratified) in `data/labeling/spot_check.csv` — fill `human_family` to measure accuracy.