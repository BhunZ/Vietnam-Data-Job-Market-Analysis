"""Build silver labels (LLM consensus) + a human review queue for the gold TEST set.

LEAN scope: train on `silver` (the consensus label of every job that has a majority). For a
clean eval the user hand-labels a stratified ~150 TEST sample in `review_queue.csv`; until then,
the split falls back to LLM-consensus as pseudo-gold (clearly flagged). Disagreements (no
majority) are excluded from silver and surfaced in the queue.

Run:  python -m pipeline golden --scope full
"""

from __future__ import annotations

import json
import logging

import pandas as pd

from . import _io

log = logging.getLogger("pipeline.dataset.golden")
TEXT_PARQUET = _io.TEXT_DIR / "jobs_text.parquet"


def _load(scope: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    agr = pd.read_parquet(_io.ANNOTATION_DIR / f"agreement_{scope}.parquet")
    votes = pd.DataFrame(json.loads(l) for l in
                         (_io.ANNOTATION_DIR / f"judge_votes_{scope}.jsonl").open(encoding="utf-8"))
    text = pd.read_parquet(TEXT_PARQUET)
    return agr, votes, text


def run_golden(scope: str = "full", n_test: int = 150, seed: int = 42) -> pd.DataFrame:
    agr, votes, text = _load(scope)

    # 1) SILVER = jobs with a majority consensus primary_function (train labels)
    silver = (agr[agr["consensus_primary"].notna()]
              [["job_id", "consensus_primary", "unanimous", "n_judges", "routing_tier"]]
              .rename(columns={"consensus_primary": "primary_function"}).copy())
    silver["label_source"] = "llm_consensus"
    _io.write_parquet(silver, _io.DATASET_DIR / "silver.parquet",
                      schema_version="silver/1", produced_by=f"dataset.golden:{scope}")

    # 2) REVIEW QUEUE for human gold test — stratified ~n_test over consensus classes (prefer
    #    unanimous for a clean test), plus all no-majority disagreements for optional review.
    elig = silver[silver["unanimous"]]
    per = max(1, round(n_test / max(elig["primary_function"].nunique(), 1)))
    test_pick = (elig.groupby("primary_function", group_keys=False)
                 .apply(lambda g: g.sample(min(len(g), per), random_state=seed)))
    test_ids = set(test_pick["job_id"])
    disagree_ids = set(agr[agr["consensus_primary"].isna()]["job_id"])

    tmap = text.set_index("job_id")
    prim_by_job = (votes.groupby("job_id")
                   .apply(lambda g: " / ".join(f"{r['judge'].split('-')[0]}={r['primary_function']}"
                                               for _, r in g.iterrows())))
    rows = []
    for jid in sorted(test_ids | disagree_ids):
        cp = agr.loc[agr["job_id"] == jid, "consensus_primary"]
        rows.append({
            "job_id": jid,
            "title": str(tmap.loc[jid, "title"]) if jid in tmap.index else "",
            "jd_snippet": (str(tmap.loc[jid, "jd"])[:300].replace("\n", " ") if jid in tmap.index else ""),
            "judge_primaries": prim_by_job.get(jid, ""),
            "consensus_primary": (cp.iloc[0] if len(cp) else None),
            "in_test": jid in test_ids,
            "human_primary": "",      # <- fill these
            "human_secondary": "",
            "notes": "",
        })
    queue = pd.DataFrame(rows)
    qpath = _io.DATASET_DIR / "review_queue.csv"
    queue.to_csv(qpath, index=False, encoding="utf-8-sig")  # utf-8-sig so Excel shows Vietnamese
    _io.manifest_append(qpath, rows=len(queue), schema_version="review_queue/1",
                        produced_by=f"dataset.golden:{scope}")

    print(f"\n{'='*64}\nGOLDEN/SILVER ({scope})\n{'='*64}")
    print(f"  silver (consensus) rows : {len(silver)} (unanimous {int(silver['unanimous'].sum())})")
    print(f"  no-majority (excluded)  : {len(disagree_ids)}")
    print(f"  review_queue rows       : {len(queue)} (test={len(test_ids)}, disagree={len(disagree_ids)})")
    print(f"  -> silver.parquet, review_queue.csv (fill human_primary for in_test rows)")
    return silver


def ingest_golden() -> pd.DataFrame | None:
    """Read filled review_queue.csv → golden_test.parquet (human-verified test labels)."""
    qpath = _io.DATASET_DIR / "review_queue.csv"
    if not qpath.exists():
        print("no review_queue.csv — run `golden` first")
        return None
    q = pd.read_csv(qpath)
    gold = q[(q["in_test"]) & (q["human_primary"].astype(str).str.strip() != "")].copy()
    if gold.empty:
        print("review_queue has no filled human_primary yet — using pseudo-gold in split step")
        return None
    gold = gold[["job_id", "human_primary"]].rename(columns={"human_primary": "primary_function"})
    gold["label_source"] = "human"
    _io.write_parquet(gold, _io.DATASET_DIR / "golden_test.parquet",
                      schema_version="golden_test/1", produced_by="dataset.golden.ingest")
    print(f"golden_test: {len(gold)} human-verified test labels")
    return gold
