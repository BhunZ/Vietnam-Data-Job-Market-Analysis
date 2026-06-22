# Codebook v1 — VN Data/AI job-role annotation

> Companion to `taxonomy_v2.yml` (label space) + `decision_tree_v1.md` (order).
> Target = `primary_function`; `secondary_functions` + `task_tags` capture multidimensionality.
> **Golden rule:** label by PRIMARY RESPONSIBILITIES, not title. Examples are REAL corpus titles.
> Version: codebook@1. Pairs with taxonomy@2, tree@1.

## 0. Global rules
- **Title is a prior, not evidence.** Decide from responsibilities/requirements.
- **No UNSURE label.** Epistemic doubt → `annotation_status=unsure_insufficient_info`;
  genuine hybrid → `genuinely_hybrid` + multi-label.
- **Bilingual trap (critical):** `mô hình dữ liệu` = *data model / schema / ERD* → DA or DE.
  `mô hình` (rủi ro, ML, dự báo) = *statistical/ML model* → DS. Never conflate the two.
- Always record `data_intensity` (low/med/high), `domain`, `specialization`, `evidence`.

## 1. Functions — definition · inclusion · exclusion · examples

### DE — Data Engineering
Builds/operates data systems **for analytics/ML**. Includes Data Platform, Warehouse, Lake,
Lakehouse, **DataOps**, ETL/ELT, data-modeling-for-analytics, **data governance/quality**.
- ✅ `Senior Data Engineer/Data Platform Engineer` (AWS/Airflow/BigQuery/Data Pipeline)
- ✅ `Data Platform Operations` (AWS/Azure/Databricks/Data Lake/ETL) — currently OTHER → **DE** (DataOps)
- ✅ `Data Architect`, `CVCC Data Warehouse`, `Data Governance` (governance of DATA)
- ⛔ `Oracle Database Administrator`, `Head of Database Administration` (OLTP backup/tuning/HA) → **OTHER** (specialization=dba)
- ⚠️ `Database Developer` (ETL/SQL/MongoDB) → DE if ETL/analytics-data dominant; else OTHER.

### DS — Data Science
**Builds** statistical/ML/quant models; experimentation. Includes risk/credit/fraud model
**building** and **quant model validation**.
- ✅ `Data Science & Risk Modeling Specialist` (Python/Stat/ML)
- ✅ `Chuyên gia/CVCC Mô hình rủi ro` (DL/ML) — currently OTHER → **DS** (domain=risk_credit_fraud_aml, spec=credit_risk_modeling)
- ✅ `RISK MODELING SUPERVISOR` → **DS** (model building/oversight)
- ✅ `Chuyên gia Kiểm định Mô hình (BI)` (model validation, quant) → **DS** (spec=model_validation)
- ⛔ `Chuyên viên thiết kế Mô hình DỮ LIỆU` (data model = schema) → **DA/DE**, NOT DS (bilingual trap)
- ⛔ pure reporting w/o modeling → DA; productionizing a model → MLE

### MLE — ML Engineering
**Productionizes** ML: serving, MLOps, deployment, monitoring/maintenance infra.
- ✅ `MLOps Engineer - Vận Hành Và Tích Hợp Mô Hình AI` (CI/CD/Docker)
- ✅ `Chuyên viên Vận hành mô hình` (AWS/Azure/CI/CD/K8s/Hadoop) — currently DE → **MLE** (model ops)
- ⛔ model **building** (math/stats) → DS; AI app consuming models → OTHER

### AIE — AI / GenAI / NLP / CV Engineering
**Primary artifact = an AI/ML model or model-centric system** (NLP/CV/LLM/GenAI), or AI research.
- ✅ `AI/NLP ENGINEER` (NLP/PyTorch/TensorFlow/DL) — currently OTHER → **AIE**
- ✅ `Senior AI Engineer` (LLM/ML/NLP), `KỸ SƯ AI NGÔN NGỮ LỚN` (LLM) → **AIE**
- ⛔ `AI Software Engineer` (C++/Java/Docker/K8s) → **OTHER** (artifact = app/backend, AI is a feature)
- ⚠️ `Agentic Engineer` / RAG: substantial retrieval/eval/model engineering → AIE; else OTHER + `is_borderline=true`
- ⛔ `Kỹ sư dữ liệu AI (Data Engineer)` (Airflow/BigQuery/ELT) → **DE** (artifact = pipeline)

