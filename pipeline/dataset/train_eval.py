"""Baseline Job-Function classifier: TF-IDF + Logistic Regression.

Trains on SILVER (LLM-consensus) train(+val); evaluates on the held-out TEST split (human gold
if available, else LLM-consensus pseudo-gold). Reports macro-F1 + per-class P/R + confusion matrix
and writes the most-confused class pairs to `challenges.md` for the next iteration.

Run:  python -m pipeline train
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, f1_score

from . import _io

log = logging.getLogger("pipeline.dataset.train_eval")
SPLITS_DIR = _io.DATASET_DIR / "splits"
METRICS_DIR = _io.DATASET_DIR / "metrics"


def run_train(seed: int = 42) -> dict:
    tr = pd.read_parquet(SPLITS_DIR / "train.parquet")
    va = pd.read_parquet(SPLITS_DIR / "val.parquet")
    te = pd.read_parquet(SPLITS_DIR / "test.parquet")
    train = pd.concat([tr, va], ignore_index=True)  # baseline: fold val into train

    vect = TfidfVectorizer(max_features=20000, ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    Xtr = vect.fit_transform(train["role_view"])
    Xte = vect.transform(te["role_view"])
    clf = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)
    clf.fit(Xtr, train["primary_function"])
    pred = clf.predict(Xte)

    y = te["primary_function"].values
    macro = f1_score(y, pred, average="macro")
    micro = f1_score(y, pred, average="micro")
    weighted = f1_score(y, pred, average="weighted")
    labels = sorted(set(y) | set(pred))
    report = classification_report(y, pred, labels=labels, zero_division=0, output_dict=True)
    cm = confusion_matrix(y, pred, labels=labels)

    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    metrics = {"macro_f1": round(macro, 4), "micro_f1": round(micro, 4),
               "weighted_f1": round(weighted, 4), "n_train": len(train), "n_test": len(te),
               "test_label_source": te["label_source"].iloc[0] if len(te) else None,
               "per_class": {k: {kk: round(vv, 3) for kk, vv in v.items()}
                             for k, v in report.items() if isinstance(v, dict)}}
    (METRICS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    pd.DataFrame(cm, index=labels, columns=labels).to_csv(METRICS_DIR / "confusion_matrix.csv",
                                                          encoding="utf-8")

    # most-confused off-diagonal pairs → challenges.md
    pairs = []
    for i, ti in enumerate(labels):
        for j, tj in enumerate(labels):
            if i != j and cm[i][j] > 0:
                pairs.append((int(cm[i][j]), ti, tj))
    pairs.sort(reverse=True)
    ch = ["# Baseline challenges (next-iteration targets)\n",
          f"- macro-F1 **{macro:.3f}** | micro {micro:.3f} | weighted {weighted:.3f} "
          f"| test={metrics['test_label_source']} (n={len(te)})\n",
          "## Most-confused pairs (true → predicted)"]
    ch += [f"- {n}× **{t}** → {p}" for n, t, p in pairs[:12]]
    ch.append("\n## Weakest classes (by F1)")
    weak = sorted(((v["f1-score"], k) for k, v in metrics["per_class"].items()
                   if k in labels))[:6]
    ch += [f"- {k}: F1 {f:.2f} (support {int(metrics['per_class'][k]['support'])})" for f, k in weak]
    _io.write_text("\n".join(ch), METRICS_DIR / "challenges.md",
                   schema_version="challenges/1", produced_by="dataset.train_eval")

    print(f"\n{'='*64}\nTRAIN+EVAL (TF-IDF + LogReg)\n{'='*64}")
    print(f"  train {len(train)} | test {len(te)} ({metrics['test_label_source']})")
    print(f"  macro-F1 {macro:.3f} | micro {micro:.3f} | weighted {weighted:.3f}")
    print(classification_report(y, pred, labels=labels, zero_division=0))
    print(f"  -> {METRICS_DIR}/metrics.json, confusion_matrix.csv, challenges.md")
    return metrics
