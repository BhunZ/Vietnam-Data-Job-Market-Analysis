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
    # LLM-decided rows. Must match EVERY tier-3 method prefix the engine emits, else the agreement KPI
    # silently reports nothing: "llm:<provider>" (single-judge path used by predict()), plus the
    # consensus prefixes "vote:" (>=2 judges agreed), "single:" (only one judge answered) and
    # "split:" (no majority). Matching only "llm" made `base_llm_agreement` dead code.
    _m = df["labeling_method"].astype(str)
    llm = df[_m.str.startswith(("llm", "vote:", "single:", "split:", "refine"))]
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
        # Vote coverage = the honest headline. How much of the corpus actually met the >=2-judge bar,
        # versus what a rule/embedding/lone-judge decided on its own with nothing to check it.
        "verified_2plus_votes": int((df["llm_votes"].map(lambda s: len(json.loads(s or "[]"))) >= 2).sum()),
        "single_vote": int(_m.str.startswith("single:").sum()),
        "no_majority": int(_m.str.startswith("split:").sum()),
        "unverified_local_tiers": int(_m.isin(["rule", "embedding"]).sum()),
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
         f"- **verified by >=2 judges: {kpi['verified_2plus_votes']}** | single vote only: "
         f"{kpi['single_vote']} | no majority: {kpi['no_majority']} | "
         f"rule/embedding (no LLM read the JD): {kpi['unverified_local_tiers']}",
         f"- confidence distribution: {kpi['confidence_dist']}",
         "\n> `confidence_score` mixes three incommensurable scales (a constant 0.9 for rules, raw"
         " cosine for embeddings, self-reported LLM numbers for tier-3) and LLM self-confidence is"
         " poorly calibrated — treat it as provenance, NOT as an accuracy estimate.\n",
         "## Family distribution (all jobs)",
         *[f"- {k}: {v}" for k, v in kpi["family_dist"].items()],
         "\n## Market share % (non-OTHER = Data/AI jobs)",
         *[f"- {k}: {v}%" for k, v in share.items()],
         "\n## Domain roll-up", *[f"- {k}: {v}" for k, v in kpi["domain_dist"].items()],
         f"\n> Spot-check {spot_n} jobs (stratified) in `data/labeling/spot_check.csv` — fill `human_family` to measure accuracy."]
    _io.write_text("\n".join(L), DATA_DIR.parent / "docs" / "labeling_kpi.md",
                   schema_version="labeling_kpi/1", produced_by="job_family_engine.evaluate")

    # Stratified spot-check sample, stratified by LABELING TIER (not 1-per-family).
    #
    # The old sampler took spot_n // n_families = 1 job per family, which (a) gave OTHER — ~48% of the
    # corpus and the only place a *missed* data job can hide — the same single row as MLOPS, and (b)
    # measured precision only, never the denominator. Errors concentrate by tier, not by family: rule
    # and embedding never saw the JD, so they are sampled hardest. `stratum` + `stratum_size` are
    # written out so accuracy can be re-weighted back to corpus level instead of averaged naively.
    def _tier(m: str) -> str:
        m = str(m)
        if m in ("rule", "embedding"):
            return m
        if m.startswith("vote:") or m.startswith("refine:"):
            return "llm_2plus_votes"
        return "llm_unverified"                      # single: / split: / llm: / failed
    df = df.copy()
    df["stratum"] = df["labeling_method"].map(_tier) + "|" + \
                    df["job_family"].where(df["job_family"] == "OTHER", "DATA")
    quota = {"rule|DATA": 25, "rule|OTHER": 5, "embedding|DATA": 10, "embedding|OTHER": 2,
             "llm_2plus_votes|DATA": 25, "llm_2plus_votes|OTHER": 25,
             "llm_unverified|DATA": 15, "llm_unverified|OTHER": 10}
    scale = spot_n / sum(quota.values())
    parts = []
    for stratum, g in df.groupby("stratum"):
        k = max(1, round(quota.get(stratum, 5) * scale))
        s = g.sample(min(len(g), k), random_state=seed).copy()
        s["stratum_size"] = len(g)                   # population weight for this stratum
        parts.append(s)
    sc = pd.concat(parts, ignore_index=True)
    text = pd.read_parquet(_io.TEXT_DIR / "jobs_text.parquet")[["job_id", "title"]]
    sc = sc.merge(text, on="job_id", how="left")
    # `verdict`: the cheap human task — judge whether the recorded reasoning is absurd, which needs no
    # domain expertise. Fill with ok / wrong / unsure. `human_family` only if you know the right label.
    sc["verdict"] = ""
    sc["human_family"] = ""
    sc[["job_id", "title", "job_family", "reasoning", "labeling_method", "review_status",
        "stratum", "stratum_size", "verdict", "human_family"]] \
        .to_csv(DATA_DIR / "labeling" / "spot_check.csv", index=False, encoding="utf-8-sig")

    print(json.dumps(kpi, ensure_ascii=False, indent=2))
    print(f"-> docs/labeling_kpi.md + data/labeling/spot_check.csv")
    return kpi
