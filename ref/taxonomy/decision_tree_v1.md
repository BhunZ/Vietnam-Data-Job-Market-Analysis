# Decision Tree v1 — primary_function

> Deterministic ordering so two independent annotators (or LLM judges) reach the same
> `primary_function`. Resolves DE↔DS↔MLE↔AIE↔DA↔BI↔ANALYTICS_ADJ overlap by **priority**
> (engineering → modeling → analysis → BA → other), not by judgment.
> Pairs with `codebook_v1.md` (definitions/examples) and `taxonomy_v2.yml` (label space).
> Version: tree@1. Every node id (S0…S8) is recorded in `evidence.decision_tree_node_id`.

## Inputs
- For GOLD: **full JD** (most-informed truth). For eval, the same gold is tested under
  S1 title-only / S2 title+skills / S3 full-JD (annotation always uses full JD).
- Read **primary responsibilities** first; the **title is a prior, not evidence**.

## Steps

**S0 — Objective extraction (before choosing a function).**
Extract `task_tags` (build_pipeline, etl_elt, model_build, model_serve, model_validate,
dashboard, adhoc_analysis, requirements_process, data_governance, dba_admin,
nlp_cv_llm_modeling, ai_app_integration, research, …) and `artifact`
(pipeline / model / model_system / dashboard_report / application / doc_spec / none).
Record `domain`, `data_intensity` (low/med/high), `seniority` (from silver).

**S1 — Is data/analytics/ML work the PRIMARY responsibility?**
No (sales, accounting, ops, OLTP-DBA admin, IT-infra, generic software/AI-app) → **OTHER**.
If you cannot tell from the JD → primary = best guess + `annotation_status = unsure_insufficient_info`.

**S2 — Is the primary artifact a data pipeline/platform/warehouse/lake/governance?** → **DE**
(includes DataOps + data-modeling-for-analytics + data governance/quality.
OLTP DBA administration → OTHER, not DE.)

**S3 — Is the primary artifact a production ML system (serving / MLOps / deploy / monitoring-eng / maintenance)?** → **MLE**

**S4 — Does the role TRAIN / FINE-TUNE / RESEARCH models?**
- NLP / CV / LLM / GenAI modeling, or model-centric AI system, or AI research → **AIE**
- statistical / predictive / quant modeling (incl. risk/credit/fraud model **building**,
  and quant **model validation**) → **DS**

**S5 — Is the primary artifact analysis / insight / reporting?**
- BI semantic-model / dashboard **development** / BI platform → **BI**
- data analysis / reporting / ad-hoc insight → **DA**

**S6 — Analyst/BA where requirements / process / stakeholder work dominates over data work?** → **ANALYTICS_ADJ** (holding)
Then apply the holding-area reclassify rule:
- data-analysis/reporting dominant → **DA**; BI-platform dominant → **BI**;
- data governance/pipeline → **DE**; no data signal → **OTHER**; else stay **ANALYTICS_ADJ**.

**S7 — dbt / analytics-transformation bridging DE↔DA?** → **AE** (experimental; may fold post-pilot)

**S8 — Still ambiguous / conflicting signals** → primary = best-supported guess +
`annotation_status = genuinely_hybrid` (if the job truly spans functions) and set
`is_borderline = true`. **secondary_functions MUST be filled** with the competing function(s).

## After choosing primary
- `secondary_functions` = every OTHER function with a strong task signal (≥1 clear task_tag).
- `evidence` = quoted JD span(s) + the node id that decided primary.
- `data_intensity`, `domain`, `specialization`, `seniority` recorded regardless of function.

## Tie-breaks (for genuinely_hybrid)
1. Higher `data_intensity` function wins primary.
2. If equal: the function matching the **larger share of responsibilities** in the JD.
3. If still equal: priority order DE > MLE > AIE > DS > BI > DA > AE > ANALYTICS_ADJ
   (engineering/modeling before analysis), and record the other as secondary.
