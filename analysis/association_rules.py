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

# These run as standalone scripts (`python analysis/<name>.py`), so the repo root is not on sys.path
# by default — add it before importing the shared analysis-base definition.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.utils.analysis_base import ANALYSIS_BASE_WHERE


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse.duckdb"
OUT = Path(__file__).resolve().parent / "outputs"
OUT.mkdir(parents=True, exist_ok=True)


def base_count() -> int:
    """Size of the official analysis base, so the report can state what the rules exclude."""
    con = duckdb.connect(str(DB), read_only=True)
    n = con.execute(
        f"""
        SELECT COUNT(*) FROM jobs_silver
        WHERE {ANALYSIS_BASE_WHERE}
        """
    ).fetchone()[0]
    con.close()
    return int(n)


def load_transactions() -> list[set[str]]:
    con = duckdb.connect(str(DB), read_only=True)
    df = con.execute(
        f"""
        SELECT skills
        FROM jobs_silver
        WHERE {ANALYSIS_BASE_WHERE}
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
) -> tuple[pd.DataFrame, int]:
    """Returns (rules, n_evaluated) where `n_evaluated` counts every antecedent→consequent pair that got
    a confidence/lift computed — i.e. every hypothesis actually tested. That is the family size a
    family-wise correction has to use; `len(rules)` is the survivors and is far too small (see
    `add_significance`)."""
    n_transactions = len(transactions)
    counts = count_itemsets(transactions, max_size=max_antecedent + 1)
    rows = []
    n_evaluated = 0

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
                    n_evaluated += 1
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

    cols = ["antecedent", "consequent", "antecedent_n", "consequent_n", "both_n",
            "support_pct", "confidence", "lift"]
    if not rows:
        return pd.DataFrame(columns=cols), n_evaluated
    return (
        pd.DataFrame(rows)
        # Stable sort so tied rules keep a fixed order between runs (the default quicksort let ties
        # shuffle, which makes a diff-based reader think the results moved).
        # Sorted by SUPPORT, not lift: sorting by lift floated ~20 near-duplicate PyTorch/TensorFlow
        # rules to the top on ~4% support, presenting a negligible absolute co-occurrence as the
        # headline finding.
        .sort_values(["both_n", "confidence", "lift"], ascending=False, kind="stable")
        .reset_index(drop=True)
    ), n_evaluated


def add_significance(rules: pd.DataFrame, n_transactions: int, n_evaluated: int) -> pd.DataFrame:
    """Fisher exact p-value per rule + a family-wise (Bonferroni) flag.

    Thousands of antecedent→consequent pairs are tested, so some clear any confidence/lift threshold by
    chance alone. The correction must divide by the number of hypotheses TESTED (`n_evaluated`), not by
    the number that survived pruning: an earlier version used `0.05/len(rules)`, which is the survivors
    and under-corrects by the pruning ratio — it called rules significant that a correct family-wise
    correction rejects. Both columns are emitted so the difference is visible rather than asserted:

      * `significant_bonferroni`      — alpha = 0.05 / n_evaluated   (correct; quote this one)
      * `significant_at_kept_alpha`   — alpha = 0.05 / len(rules)    (the old, too-lenient threshold)
    """
    if rules.empty:
        return rules
    try:
        from scipy.stats import fisher_exact
    except ImportError:                       # scipy absent → be explicit rather than silently skip
        rules["p_value"] = float("nan")
        rules["significant_bonferroni"] = pd.NA
        rules["significant_at_kept_alpha"] = pd.NA
        return rules
    pvals = []
    for r in rules.itertuples(index=False):
        a_only = r.antecedent_n - r.both_n
        c_only = r.consequent_n - r.both_n
        neither = n_transactions - r.both_n - a_only - c_only
        _, p = fisher_exact([[r.both_n, a_only], [c_only, max(neither, 0)]], alternative="greater")
        pvals.append(float(p))
    rules = rules.copy()
    rules["p_value"] = pvals
    rules["significant_bonferroni"] = rules["p_value"] < 0.05 / max(n_evaluated, 1)
    rules["significant_at_kept_alpha"] = rules["p_value"] < 0.05 / max(len(rules), 1)
    return rules


def drop_redundant(rules: pd.DataFrame, min_gain: float) -> pd.DataFrame:
    """Keep a 2-item-antecedent rule only if it beats its best 1-item sub-rule by `min_gain` confidence.

    "SQL + Python -> Power BI" is not a finding if "SQL -> Power BI" already has the same confidence —
    the second item adds nothing. Without this, ~93% of 2-item rules shipped alongside their own subsets
    and ~43% added under 0.05 confidence, padding the rule count without adding information.
    """
    if rules.empty:
        return rules
    best_single = {(r.antecedent, r.consequent): r.confidence
                   for r in rules.itertuples(index=False) if " + " not in r.antecedent}
    keep = []
    for r in rules.itertuples(index=False):
        if " + " not in r.antecedent:
            keep.append(True)
            continue
        subs = [best_single.get((part, r.consequent))
                for part in r.antecedent.split(" + ")]
        subs = [c for c in subs if c is not None]
        keep.append(True if not subs else r.confidence >= max(subs) + min_gain)
    return rules[pd.Series(keep, index=rules.index)].reset_index(drop=True)


def write_findings(*, base_n: int, n_tx: int, n_raw: int, rules: pd.DataFrame, args,
                   n_eval: int) -> None:
    """Generate the findings doc FROM the rules table.

    This doc used to be hand-maintained — the only P5 findings file that was — and it drifted until
    every number in every evidence table was wrong (711/1834 transactions/rules against an actual
    657/1821, and support percentages off by the ratio of the two bases). Generating it removes the
    entire class of error.
    """
    sig = int(rules["significant_bonferroni"].sum()) if "significant_bonferroni" in rules else 0
    sig_lenient = (int(rules["significant_at_kept_alpha"].sum())
                   if "significant_at_kept_alpha" in rules else 0)
    # Count 1-item rules whose reverse is also present, so the doc can state distinct associations.
    single = rules[~rules["antecedent"].astype(str).str.contains(r" \+ ")] if not rules.empty else rules
    seen = {frozenset((str(a), str(c))) for a, c in zip(single["antecedent"], single["consequent"])} \
        if not rules.empty else set()
    n_bidir = len(single) - len(seen) if not rules.empty else 0
    top = rules.head(15)
    rows = "\n".join(
        f"| {r.antecedent} | {r.consequent} | {r.both_n} | {r.support_pct} | {r.confidence} | "
        f"{r.lift} | {'yes' if getattr(r, 'significant_bonferroni', False) else 'no'} |"
        for r in top.itertuples(index=False)
    )
    doc = f"""# Association Rules — Findings

*Generated by `python analysis/association_rules.py`. Do not hand-edit; re-run to refresh.*

## Business Question

Which skills are asked for together in Vietnamese Data/AI job postings, so a learner can pick a bundle
rather than a single tool?

## Population

- Official analysis base: **{base_n}** postings.
- Postings with at least 2 normalized skill tags (**transactions**): **{n_tx}**.
- Excluded: **{base_n - n_tx}** postings ({100 * (base_n - n_tx) / base_n:.1f}%) that list 0 or 1 skill.
  `support_pct` below is therefore a share of the **{n_tx} multi-skill postings, not of {base_n}** — it
  runs about {n_tx and base_n / n_tx:.2f}x higher than the corresponding share of the full base. Dropping
  thin-tag postings also tilts the set toward richly-described JDs, which are exactly the ones that list
  framework bundles, so framework-pair lift is biased upward.

## Method and thresholds

- Antecedents up to {args.max_antecedent} items, single-item consequents.
- Kept when `both_n >= {args.min_n}`, `confidence >= {args.min_confidence}`, `lift >= {args.min_lift}`.
- **Redundancy pruning:** a 2-item rule is dropped unless it beats its best 1-item sub-rule by
  >= {args.min_conf_gain} confidence. Mined {n_raw} rules, kept **{len(rules)}** after pruning.
- **Significance:** one-sided Fisher exact test per rule, then a family-wise (Bonferroni) correction.
  The family is every antecedent→consequent pair that actually got a statistic computed:
  **{n_eval} hypotheses tested**, so alpha = 0.05/{n_eval} = {0.05 / max(n_eval, 1):.2e}.
  **{sig} of {len(rules)}** rules pass — quote only these.
  A previous version divided by the {len(rules)} rules that *survived* pruning (alpha =
  {0.05 / max(len(rules), 1):.2e}), which under-corrects by {n_eval / max(len(rules), 1):.1f}x and passed
  **{sig_lenient}** rules. The `significant_at_kept_alpha` column keeps that looser flag so the
  {sig_lenient - sig} rules that only clear the wrong threshold stay identifiable instead of vanishing.
- **Bidirectional pairs:** a 1-item rule and its reverse are two rows (`Python → SQL` and `SQL → Python`).
  {n_bidir} pairs appear both ways = {2 * n_bidir} of {len(rules)} rows, so the {len(rules)} rules describe
  **{len(rules) - n_bidir} distinct associations**. Do not report {len(rules)} as a count of findings.
- Sorted by absolute co-occurrence (`both_n`), not lift — lift alone promotes rare pairs.

## Top rules by co-occurrence

| If a posting asks for | it also asks for | both_n | support_pct | confidence | lift | sig. |
|---|---|---:|---:|---:|---:|---|
{rows}

Full table: `analysis/outputs/association_rules.csv`.

## How to read this

- These are **co-occurrence** rules over normalized skill tags, not causal or temporal statements.
- `confidence` = P(consequent | antecedent) within multi-skill postings; `lift` > 1 means the pair
  appears together more than independence would predict.
- A rule says employers *list* the skills together. It does not say learning one causes the other, nor
  which to learn first.
- One snapshot only: no trend, no growth claim. No salary in the data: no pay claim.
"""
    (ROOT / "docs" / "ASSOCIATION_RULES_FINDINGS.md").write_text(doc, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine skill association rules.")
    parser.add_argument("--min-n", type=int, default=25, help="Minimum jobs containing A+B.")
    parser.add_argument("--min-confidence", type=float, default=0.35)
    parser.add_argument("--min-lift", type=float, default=1.1)
    parser.add_argument("--max-antecedent", type=int, default=2)
    parser.add_argument("--min-conf-gain", type=float, default=0.05,
                        help="A 2-item rule must beat its best 1-item sub-rule by this much.")
    args = parser.parse_args()

    base_n = base_count()
    transactions = load_transactions()
    raw, n_evaluated = mine_rules(
        transactions,
        min_n=args.min_n,
        min_confidence=args.min_confidence,
        min_lift=args.min_lift,
        max_antecedent=args.max_antecedent,
    )
    rules = add_significance(drop_redundant(raw, args.min_conf_gain), len(transactions), n_evaluated)

    out_csv = OUT / "association_rules.csv"
    rules.to_csv(out_csv, index=False, encoding="utf-8")
    write_findings(base_n=base_n, n_tx=len(transactions), n_raw=len(raw), rules=rules, args=args,
                   n_eval=n_evaluated)

    print(f"analysis_base {base_n}")
    print(f"transactions {len(transactions)}")
    print(f"hypotheses_tested {n_evaluated}")
    print(f"rules_mined {len(raw)}")
    print(f"rules {len(rules)}")
    if "significant_bonferroni" in rules:
        print(f"significant_bonferroni {int(rules['significant_bonferroni'].sum())} "
              f"(alpha=0.05/{n_evaluated})")
        print(f"significant_at_kept_alpha {int(rules['significant_at_kept_alpha'].sum())} "
              f"(alpha=0.05/{len(rules)}, too lenient)")
    print(f"output {out_csv}")
    if not rules.empty:
        print(rules.head(12).to_string(index=False))


if __name__ == "__main__":
    main()

