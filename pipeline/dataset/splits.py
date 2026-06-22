"""Group-aware train/val/test split (no cross-source-duplicate leakage).

Splits by `dup_group_id` so the same job (appearing in multiple sources) never straddles splits.
TEST = human-verified `golden_test.parquet` if present, else a held-out slice of LLM-consensus
silver (pseudo-gold, clearly flagged). Train/val = the rest of silver.

Run:  python -m pipeline split
"""

from __future__ import annotations

import logging

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from . import _io

log = logging.getLogger("pipeline.dataset.splits")
SPLITS_DIR = _io.DATASET_DIR / "splits"


def _group_split(df: pd.DataFrame, frac: float, seed: int):
    gss = GroupShuffleSplit(n_splits=1, test_size=frac, random_state=seed)
    a_idx, b_idx = next(gss.split(df, groups=df["dup_group_id"]))
    return df.iloc[a_idx], df.iloc[b_idx]


def run_split(seed: int = 42, test_frac: float = 0.15, val_frac: float = 0.15) -> dict:
    silver = pd.read_parquet(_io.DATASET_DIR / "silver.parquet")
    text = pd.read_parquet(_io.TEXT_DIR / "jobs_text.parquet")[["job_id", "dup_group_id", "role_view"]]
    df = silver.merge(text, on="job_id", how="inner")
    df = df[df["role_view"].fillna("").str.len() > 0].reset_index(drop=True)

    gpath = _io.DATASET_DIR / "golden_test.parquet"
    if gpath.exists():
        gt = pd.read_parquet(gpath)
        test = df[df["job_id"].isin(gt["job_id"])].copy()
        # override labels with human gold
        hum = gt.set_index("job_id")["primary_function"]
        test["primary_function"] = test["job_id"].map(hum)
        test["label_source"] = "human"
        test_groups = set(test["dup_group_id"])
        trainval = df[~df["dup_group_id"].isin(test_groups)].copy()
        gold_kind = "human"
    else:
        trainval, test = _group_split(df, test_frac, seed)
        test = test.copy(); test["label_source"] = "llm_consensus_pseudo_gold"
        gold_kind = "pseudo_gold(LLM consensus)"

    # split trainval → train/val (group-aware), val sized relative to trainval
    rel_val = val_frac / (1 - (len(test) / len(df)))
    train, val = _group_split(trainval, min(max(rel_val, 0.05), 0.4), seed)

    for name, part in [("train", train), ("val", val), ("test", test)]:
        part = part.assign(split=name)
        _io.write_parquet(part[["job_id", "dup_group_id", "primary_function", "role_view",
                                "label_source", "split"]],
                          SPLITS_DIR / f"{name}.parquet",
                          schema_version="split/1", produced_by="dataset.splits")

    # leakage assertion
    g = {n: set(p["dup_group_id"]) for n, p in [("train", train), ("val", val), ("test", test)]}
    leak = (g["train"] & g["test"]) | (g["val"] & g["test"]) | (g["train"] & g["val"])
    assert not leak, f"LEAKAGE: {len(leak)} dup_groups span splits"

    print(f"\n{'='*64}\nSPLIT (group-aware by dup_group_id) — test={gold_kind}\n{'='*64}")
    print(f"  train {len(train)} | val {len(val)} | test {len(test)}  (0 group leakage ✓)")
    print(f"  test class counts: {test['primary_function'].value_counts().to_dict()}")
    miss = set(train["primary_function"]) - set(test["primary_function"])
    if miss:
        print(f"  ⚠ classes absent from test (rare): {miss}")
    return {"train": len(train), "val": len(val), "test": len(test), "gold": gold_kind}
