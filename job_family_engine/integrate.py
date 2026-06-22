"""B7: integrate `job_family` (+ metadata) into `jobs_silver` and rebuild Gold by job_family.

Adds job_family columns to jobs_silver (idempotent) from the engine output, then builds the
family-centric Gold tables the teammate's analysis consumes. Keeps the legacy rule-based Gold
(role_category) tables untouched for reference. Analysis set = labeled, active, non-duplicate,
non-OTHER (Data/AI jobs).

Run:  python -m pipeline integrate
"""

from __future__ import annotations

import json
from collections import Counter
from itertools import combinations

import duckdb
import pandas as pd

from pipeline.utils.config import DATA_DIR

DB = DATA_DIR / "warehouse.duckdb"
LABEL = DATA_DIR / "labeling" / "job_family.parquet"
_COLS = [("job_family", "VARCHAR"), ("jf_domain", "VARCHAR"), ("jf_subdomain", "VARCHAR"),
         ("jf_confidence", "DOUBLE"), ("jf_method", "VARCHAR"), ("jf_review", "VARCHAR")]


def _write(con, name, df):
    con.register("_g", df)
    con.execute(f"DROP TABLE IF EXISTS {name}")
    con.execute(f"CREATE TABLE {name} AS SELECT * FROM _g")
    con.unregister("_g")


def integrate() -> None:
    con = duckdb.connect(str(DB))
    lab = pd.read_parquet(LABEL)[["job_id", "job_family", "domain", "subdomain",
                                  "confidence_score", "labeling_method", "review_status"]]
    con.register("lab", lab)
    for col, typ in _COLS:
        con.execute(f"ALTER TABLE jobs_silver ADD COLUMN IF NOT EXISTS {col} {typ}")
    con.execute("""UPDATE jobs_silver SET
        job_family=lab.job_family, jf_domain=lab.domain, jf_subdomain=lab.subdomain,
        jf_confidence=lab.confidence_score, jf_method=lab.labeling_method, jf_review=lab.review_status
        FROM lab WHERE jobs_silver.job_id=lab.job_id""")
    con.unregister("lab")

    # analysis set
    sd = con.execute("""SELECT job_id, job_family, jf_domain, jf_subdomain, seniority, city, region,
        company, company_type, skills FROM jobs_silver
        WHERE job_family IS NOT NULL AND is_active AND is_duplicate_of IS NULL""").df()
    data = sd[sd["job_family"] != "OTHER"].copy()
    data["skill_list"] = data["skills"].map(lambda s: json.loads(s) if isinstance(s, str) else [])
    n = len(data)

    # gold_jobs (all labeled, incl OTHER — teammate filters)
    _write(con, "gold_jobs", sd.drop(columns=["skills"]))
    # gold_market_share (per family + domain)
    ms = (data.groupby(["jf_domain", "job_family"])["job_id"].nunique().reset_index(name="n"))
    ms["pct"] = (100.0 * ms["n"] / n).round(1)
    _write(con, "gold_market_share", ms.sort_values("n", ascending=False))
    # gold_family_skill (skill share within family)
    long = data.explode("skill_list").dropna(subset=["skill_list"]).rename(columns={"skill_list": "skill"})
    fam_tot = data.groupby("job_family")["job_id"].nunique().to_dict()
    fs = long.groupby(["job_family", "skill"])["job_id"].nunique().reset_index(name="n")
    fs["share_in_family"] = fs.apply(lambda r: round(100.0 * r["n"] / fam_tot[r["job_family"]], 1), axis=1)
    _write(con, "gold_family_skill", fs.sort_values(["job_family", "n"], ascending=[True, False]))
    # gold_company (company_type × family)
    cc = data.groupby(["company_type", "job_family"])["job_id"].nunique().reset_index(name="n")
    _write(con, "gold_company", cc.sort_values("n", ascending=False))
    # gold_location (region/city × family)
    loc = (data.dropna(subset=["city"]).groupby(["region", "city", "job_family"])["job_id"]
           .nunique().reset_index(name="n"))
    _write(con, "gold_location", loc.sort_values("n", ascending=False))
    # gold_seniority (seniority × family)
    se = data.groupby(["seniority", "job_family"])["job_id"].nunique().reset_index(name="n")
    _write(con, "gold_seniority", se.sort_values("n", ascending=False))
    # gold_skill_cooccurrence (learning-path edges; unordered pairs)
    pair = Counter()
    for sk in data["skill_list"]:
        for a, b in combinations(sorted(set(sk)), 2):
            pair[(a, b)] += 1
    cooc = pd.DataFrame([(a, b, c) for (a, b), c in pair.items()],
                        columns=["skill_a", "skill_b", "n"]).sort_values("n", ascending=False)
    _write(con, "gold_skill_cooccurrence", cooc)

    rep = con.execute("""SELECT job_family, n, pct FROM gold_market_share
        ORDER BY n DESC LIMIT 12""").fetchall()
    con.close()
    print(f"\n{'='*64}\nINTEGRATE → jobs_silver.job_family + family Gold ({n} Data/AI jobs)\n{'='*64}")
    print("Market share (top families):")
    for f, c, p in rep:
        print(f"  {p:5.1f}%  {c:4d}  {f}")
    print("Gold tables: gold_jobs, gold_market_share, gold_family_skill, gold_company, "
          "gold_location, gold_seniority, gold_skill_cooccurrence")
