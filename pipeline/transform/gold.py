"""Gold layer: serving aggregates built from `jobs_silver` for the report/dashboard/model.

Keyed on **`job_family`** (the Job Family Labeling Engine's output), NOT the legacy title-derived
`role_category`. Until 2026-07-25 this module filtered and grouped by `role_category`, which is
deprecated (~27% contaminated) — so these tables described a *different population* (~597 jobs) from the
family tables that `job_family_engine/integrate.py` builds (`gold_*`), and a relabel did not move them at
all. Anyone joining `skill_cooccurrence` against `gold_market_share` silently mixed two populations.

Analysis base mirrors `integrate.py` exactly: labeled, non-OTHER, resolved, active, non-duplicate.
Requires `python -m pipeline label && python -m pipeline integrate` to have run first.

All tables are descriptive — NO salary, NO forecasting: both are out of scope for this project.
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

from ..utils import runlog
from ..utils.config import DATA_DIR

log = logging.getLogger("pipeline.gold")
DB_PATH = DATA_DIR / "warehouse.duckdb"

# Single source of truth — see pipeline/utils/analysis_base.py for why this must not be re-typed.
from ..utils.analysis_base import ANALYSIS_BASE_WHERE


def _write(con, name: str, df: pd.DataFrame) -> None:
    con.register("_g", df)
    con.execute(f"DROP TABLE IF EXISTS {name}")
    con.execute(f"CREATE TABLE {name} AS SELECT * FROM _g")
    con.unregister("_g")


def run_gold() -> None:
    con = duckdb.connect(str(DB_PATH))
    cols = {r[0] for r in con.execute("DESCRIBE jobs_silver").fetchall()}
    if "job_family" not in cols:
        # Exit NON-ZERO. Returning 0 here left the previous `gold_*` tables in place while `jobs_silver`
        # had no labels at all, and `analysis/market_insights.py` reads only the gold tables — so it
        # regenerated every figure from the stale aggregates without a single error. A shell chain
        # (`silver && gold && market_insights`) has to stop here.
        con.close()
        raise SystemExit("jobs_silver has no job_family column — the label columns are gone (did you "
                         "re-run `silver`?). Run `python -m pipeline label` then `integrate` first; "
                         "the existing gold_* tables are now STALE and were left untouched.")
    where = ANALYSIS_BASE_WHERE if "jf_review" in cols else ANALYSIS_BASE_WHERE.split(" AND COALESCE")[0]
    sd = con.execute(f"""SELECT job_id, job_family, seniority, city, region, company_type, skills
                         FROM jobs_silver WHERE {where}""").df()
    n = len(sd)
    if n == 0:
        print("No labeled Data jobs in jobs_silver — run `silver`, `label`, `integrate` first.")
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

    # 2. role_skill_matrix — share of each skill within each job family (family differentiation)
    fam_tot = sd.groupby("job_family")["job_id"].nunique().to_dict()
    rsm = long.groupby(["job_family", "skill"])["job_id"].nunique().reset_index(name="n")
    rsm["share_in_family"] = rsm.apply(
        lambda r: round(100.0 * r["n"] / fam_tot[r["job_family"]], 1), axis=1)
    rsm = rsm.sort_values(["job_family", "n"], ascending=[True, False])
    _write(con, "role_skill_matrix", rsm)

    # 3. seniority_progression — share of each skill within each seniority
    sen_tot = sd.groupby("seniority")["job_id"].nunique().to_dict()
    spg = long.groupby(["seniority", "skill"])["job_id"].nunique().reset_index(name="n")
    spg["share_in_seniority"] = spg.apply(
        lambda r: round(100.0 * r["n"] / sen_tot[r["seniority"]], 1), axis=1)
    spg = spg.sort_values(["seniority", "n"], ascending=[True, False])
    _write(con, "seniority_progression", spg)

    # 4. role_by_location
    rbl = (sd.dropna(subset=["city"]).groupby(["job_family", "region", "city"])["job_id"]
           .nunique().reset_index(name="n").sort_values("n", ascending=False))
    _write(con, "role_by_location", rbl)

    # 5. company_type_demand — family mix by company type
    ctd = (sd.groupby(["company_type", "job_family"])["job_id"].nunique()
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
    print(f"\n{'='*64}\nGOLD ({n} labeled Data jobs, keyed on job_family)\n{'='*64}")
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
    total_gold = sum(con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                     for t in ["skill_demand", "role_skill_matrix", "seniority_progression",
                               "role_by_location", "company_type_demand",
                               "skill_cooccurrence", "trend"])
    con.close()
    runlog.set_rows(rows_in=n, rows_out=total_gold)
    print(f"\nDone. 7 Gold tables in {DB_PATH}")
