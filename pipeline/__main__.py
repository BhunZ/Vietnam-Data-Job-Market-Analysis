"""CLI entrypoint:  python -m pipeline <command> [options]

Commands (per PROJECT_SPEC §4):
  inspect   Phase 1 spike — sample one source, persist raw, print data shape + volume.
  ingest    Fetch + persist raw for enabled sources.        (Phase 2)
  bronze    Parse raw -> typed Bronze.                       (Phase 2)
  silver    Normalize + dedup -> Silver.                     (Phase 3)
  gold      Build serving aggregates -> Gold.                (Phase 4)
  all       Run ingest -> bronze -> silver -> gold.          (Phase 4)
"""

from __future__ import annotations

import argparse
import logging
import sys


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    # Force UTF-8 stdout so Vietnamese text prints on Windows (cp1252) consoles.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

    parser = argparse.ArgumentParser(prog="python -m pipeline")
    parser.add_argument("-v", "--verbose", action="store_true", help="log fetch activity")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ins = sub.add_parser("inspect", help="Phase 1 spike: sample + data shape + volume")
    p_ins.add_argument("--source", default="itviec")
    p_ins.add_argument("--sample", type=int, default=25, help="target unique postings")
    p_ins.add_argument("--details", type=int, default=10, help="how many descriptions to fetch")

    p_scr = sub.add_parser("scrape", help="Scaled multi-source scrape + block/capacity report")
    p_scr.add_argument("--jd-limit", type=int, default=25,
                       help="max ITviec JD detail fetches (API sources include JD inline)")
    p_scr.add_argument("--max-live-fetches", type=int, default=60,
                       help="credit guard: hard cap on live ScraperAPI fetches per source")
    p_scr.add_argument("--run-date", default=None,
                       help="snapshot date (default: reuse latest existing snapshot)")

    p_enr = sub.add_parser("enrich", help="Fill description_raw (JD) on an existing Bronze file")
    p_enr.add_argument("--source", required=True)
    p_enr.add_argument("--delay", type=float, default=None, help="override detail-fetch delay (s)")
    p_enr.add_argument("--limit", type=int, default=None, help="cap number of details fetched")

    p_load = sub.add_parser("load", help="Incremental load Bronze → DuckDB warehouse (CDC upsert)")
    p_load.add_argument("--run-date", default=None, help="snapshot date YYYY-MM-DD (default today)")

    sub.add_parser("silver", help="Normalize + dedup warehouse jobs → jobs_silver")
    sub.add_parser("gold", help="Build serving aggregates (7 tables) from jobs_silver")

    p_disc = sub.add_parser("discover",
                            help="Dataset Phase 1: embed + cluster jobs → discovery report")
    p_disc.add_argument("--model", default=None, help="sentence-transformers model name")

    sub.add_parser("label", help="Job Family Labeling Engine: label all jobs → job_family.parquet")
    sub.add_parser("label-kpi", help="Engine KPI report + spot-check sample")
    sub.add_parser("integrate", help="Integrate job_family into jobs_silver + build family Gold")

    sub.add_parser("all", help="(chưa triển khai — xem PROJECT_STATUS §8)")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    if args.command == "inspect":
        from .inspect import run_inspect

        run_inspect(source=args.source, sample_size=args.sample, details=args.details)
        return 0

    if args.command == "scrape":
        from .scrape import run_scrape

        run_scrape(jd_limit=args.jd_limit, max_live_fetches=args.max_live_fetches,
                   run_date=args.run_date)
        return 0

    if args.command == "enrich":
        from .enrich import run_enrich

        run_enrich(source=args.source, delay=args.delay, limit=args.limit)
        return 0

    if args.command == "load":
        from .transform.load import run_load

        run_load(run_date_str=args.run_date)
        return 0

    if args.command == "silver":
        from .transform.silver import run_silver

        run_silver()
        return 0

    if args.command == "gold":
        from .transform.gold import run_gold

        run_gold()
        return 0

    if args.command == "discover":
        from .dataset.embed import DEFAULT_MODEL
        from .dataset.run import run_discovery_pipeline

        run_discovery_pipeline(model_name=args.model or DEFAULT_MODEL)
        return 0

    if args.command == "label":
        from job_family_engine.engine import run_corpus

        run_corpus()
        return 0

    if args.command == "label-kpi":
        from job_family_engine.evaluate import run_eval

        run_eval()
        return 0

    if args.command == "integrate":
        from job_family_engine.integrate import integrate

        integrate()
        return 0

    print(f"Command '{args.command}' is not implemented yet (Phase 1 ships 'inspect' only).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
