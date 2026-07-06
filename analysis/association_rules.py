"""Association rules for skill learning paths.

Reads `jobs_silver.skills` from the shipped DuckDB warehouse, keeps the analysis
population (active, non-duplicate, non-OTHER job_family), and derives simple
skill association rules without extra mining dependencies.

Run:
    python analysis/association_rules.py
"""

from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse.duckdb"
OUT = Path(__file__).resolve().parent / "outputs"
OUT.mkdir(parents=True, exist_ok=True)


def load_transactions() -> list[set[str]]:
    con = duckdb.connect(str(DB), read_only=True)
    df = con.execute(
        """
        SELECT skills
        FROM jobs_silver
        WHERE job_family IS NOT NULL
          AND job_family != 'OTHER'
          AND is_active
          AND is_duplicate_of IS NULL
        """
    ).df()
    con.close()

    transactions: list[set[str]] = []
    for raw in df["skills"]:
        skills = json.loads(raw) if isinstance(raw, str) else []
        skill_set = {s for s in skills if isinstance(s, str) and s.strip()}
        if len(skill_set) >= 2:
            transactions.append(skill_set)
    return transactions


def count_itemsets(transactions: list[set[str]], max_size: int) -> dict[int, Counter[tuple[str, ...]]]:
    counts: dict[int, Counter[tuple[str, ...]]] = {size: Counter() for size in range(1, max_size + 1)}
    for skills in transactions:
        ordered = sorted(skills)
        for size in range(1, max_size + 1):
            for combo in itertools.combinations(ordered, size):
                counts[size][combo] += 1
    return counts


def mine_rules(
    transactions: list[set[str]],
    *,
    min_n: int,
    min_confidence: float,
    min_lift: float,
    max_antecedent: int,
) -> pd.DataFrame:
    n_transactions = len(transactions)
    counts = count_itemsets(transactions, max_size=max_antecedent + 1)
    rows = []

    for size in range(2, max_antecedent + 2):
        for itemset, both_n in counts[size].items():
            if both_n < min_n:
                continue
            items = set(itemset)
            for ant_size in range(1, min(max_antecedent, size - 1) + 1):
                for antecedent in itertools.combinations(itemset, ant_size):
                    consequent_items = tuple(sorted(items - set(antecedent)))
                    if len(consequent_items) != 1:
                        continue

                    antecedent = tuple(sorted(antecedent))
                    consequent = consequent_items[0]
                    antecedent_n = counts[len(antecedent)][antecedent]
                    consequent_n = counts[1][(consequent,)]
                    confidence = both_n / antecedent_n
                    consequent_support = consequent_n / n_transactions
                    lift = confidence / consequent_support if consequent_support else 0
                    if confidence < min_confidence or lift < min_lift:
                        continue

                    rows.append(
                        {
                            "antecedent": " + ".join(antecedent),
                            "consequent": consequent,
                            "antecedent_n": antecedent_n,
                            "consequent_n": consequent_n,
                            "both_n": both_n,
                            "support_pct": round(100 * both_n / n_transactions, 2),
                            "confidence": round(confidence, 3),
                            "lift": round(lift, 3),
                        }
                    )

    if not rows:
        return pd.DataFrame(
            columns=[
                "antecedent",
                "consequent",
                "antecedent_n",
                "consequent_n",
                "both_n",
                "support_pct",
                "confidence",
                "lift",
            ]
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["lift", "confidence", "both_n"], ascending=[False, False, False])
        .reset_index(drop=True)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine skill association rules.")
    parser.add_argument("--min-n", type=int, default=25, help="Minimum jobs containing A+B.")
    parser.add_argument("--min-confidence", type=float, default=0.35)
    parser.add_argument("--min-lift", type=float, default=1.1)
    parser.add_argument("--max-antecedent", type=int, default=2)
    args = parser.parse_args()

    transactions = load_transactions()
    rules = mine_rules(
        transactions,
        min_n=args.min_n,
        min_confidence=args.min_confidence,
        min_lift=args.min_lift,
        max_antecedent=args.max_antecedent,
    )

    out_csv = OUT / "association_rules.csv"
    rules.to_csv(out_csv, index=False, encoding="utf-8")

    print(f"transactions {len(transactions)}")
    print(f"rules {len(rules)}")
    print(f"output {out_csv}")
    if not rules.empty:
        print(rules.head(20).to_string(index=False))


if __name__ == "__main__":
    main()

