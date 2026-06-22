"""Gold layer: serving aggregates built from `jobs_silver` for the report/dashboard/model.

Computed ONLY over confirmed, current, de-duplicated Data jobs:
`role_category != 'OTHER' AND is_active AND is_duplicate_of IS NULL`.
All tables are descriptive — NO salary, NO forecasting (see PROJECT_STATUS §9/§11).
`trend` is descriptive over accumulated snapshots (from `job_observations`), not a forecast.

Run:  python -m pipeline gold
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from itertools import combinations

import duckdb
import pandas as pd

from ..utils.config import DATA_DIR

log = logging.getLogger("pipeline.gold")
DB_PATH = DATA_DIR / "warehouse.duckdb"

_FILTER = "role_category != 'OTHER' AND is_active AND is_duplicate_of IS NULL"


def _write(con, name: str, df: pd.DataFrame) -> None:
    con.register("_g", df)
    con.execute(f"DROP TABLE IF EXISTS {name}")
    con.execute(f"CREATE TABLE {name} AS SELECT * FROM _g")
    con.unregister("_g")


def run_gold() -> None:
    con = duckdb.connect(str(DB_PATH))
    sd = con.execute(f"""SELECT job_id, role_category, seniority, city, region, company_type, skills
                         FROM jobs_silver WHERE {_FILTER}""").df()
    n = len(sd)
    if n == 0:
        print("No confirmed Data jobs in jobs_silver — run `silver` first.")
        con.close()
        return
    sd["skill_list"] = sd["skills"].map(lambda s: json.loads(s) if isinstance(s, str) else [])
    long = (sd.explode("skill_list").dropna(subset=["skill_list"])
            .rename(columns={"skill_list": "skill"}))

    # 1. skill_demand — overall demand per skill
    sdm = (long.groupby("skill")["job_id"].nunique().reset_index(name="n_jobs")
           .sort_values("n_jobs", ascending=False))
    sdm["pct_of_all"] = (100.0 * sdm["n_jobs"] / n).round(1)
    _write(con, "skill_demand", sdm)

    # 2. role_skill_matrix — share of each skill within each role (role differentiation)
    role_tot = sd.groupby("role_category")["job_id"].nunique().to_dict()
    rsm = long.groupby(["role_category", "skill"])["job_id"].nunique().reset_index(name="n")
    rsm["share_in_role"] = rsm.apply(
        lambda r: round(100.0 * r["n"] / role_tot[r["role_category"]], 1), axis=1)
    rsm = rsm.sort_values(["role_category", "n"], ascending=[True, False])
    _write(con, "role_skill_matrix", rsm)

    # 3. seniority_progression — share of each skill within each seniority
    sen_tot = sd.groupby("seniority")["job_id"].nunique().to_dict()
    spg = long.groupby(["seniority", "skill"])["job_id"].nunique().reset_index(name="n")
    spg["share_in_seniority"] = spg.apply(
        lambda r: round(100.0 * r["n"] / sen_tot[r["seniority"]], 1), axis=1)
    spg = spg.sort_values(["seniority", "n"], ascending=[True, False])
    _write(con, "seniority_progression", spg)

    # 4. role_by_location
    rbl = (sd.dropna(subset=["city"]).groupby(["role_category", "region", "city"])["job_id"]
           .nunique().reset_index(name="n").sort_values("n", ascending=False))
    _write(con, "role_by_location", rbl)

    # 5. company_type_demand — role mix by company type
    ctd = (sd.groupby(["company_type", "role_category"])["job_id"].nunique()
           .reset_index(name="n").sort_values(["company_type", "n"], ascending=[True, False]))
    _write(con, "company_type_demand", ctd)

    # 6. skill_cooccurrence — learning-path edges (unordered skill pairs per job)
    pair = Counter()
    for sk in sd["skill_list"]:
        for a, b in combinations(sorted(set(sk)), 2):
            pair[(a, b)] += 1
    cooc = pd.DataFrame([(a, b, c) for (a, b), c in pair.items()],
                        columns=["skill_a", "skill_b", "n"]).sort_values("n", ascending=False)
    _write(con, "skill_cooccurrence", cooc)

    # 7. trend — skill counts per snapshot (descriptive; grows as weekly snapshots accumulate)
    obs = con.execute(
        "SELECT snapshot_date, source || ':' || source_job_id AS job_id FROM job_observations").df()
    tj = obs.merge(long[["job_id", "skill"]], on="job_id", how="inner")
    trend = (tj.groupby(["snapshot_date", "skill"])["job_id"].nunique()
             .reset_index(name="n").sort_values(["snapshot_date", "n"], ascending=[True, False]))
    _write(con, "trend", trend)

    # ---- report ----
    print(f"\n{'='*64}\nGOLD ({n} confirmed Data jobs)\n{'='*64}")
    for t in ["skill_demand", "role_skill_matrix", "seniority_progression",
              "role_by_location", "company_type_demand", "skill_cooccurrence", "trend"]:
        rows = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"  {t:22s} {rows} rows")
    print("\nTop 8 skills (skill_demand):")
    for s, nj, p in con.execute("SELECT skill,n_jobs,pct_of_all FROM skill_demand LIMIT 8").fetchall():
        print(f"  {p:5.1f}%  {nj:3d}  {s}")
    print("\nTop learning-path edges (skill_cooccurrence):")
    for a, b, c in con.execute("SELECT skill_a,skill_b,n FROM skill_cooccurrence LIMIT 6").fetchall():
        print(f"  {c:3d}  {a} + {b}")
    con.close()
    print(f"\nDone. 7 Gold tables in {DB_PATH}")