### DA — Data Analysis
Analyzes data, builds reports/dashboards, answers business questions. Includes risk/fraud **data analysis**.
- ✅ `Data Analyst` (Data Analysis/Excel/Statistics), `Chuyên viên Phân tích dữ liệu`
- ✅ `Trưởng Nhóm Phân Tích Dữ Liệu` — currently DE → **DA** (seniority=Lead)
- ✅ `Customer & Product Analytics Executive` — currently DE → **DA** (spec=product_analytics)
- ✅ `Chuyên Gia Phân tích dữ liệu và xây dựng mô hình phát hiện gian lận` → DA or DS (read JD: if model-building dominant → DS)
- ⛔ requirements/process analysis w/ little data → ANALYTICS_ADJ; BI-platform dev → BI

### BI — Business Intelligence
BI **development**: semantic models, dashboards, BI tooling/platform.
- ✅ `Trưởng Bộ Phận BI` — currently DE → **BI** (seniority=Manager)
- ✅ `Chuyên Viên Phân Tích Quản Trị (BI)` (Power BI/Data Modeling/Reporting)
- ⛔ one-off Excel reporting by a non-BI role → DA

### AE — Analytics Engineering (EXPERIMENTAL, low-support)
dbt-style transformation/modeling bridging DE↔DA. Report separately; merge decision post-pilot.
- ✅ `Analytics Engineer`, `Lead Analytics Engineer` (dbt/Data Modeling/Data Warehouse)
- ⛔ full data-platform engineering → DE

### ANALYTICS_ADJ — Analytics-adjacent (HOLDING AREA)
Analyst/BA where requirements/process/stakeholder work dominates. **Default for bare BA**, then reclassify.
- ✅ `IT Business Analyst` (Agile/Azure/Excel/SQL) → ANALYTICS_ADJ (spec=it)
- ✅ `Senior IT Product Business Analyst` (Agile/LLM) → ANALYTICS_ADJ (spec=product)
- ↪ `Business Analyst` (Data Analysis/SQL/Data Viz/ML, reporting dominant) → **reclassify DA**
- ↪ `Senior Data Management Specialist – Business Analyst` (Data Governance/Quality) → **reclassify DE**
- ↪ `Chuyên viên phân tích nghiệp vụ` (0 skill, no JD signal) → stay ANALYTICS_ADJ + `unsure_insufficient_info`

### OTHER — Not a data role
No substantive data work: sales, accounting, ops, **OLTP DBA**, IT infrastructure, **generic software / AI-app engineering**.
- ✅ `Nhân viên Kinh doanh`, `Chuyên viên Tài chính`, `Thủ kho`, `Oracle DBA`, `AI Software Engineer`

## 2. Model-lifecycle quick map (annotator cheat-sheet)
| Stage | Function | Note |
|---|---|---|
| Model **building** (train/develop) | DS | risk/credit/fraud models too |
| Model **validation** (independent quant check) | DS (spec=model_validation) | → DA only if near-pure reporting |
| Model **governance** | DS if quantitative; OTHER/ANALYTICS_ADJ if pure policy | |
| Model **monitoring** | MLE (eng) / DS (analysis) | |
| Model **deploy / serve / ops / maintain** | MLE | |
| **Data** governance/quality (≠ model) | DE | |

## 3. Three confusions annotators MUST get right
- **DS vs MLE:** DS *creates* the model (artifact = model + insight); MLE *runs it in production* (artifact = deployed system).
- **DS/AIE vs OTHER (AI):** *builds/trains/researches* AI model → DS/AIE; *integrates pre-built AI into an app* → OTHER.
- **DA vs ANALYTICS_ADJ:** dominant duty = data analysis/reporting → DA; dominant duty = requirements/process/stakeholder → ANALYTICS_ADJ. `data_intensity` recorded either way (it is NOT the decider — dominant DUTY is).

## 4. Annotation flow (per JD)
1. Read responsibilities (ignore title first). 2. S0: extract task_tags + artifact + domain + data_intensity.
3. Walk decision tree S1→S8 → primary_function. 4. secondary_functions = other strong-signal functions.
5. evidence = JD span(s) + decision node id. 6. confidence + annotation_status. 7. seniority from silver.

## 5. Specialization vocab (optional, preserves sub-discipline)
credit_risk_modeling · fraud_modeling · aml · market_risk · model_validation · model_ops ·
nlp · computer_vision · llm_genai · product_analytics · marketing_analytics · hr_analytics ·
dataops · dba · finance_analytics
