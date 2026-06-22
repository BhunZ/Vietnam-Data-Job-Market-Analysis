"""Engine quality KPIs + spot-check sampler (no training, no benchmark formalism).

Reads `data/labeling/job_family.parquet` and reports coverage, method mix, manual-review rate,
OTHER rate, inter-LLM agreement (on LLM-decided jobs), confidence distribution, and the family/
domain distribution. Also emits a stratified spot-check CSV for a human to verify accuracy.
"""

from __future__ import annotations

import json
from collections import Counter

import pandas as pd

from pipeline.dataset import _io
from pipeline.utils.config import DATA_DIR

LABEL_PARQUET = DATA_DIR / "labeling" / "job_family.parquet"


def _agreement(votes_json: str) -> bool | None:
    v = json.loads(votes_json or "[]")
    fams = [x["job_family"] for x in v]
    base = fams[:2]  # base pair
    if len(base) < 2:
        return None
    return base[0] == base[1]


def run_eval(spot_n: int = 40, seed: int = 42) -> dict:
    df = pd.read_parquet(LABEL_PARQUET)
    n = len(df)
    # LLM-decided rows: labeling_method is "llm:<provider>" (one judge per job in this engine).
    llm = df[df["labeling_method"].astype(str).str.startswith("llm")]
    agr = llm["llm_votes"].map(_agreement).dropna()  # empty under single-judge (no 2nd vote)
    conf_bins = pd.cut(df["confidence_score"], [0, 0.5, 0.66, 0.85, 1.01],
                       labels=["<0.5", "0.5-0.66", "0.66-0.85", "0.85-1.0"],
                       include_lowest=True).value_counts().to_dict()  # keep conf==0.0 (failed rows)
    kpi = {
        "n": n,
        "coverage": round(100 * df["job_family"].notna().mean(), 1),
        "method": dict(Counter(df["labeling_method"])),
        "manual_review_rate": round(100 * (df["review_status"] == "manual_review").mean(), 1),
        "other_rate": round(100 * (df["job_family"] == "OTHER").mean(), 1),
        "llm_decided": int(len(llm)),
        "base_llm_agreement": (round(100 * agr.mean(), 1) if len(agr) else None),  # None = single-judge
        "confidence_dist": {str(k): int(v) for k, v in conf_bins.items()},
        "family_dist": dict(Counter(df["job_family"]).most_common()),
        "domain_dist": dict(Counter(df.loc[df["job_family"] != "OTHER", "domain"].dropna()).most_common()),
    }

    # market share over non-OTHER (analysis preview)
    data_only = df[df["job_family"] != "OTHER"]
    share = (data_only["job_family"].value_counts(normalize=True) * 100).round(1).to_dict()

    L = [f"# Job Family Labeling — KPI report\n",
         f"- jobs: {n} | coverage: {kpi['coverage']}%",
         f"- method mix: {kpi['method']}",
         f"- manual-review rate: {kpi['manual_review_rate']}% | OTHER rate: {kpi['other_rate']}%",
         f"- LLM-decided jobs: {kpi['llm_decided']} | base-LLM agreement: "
         f"{kpi['base_llm_agreement'] if kpi['base_llm_agreement'] is not None else 'n/a (single judge per job)'}",
         f"- confidence distribution: {kpi['confidence_dist']}\n",
         "## Family distribution (all jobs)",
         *[f"- {k}: {v}" for k, v in kpi["family_dist"].items()],
         "\n## Market share % (non-OTHER = Data/AI jobs)",
         *[f"- {k}: {v}%" for k, v in share.items()],
         "\n## Domain roll-up", *[f"- {k}: {v}" for k, v in kpi["domain_dist"].items()],
         f"\n> Spot-check {spot_n} jobs (stratified) in `data/labeling/spot_check.csv` — fill `human_family` to measure accuracy."]
    _io.write_text("\n".join(L), DATA_DIR.parent / "docs" / "labeling_kpi.md",
                   schema_version="labeling_kpi/1", produced_by="job_family_engine.evaluate")

    # stratified spot-check sample. Build per-group manually (concat of full sub-frames) so the
    # grouping column is preserved — newer pandas excludes it from groupby.apply by default.
    per = max(1, spot_n // max(1, df["job_family"].nunique()))
    sc = pd.concat([g.sample(min(len(g), per), random_state=seed)
                    for _, g in df.groupby("job_family")], ignore_index=True)
    text = pd.read_parquet(_io.TEXT_DIR / "jobs_text.parquet")[["job_id", "title"]]
    sc = sc.merge(text, on="job_id", how="left")
    sc["human_family"] = ""
    sc[["job_id", "title", "job_family", "confidence_score", "labeling_method", "review_status", "human_family"]] \
        .to_csv(DATA_DIR / "labeling" / "spot_check.csv", index=False, encoding="utf-8-sig")

    print(json.dumps(kpi, ensure_ascii=False, indent=2))
    print(f"-> docs/labeling_kpi.md + data/labeling/spot_check.csv")
    return kpi
