"""CLI entrypoint:  python -m pipeline <command> [options]

Run `python -m pipeline --help` for the full list; the summary that used to live here
advertised an `ingest` and a `bronze` command that were never written.

The chain `all` runs, in order:

    scrape -> load -> gate -> silver -> label -> refine -> enrich-llm
           -> integrate -> gold -> validate

`gate` sits between load and label on purpose. Labeling is the step that costs LLM quota,
so the check for "did a parser break and hand us several hundred fake postings" has to
happen before it, not after.

Every step records itself in `pipeline_runs`; `python -m pipeline runs` prints the history.
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
                       help="snapshot date YYYY-MM-DD (default: today). Names the Bronze "
                            "snapshot and the volatile listing-cache folder for this run.")

    p_enr = sub.add_parser("enrich", help="Fill description_raw (JD) on an existing Bronze file")
    p_enr.add_argument("--source", required=True)
    p_enr.add_argument("--delay", type=float, default=None, help="override detail-fetch delay (s)")
    p_enr.add_argument("--limit", type=int, default=None, help="cap number of details fetched")

    p_load = sub.add_parser("load", help="Incremental load Bronze → DuckDB warehouse (CDC upsert)")
    p_load.add_argument("--run-date", default=None, help="snapshot date YYYY-MM-DD (default today)")

    p_sil = sub.add_parser("silver", help="Normalize + dedup warehouse jobs → jobs_silver")
    p_sil.add_argument("--force", action="store_true",
                       help="rebuild even though it DROPs the labeling-engine columns (job_family, "
                            "jf_*) — you must re-run label/integrate afterwards")
    sub.add_parser("gold", help="Build serving aggregates (7 tables) from jobs_silver")

    p_disc = sub.add_parser("discover",
                            help="Dataset Phase 1: embed + cluster jobs → discovery report")
    p_disc.add_argument("--model", default=None, help="sentence-transformers model name")

    sub.add_parser("label", help="Job Family Labeling Engine: label all jobs → job_family.parquet")
    sub.add_parser("refine", help="Stage-2: settle disputed labels with a narrowed choice set + full JD")
    p_ellm = sub.add_parser("enrich-llm",
                            help="Fill seniority + employer industry where keyword rules gave up (LLM)")
    p_ellm.add_argument("--all", action="store_true",
                       help="also enrich rows outside the analysis base (slower)")
    sub.add_parser("apply-manual",
                   help="Apply hand-filled industries from data/labeling/company_industry_todo.csv")
    sub.add_parser("label-kpi", help="Engine KPI report + spot-check sample")
    sub.add_parser("integrate", help="Integrate job_family into jobs_silver + build family Gold")

    p_all = sub.add_parser("all", help="Run the whole chain: scrape → … → validate")
    p_all.add_argument("--from", dest="from_step", default=None, metavar="STEP",
                       help="resume the chain from this step (skip everything before it)")
    p_all.add_argument("--skip", nargs="*", default=[], metavar="STEP",
                       help="steps to leave out")
    p_all.add_argument("--dry-run", action="store_true",
                       help="print the steps that would run, then stop")
    p_all.add_argument("--allow-large-delta", action="store_true",
                       help="let the ingest gate pass even when the new-posting share is over "
                            "its allowance (use after checking the postings are real)")
    p_all.add_argument("--run-date", default=None, help="run date YYYY-MM-DD (default: today)")
    p_all.add_argument("--jd-limit", type=int, default=25)

    p_runs = sub.add_parser("runs", help="Show recent pipeline step history (pipeline_runs)")
    p_runs.add_argument("--limit", type=int, default=20)


    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    # `runs` only reads the log, so it must not write a row of its own.
    if args.command == "runs":
        from .utils.runlog import print_recent

        print_recent(limit=args.limit)
        return 0

    from .utils import runlog

    # `all` tracks each of its steps individually; tracking the wrapper too would double-count.
    if args.command == "all":
        return _run_all(args)

    # Every other command is one pipeline step: time it, count it, record how it ended.
    with runlog.track(args.command):
        return _dispatch(args)


#: The chain, in the only order that works. `gate` is not a standalone command — it is the
#: check that stands between loading and paying for labels.
ALL_STEPS = ["scrape", "load", "gate", "silver", "label", "refine",
             "enrich-llm", "integrate", "gold", "validate"]


def _run_all(args) -> int:
    """Run the chain, sharing one run_id so `pipeline_runs` groups it as a single execution."""
    import os
    from datetime import date

    from .utils import runlog

    run_date = (date.fromisoformat(args.run_date) if args.run_date else date.today())

    steps = ALL_STEPS
    if args.from_step:
        if args.from_step not in ALL_STEPS:
            print(f"Unknown step {args.from_step!r}. Known steps: {', '.join(ALL_STEPS)}")
            return 1
        steps = steps[ALL_STEPS.index(args.from_step):]
    unknown = [s for s in args.skip if s not in ALL_STEPS]
    if unknown:
        print(f"Unknown step(s) to skip: {unknown}. Known steps: {', '.join(ALL_STEPS)}")
        return 1
    steps = [s for s in steps if s not in args.skip]

    if args.dry_run:
        print(f"Would run for run_date={run_date}:")
        for i, s in enumerate(steps, 1):
            print(f"  {i}. {s}")
        return 0

    # One id for the whole chain. runlog reads this, so every step joins the same run.
    os.environ[runlog.RUN_ID_ENV] = runlog.new_run_id()
    run_id = runlog.current_run_id()
    print(f"\n{'#'*72}\n# PIPELINE ALL  run_id={run_id}  run_date={run_date}\n"
          f"# steps: {' -> '.join(steps)}\n{'#'*72}")

    for i, step in enumerate(steps, 1):
        print(f"\n{'#'*72}\n# [{i}/{len(steps)}] {step}\n{'#'*72}")
        try:
            with runlog.track(step):
                code = _run_one(step, args, run_date)
        except Exception as exc:  # noqa: BLE001 — report and stop the chain, do not traceback
            print(f"\nSTOPPED at step {step!r}: {type(exc).__name__}: {exc}")
            print(f"Resume with:  python -m pipeline all --from {step}")
            return 1
        if code != 0:
            print(f"\nSTOPPED at step {step!r} (exit {code}).")
            print(f"Resume with:  python -m pipeline all --from {step}")
            return code

    print(f"\n{'#'*72}\n# DONE — all {len(steps)} steps passed (run_id={run_id})\n{'#'*72}")
    return 0


def _run_one(step: str, args, run_date) -> int:
    """Run a single chain step. Raises or returns non-zero to stop the chain."""
    if step == "scrape":
        from .scrape import run_scrape

        run_scrape(jd_limit=args.jd_limit, run_date=run_date.isoformat())
        return 0

    if step == "load":
        from .transform.load import run_load

        run_load(run_date_str=run_date.isoformat())
        return 0

    if step == "gate":
        from .gates import check_ingest_delta, print_report, stale_sources

        delta = check_ingest_delta(run_date, allow_large=args.allow_large_delta)
        print_report(run_date, delta, stale_sources(run_date))
        return 0

    if step == "silver":
        from .transform.silver import run_silver

        # The chain rebuilds labels immediately afterwards (label -> refine -> integrate),
        # and the label cache is keyed on content_hash so unchanged postings cost nothing to
        # re-decide. Outside the chain `silver` still refuses without --force.
        run_silver(force=True)
        return 0

    if step == "validate":
        import subprocess
        import sys
        from pathlib import Path

        script = Path(__file__).resolve().parents[1] / "analysis" / "validate_gold.py"
        return subprocess.run([sys.executable, str(script)]).returncode

    # The remaining steps take no arguments and share the plain dispatch path.
    simple = {"label": ("job_family_engine.engine", "run_corpus_consensus"),
              "refine": ("job_family_engine.refine", "refine_unresolved"),
              "enrich-llm": ("pipeline.transform.enrich_llm", "enrich"),
              "integrate": ("job_family_engine.integrate", "integrate"),
              "gold": ("pipeline.transform.gold", "run_gold")}
    module_name, func_name = simple[step]
    module = __import__(module_name, fromlist=[func_name])
    getattr(module, func_name)()
    return 0


def _dispatch(args) -> int:
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

        run_silver(force=args.force)
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
        # Consensus path: every tier-3 job needs >=2 judges to agree (3rd arbitrates). `run_corpus`
        # (one judge per job) is kept in the engine for single-job/predict use, but the corpus run
        # must not decide a label on one unchecked opinion.
        from job_family_engine.engine import run_corpus_consensus

        run_corpus_consensus()
        return 0

    if args.command == "refine":
        from job_family_engine.refine import refine_unresolved

        refine_unresolved()
        return 0

    if args.command == "enrich-llm":
        from pipeline.transform.enrich_llm import enrich

        enrich(only_base=not args.all)
        return 0

    if args.command == "apply-manual":
        from pipeline.transform.enrich_llm import apply_manual

        apply_manual()
        return 0

    if args.command == "label-kpi":
        from job_family_engine.evaluate import run_eval

        run_eval()
        return 0

    if args.command == "integrate":
        from job_family_engine.integrate import integrate

        integrate()
        return 0

    print(f"Command '{args.command}' has no handler — this is a bug in __main__.py, "
          f"not a missing feature.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
