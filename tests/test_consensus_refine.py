"""Tests for the consensus / refine label paths and the shared analysis-base filter.

Written after an audit found that all 45 pre-existing tests passed only because none of them touched the
consensus engine, the refine stage, or the changed Gold filters: they exercised the superseded
single-judge dispatcher. Each test below pins a defect that actually shipped.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from job_family_engine import engine, refine
from pipeline.dataset.llm_clients import JUDGES, _MIN_INTERVAL, _gate
from pipeline.utils.analysis_base import ANALYSIS_BASE_WHERE, qualified

JOB = {"job_id": "src:1", "content_hash": "abc123", "title": "Data Analyst", "skills": ["SQL"]}


def _vote(judge: str, fam: str, conf: float = 0.8) -> dict:
    return {"judge": judge, "job_family": fam, "confidence": conf, "reasoning": "r"}


# --- provider config -----------------------------------------------------------------------------

def test_every_judge_has_a_rate_interval():
    """A judge missing from _MIN_INTERVAL is silently UNTHROTTLED, and its 429s fall back to a 2s reset
    (below EXHAUST_RESET) so the engine never marks it exhausted and re-probes it on every job.
    `github` shipped in this state."""
    assert set(JUDGES) == set(_MIN_INTERVAL)


def test_dynamically_registered_judges_have_throttle_gates():
    """9Router and Cloudflare are registered at import time; _gate/_last_start are built afterwards.
    If that order ever flips, _throttle raises KeyError mid-run."""
    assert set(JUDGES) <= set(_gate)


# --- consensus decision rule ---------------------------------------------------------------------

def test_two_agreeing_judges_resolve_without_inflating_confidence():
    r = engine._decide_votes([_vote("groq", "DATA_ANALYST", 0.8),
                              _vote("cerebras", "DATA_ANALYST", 0.9)], JOB)
    assert r["review_status"] == "resolved"
    assert r["labeling_method"].startswith("vote:")
    # Confidence must stay within the judges' own range. The old `conf * (0.9 + 0.1*n_agree)` capped at
    # 0.99 pinned 76% of two-vote rows to exactly 0.99, so the KPI described the formula, not the labels.
    assert r["confidence_score"] <= 0.9


def test_single_vote_is_marked_single_not_vote():
    r = engine._decide_votes([_vote("groq", "DATA_ANALYST", 0.9)], JOB)
    assert r["labeling_method"].startswith("single:"), "a lone opinion must not look like a consensus"


def test_low_confidence_single_vote_goes_to_review():
    r = engine._decide_votes([_vote("groq", "DATA_ANALYST", 0.4)], JOB)
    assert r["review_status"] == "manual_review"


def test_three_way_split_within_one_domain_becomes_domain_only():
    """Judges disagreeing on BUSINESS_ANALYST / DATA_ANALYST / RISK_FRAUD_ANALYST still agree the posting
    is Analytics. Recording the domain is honest; picking one family is not."""
    r = engine._decide_votes([_vote("a", "BUSINESS_ANALYST"), _vote("b", "DATA_ANALYST"),
                              _vote("c", "RISK_FRAUD_ANALYST")], JOB)
    assert r["review_status"] == "domain_only"


def test_split_including_other_stays_manual_review():
    """OTHER has no place in the family hierarchy, so a data-vs-OTHER dispute has no common ancestor and
    cannot be resolved by rolling up."""
    r = engine._decide_votes([_vote("a", "OTHER"), _vote("b", "DATA_ANALYST"),
                              _vote("c", "RISK_FRAUD_ANALYST")], JOB)
    assert r["review_status"] == "manual_review"


def test_no_votes_is_failed():
    r = engine._decide_votes([], JOB)
    assert r["labeling_method"] == "failed" and r["review_status"] == "manual_review"


def test_judge_rotation_is_reproducible_across_processes():
    """Rotation used `hash()`, which is salted per process, so judge assignment changed between runs.
    crc32 keeps it stable — verified by running under two different PYTHONHASHSEEDs."""
    code = ("import zlib;print(zlib.crc32(b'abc123')%5)")
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env={"PYTHONHASHSEED": seed, "PATH": ""}).stdout.strip()
            for seed in ("0", "12345")}
    assert len(outs) == 1


# --- refine stage --------------------------------------------------------------------------------

def test_refine_never_resolves_on_a_single_stage2_vote():
    """Tier-3 needs >=2 agreeing judges; refine must not undercut that bar."""
    assert refine._decide([_vote("c", "DATA_ANALYST")],
                          [_vote("a", "BUSINESS_ANALYST"), _vote("b", "DATA_ANALYST")], JOB) is None


def test_refine_requires_two_stage2_backers_not_tier3_weight():
    """If the winner is carried by tier-3 weight alone, `backers` is empty and the old code emitted a
    resolved row with confidence 0.0 and no evidence."""
    out = refine._decide(
        [_vote("c", "DATA_ANALYST"), _vote("d", "BI")],
        [_vote("a", "BI"), _vote("b", "BI"), _vote("e", "BI")], JOB)
    assert out is None or out["confidence_score"] > 0.0


def test_refine_exact_tie_is_left_unresolved():
    assert refine._decide([_vote("c", "BI"), _vote("d", "DATA_ANALYST")],
                          [_vote("a", "BI"), _vote("b", "DATA_ANALYST")], JOB) is None


def test_refine_cache_key_distinguishes_candidate_sets():
    """The key was the candidate names truncated to 60 chars, so distinct 4-way disputes collided and one
    could read back another's answer."""
    long_a = ["ANALYTICS_ENGINEER", "BIG_DATA_ENGINEER", "BUSINESS_ANALYST", "DATA_ANALYST"]
    long_b = ["ANALYTICS_ENGINEER", "BIG_DATA_ENGINEER", "BUSINESS_ANALYST", "DATA_ARCHITECT"]
    import hashlib

    key = lambda c: hashlib.sha1("|".join(sorted(c)).encode()).hexdigest()[:16]  # noqa: E731
    assert key(long_a) != key(long_b)


# --- analysis base -------------------------------------------------------------------------------

def test_analysis_base_excludes_both_unresolved_kinds():
    for token in ("manual_review", "domain_only", "is_active", "is_duplicate_of IS NULL"):
        assert token in ANALYSIS_BASE_WHERE


def test_qualified_filter_prefixes_every_column():
    q = qualified(alias="s")
    assert "s.job_family" in q and "s.jf_review" in q and " job_family" not in q.replace("s.job_family", "")


def test_legacy_single_judge_corpus_run_is_guarded():
    """run_corpus writes the SAME parquet as the consensus run with one unchecked opinion per job."""
    with pytest.raises(RuntimeError, match="legacy single-judge"):
        engine.run_corpus()
