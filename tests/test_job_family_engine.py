"""Unit tests for the deterministic parts of the Job Family Labeling Engine (no network/model)."""

from job_family_engine import rules, taxonomy
from job_family_engine.llm_judge import _coerce_code


def test_taxonomy_loads():
    codes = taxonomy.codes()
    assert "OTHER" in codes
    for c in ["DATA_ENGINEER", "DATA_ANALYST", "BUSINESS_ANALYST", "AI_ENGINEER", "GENAI_LLM"]:
        assert c in codes
    m = taxonomy.meta("DATA_ENGINEER")
    assert m["domain"] == "Data Engineering" and m["aliases"]


def test_prompt_catalog_nonempty():
    cat = taxonomy.prompt_catalog()
    assert "DATA_ENGINEER" in cat and "OTHER" in cat


def test_rule_clear_titles():
    assert rules.tier1("Senior Data Engineer")[0] == "DATA_ENGINEER"
    assert rules.tier1("Data Scientist")[0] == "DATA_SCIENTIST"
    assert rules.tier1("BI Analyst")[0] == "BI"


def test_rule_business_analyst_is_own_family_not_da():
    # the old bug mapped business analyst -> DA; now its own family
    assert rules.tier1("Business Analyst")[0] == "BUSINESS_ANALYST"


def test_rule_separator_fix():
    # hyphen/underscore must not break the match (old bug)
    assert rules.tier1("Data-Engineer_HN")[0] == "DATA_ENGINEER"


def test_rule_ambiguous_defers():
    # ambiguous / non-data titles → no high-confidence tier-1 label
    assert rules.tier1("Specialist")[0] is None
    assert rules.tier1("Nhân viên Kinh doanh")[0] is None


def test_coerce_code():
    assert _coerce_code("DATA_ENGINEER") == "DATA_ENGINEER"
    assert _coerce_code("data engineer") == "DATA_ENGINEER"   # by family name (lowercased)
    assert _coerce_code("totally bogus") is None


# --- Tier-3 rate-limit parsing + dynamic-dispatch failover (no network) ---

def test_reset_seconds_from_message_body():
    from job_family_engine.llm_judge import _reset_seconds
    e = Exception("Error code: 429 - rate limit reached. Please try again in 7.66s. Visit ...")
    assert 7.0 <= _reset_seconds(e, "groq") <= 8.5


def test_reset_seconds_from_header():
    from job_family_engine.llm_judge import _reset_seconds

    class _Resp:
        headers = {"retry-after": "13"}

    e = Exception("429")
    e.response = _Resp()  # type: ignore[attr-defined]
    assert _reset_seconds(e, "groq") == 13.0


def test_reset_seconds_daily_quota_marks_long():
    # a daily/plan/quota message must yield a long reset → engine exhausts + reroutes
    from job_family_engine.llm_judge import _reset_seconds
    e = Exception("Error code: 429 - You exceeded your current quota, please check your plan")
    assert _reset_seconds(e, "gemini") >= 3600.0


def test_is_rate_limit_detection():
    from job_family_engine.llm_judge import _is_rate_limit
    assert _is_rate_limit(Exception("Error code: 429 - Too Many Requests"))
    assert _is_rate_limit(Exception("rate limit reached for model"))
    assert not _is_rate_limit(Exception("connection reset by peer"))


def test_dispatch_failover_reroutes_when_a_provider_dies(monkeypatch):
    """A provider hitting a hard (long-reset) 429 must be marked exhausted and its jobs
    re-routed to a provider with capacity — every job still gets labeled."""
    from job_family_engine import engine, llm_judge

    dead = engine._PState(key="dead", min_interval=0.0, cap=1000)
    live = engine._PState(key="live", min_interval=0.0, cap=1000)
    monkeypatch.setattr(engine, "_active_states", lambda: [dead, live])
    monkeypatch.setattr(llm_judge, "cached_any", lambda job: None)

    def fake_once(judge_key, job):
        if judge_key == "dead":
            raise llm_judge.RateLimited(3600.0)   # daily-cap style → should exhaust + reroute
        return {"job_id": job["job_id"], "judge": "live-model",
                "job_family": "DATA_ENGINEER", "confidence": 0.9, "reasoning": "ok"}

    monkeypatch.setattr(llm_judge, "classify_once", fake_once)
    jobs = [{"job_id": f"j{i}", "content_hash": f"h{i}", "title": "x"} for i in range(25)]
    results: list = []
    engine._label_remainder(jobs, results, len(jobs))

    assert len(results) == 25
    assert all(r["job_family"] == "DATA_ENGINEER" for r in results)
    assert all(r["labeling_method"] == "llm:live" for r in results)
    assert dead.exhausted and live.used == 25


def test_dispatch_all_exhausted_falls_back_to_manual_review(monkeypatch):
    """If every provider is rate-limited hard, remaining jobs are finalized as manual_review
    (resumable next run) rather than hanging forever."""
    from job_family_engine import engine, llm_judge

    s = engine._PState(key="only", min_interval=0.0, cap=1000)
    monkeypatch.setattr(engine, "_active_states", lambda: [s])
    monkeypatch.setattr(llm_judge, "cached_any", lambda job: None)
    monkeypatch.setattr(llm_judge, "classify_once",
                        lambda jk, job: (_ for _ in ()).throw(llm_judge.RateLimited(9999.0)))
    jobs = [{"job_id": f"j{i}", "content_hash": f"h{i}", "title": "x"} for i in range(5)]
    results: list = []
    engine._label_remainder(jobs, results, len(jobs))

    assert len(results) == 5
    assert all(r["review_status"] == "manual_review" for r in results)


def test_dispatch_uses_cache_without_spending_quota(monkeypatch):
    """Cached jobs (resume) are returned without ever calling a provider."""
    from job_family_engine import engine, llm_judge

    s = engine._PState(key="only", min_interval=0.0, cap=1000)
    monkeypatch.setattr(engine, "_active_states", lambda: [s])
    monkeypatch.setattr(llm_judge, "cached_any",
                        lambda job: {"job_id": job["job_id"], "judge": "groq-llama-3.1-8b",
                                     "job_family": "DATA_ANALYST", "confidence": 0.8, "reasoning": "cached"})

    def _boom(jk, job):
        raise AssertionError("classify_once must not be called when a cache hit exists")

    monkeypatch.setattr(llm_judge, "classify_once", _boom)
    jobs = [{"job_id": f"j{i}", "content_hash": f"h{i}", "title": "x"} for i in range(8)]
    results: list = []
    engine._label_remainder(jobs, results, len(jobs))

    assert len(results) == 8
    assert all(r["job_family"] == "DATA_ANALYST" for r in results)
    assert s.used == 0  # no live calls


def _ok_rec(judge, job, fam="DATA_ENGINEER", conf=0.9):
    return {"job_id": job["job_id"], "judge": judge, "job_family": fam,
            "confidence": conf, "reasoning": "ok"}


def test_dispatch_short_cooldown_reroute_then_success(monkeypatch):
    """The dominant real-world path: a transient (per-minute) 429 cools the provider briefly, the job
    is re-queued, and the retry succeeds. The provider must NOT be exhausted and every job is resolved."""
    from job_family_engine import engine, llm_judge

    s = engine._PState(key="only", min_interval=0.0, cap=1000)
    monkeypatch.setattr(engine, "_active_states", lambda: [s])
    monkeypatch.setattr(llm_judge, "cached_any", lambda job: None)
    seen: dict = {}

    def fake_once(judge_key, job):
        jid = job["job_id"]
        seen[jid] = seen.get(jid, 0) + 1
        if seen[jid] == 1:
            raise llm_judge.RateLimited(0.02)   # short → cooldown, NOT exhaust
        return _ok_rec("only-model", job)

    monkeypatch.setattr(llm_judge, "classify_once", fake_once)
    jobs = [{"job_id": f"j{i}", "content_hash": f"h{i}", "title": "x"} for i in range(6)]
    results: list = []
    engine._label_remainder(jobs, results, len(jobs))

    assert len(results) == 6
    assert all(r["labeling_method"] == "llm:only" for r in results)
    assert all(r["review_status"] == "resolved" for r in results)
    assert not s.exhausted          # a short 429 must never exhaust a provider
    assert s.used == 6              # each job eventually succeeded exactly once


def test_dispatch_max_attempts_drops_to_manual_review(monkeypatch):
    """A job that keeps hitting short 429s across providers is dropped to manual_review after
    MAX_ATTEMPTS re-routes (not retried forever)."""
    from job_family_engine import engine, llm_judge

    monkeypatch.setattr(engine, "MAX_ATTEMPTS", 3)
    a = engine._PState(key="pa", min_interval=0.0, cap=1000)
    b = engine._PState(key="pb", min_interval=0.0, cap=1000)
    monkeypatch.setattr(engine, "_active_states", lambda: [a, b])
    monkeypatch.setattr(llm_judge, "cached_any", lambda job: None)
    calls = [0]

    def always_429(judge_key, job):
        calls[0] += 1
        raise llm_judge.RateLimited(0.01)   # short → never exhausts; job just bounces

    monkeypatch.setattr(llm_judge, "classify_once", always_429)
    jobs = [{"job_id": "j0", "content_hash": "h0", "title": "x"}]
    results: list = []
    engine._label_remainder(jobs, results, len(jobs))

    assert len(results) == 1
    assert results[0]["review_status"] == "manual_review"
    assert "max retries" in results[0]["reasoning"]
    assert calls[0] == 3            # exactly MAX_ATTEMPTS live attempts, then dropped


def test_dispatch_daily_cap_exhausts_and_reroutes(monkeypatch):
    """A provider that fills its daily cap with SUCCESSES is marked exhausted and the rest reroute
    (distinct from the 429-driven exhaust path)."""
    from job_family_engine import engine, llm_judge

    a = engine._PState(key="small", min_interval=0.0, cap=2)
    b = engine._PState(key="big", min_interval=0.0, cap=1000)
    monkeypatch.setattr(engine, "_active_states", lambda: [a, b])
    monkeypatch.setattr(llm_judge, "cached_any", lambda job: None)
    monkeypatch.setattr(llm_judge, "classify_once", lambda jk, job: _ok_rec(jk, job))
    jobs = [{"job_id": f"j{i}", "content_hash": f"h{i}", "title": "x"} for i in range(10)]
    results: list = []
    engine._label_remainder(jobs, results, len(jobs))

    assert len(results) == 10
    assert all(r["review_status"] == "resolved" for r in results)
    assert a.exhausted and a.used >= a.cap        # small provider hit its cap and was retired
    assert a.used + b.used == 10                  # every job counted as a success exactly once


def test_dispatch_mixed_cache_and_live(monkeypatch):
    """Realistic resume: some jobs cached, the rest live — quota spent only on the misses."""
    from job_family_engine import engine, llm_judge

    s = engine._PState(key="live", min_interval=0.0, cap=1000)
    monkeypatch.setattr(engine, "_active_states", lambda: [s])
    monkeypatch.setattr(llm_judge, "cached_any",
                        lambda job: (_ok_rec("cached-model", job, fam="DATA_ANALYST", conf=0.8)
                                     if int(job["job_id"][1:]) % 2 == 0 else None))
    monkeypatch.setattr(llm_judge, "classify_once", lambda jk, job: _ok_rec(jk, job))
    jobs = [{"job_id": f"j{i}", "content_hash": f"h{i}", "title": "x"} for i in range(10)]
    results: list = []
    engine._label_remainder(jobs, results, len(jobs))

    assert len(results) == 10
    by_id = {r["job_id"]: r for r in results}
    cached = [r for r in results if r["labeling_method"] == "llm:cached-model"]
    live = [r for r in results if r["labeling_method"] == "llm:live"]
    assert len(cached) == 5 and len(live) == 5
    assert by_id["j0"]["job_family"] == "DATA_ANALYST"   # cached
    assert by_id["j1"]["job_family"] == "DATA_ENGINEER"  # live
    assert s.used == 5   # only the 5 misses spent quota


def test_reset_seconds_retry_after_ms_and_window_headers():
    from job_family_engine.llm_judge import _reset_seconds

    class _Resp:
        def __init__(self, h):
            self.headers = h

    e1 = Exception("429")
    e1.response = _Resp({"retry-after-ms": "2500"})  # type: ignore[attr-defined]
    assert abs(_reset_seconds(e1, "groq") - 2.5) < 0.01

    e2 = Exception("429")
    e2.response = _Resp({"x-ratelimit-reset-requests": "1m30s"})  # type: ignore[attr-defined]
    assert _reset_seconds(e2, "groq") == 90.0


def test_reset_seconds_hours_format_exhausts():
    # Groq's daily-cap 429 says "try again in 1h23m45.6s" — must parse to a LONG reset (>EXHAUST_RESET),
    # not ~1s, so the engine marks the provider exhausted and reroutes instead of hammering it.
    from job_family_engine.llm_judge import _reset_seconds
    from job_family_engine.engine import EXHAUST_RESET
    e = Exception("Rate limit reached for model X. Please try again in 1h23m45.6s. Limit ...")
    assert _reset_seconds(e, "groq") > EXHAUST_RESET
    assert abs(_reset_seconds(e, "groq") - (3600 + 23 * 60 + 45.6)) < 1.0


def test_is_rate_limit_no_false_positive_on_embedded_429():
    from job_family_engine.llm_judge import _is_rate_limit
    # word-boundary 429 only: ids / token counts that merely contain 429 are NOT rate limits
    assert not _is_rate_limit(Exception("connection to req_4290xyz failed"))
    assert not _is_rate_limit(Exception("max_tokens 4290 exceeds model context window"))
    assert not _is_rate_limit(Exception("invalid api key"))
    # genuine signals still detected
    assert _is_rate_limit(Exception("Error code: 429 - Too Many Requests"))
    assert _is_rate_limit(Exception("rate limit reached for model"))
    assert _is_rate_limit(Exception("You exceeded your current quota"))


def test_provider_key_for_maps_name_to_key():
    from job_family_engine.llm_judge import provider_key_for
    assert provider_key_for("groq-llama-3.1-8b") == "groq8b"
    assert provider_key_for("gemini-2.0-flash") == "gemini"
    assert provider_key_for("unknown-model") == "unknown-model"  # fallback


def test_run_corpus_dedups_by_content_hash_and_fans_out(monkeypatch):
    """Duplicate postings (same content_hash) get ONE LLM call; the label fans out to all siblings,
    so coverage stays 100% and identical content shares an identical family."""
    import pandas as pd
    from job_family_engine import engine

    jobs = pd.DataFrame([
        {"job_id": "a1", "content_hash": "H1", "title": "t", "skills": [], "jd": ""},
        {"job_id": "a2", "content_hash": "H1", "title": "t", "skills": [], "jd": ""},  # dup of a1
        {"job_id": "b1", "content_hash": "H2", "title": "t", "skills": [], "jd": ""},
        {"job_id": "c1", "content_hash": "H3", "title": "t", "skills": [], "jd": ""},
        {"job_id": "c2", "content_hash": "H3", "title": "t", "skills": [], "jd": ""},  # dup of c1
    ])
    monkeypatch.setattr(engine.pd, "read_parquet", lambda *a, **k: jobs)
    monkeypatch.setattr(engine.embed_match, "_prototypes", lambda: None)
    monkeypatch.setattr(engine.embed_match, "_job_vectors", lambda: None)
    monkeypatch.setattr(engine, "_tier12", lambda job: None)             # force all to the LLM tier
    monkeypatch.setattr(engine._io, "write_parquet", lambda df, *a, **k: df)

    def fake_label(reps, rep_results, nn):
        for rep in reps:
            rep_results.append(engine._result(rep, "DATA_ANALYST", 0.9, f"llm:x",
                                              [{"judge": "x", "job_family": "DATA_ANALYST",
                                                "confidence": 0.9}], "r", "resolved"))

    monkeypatch.setattr(engine, "_label_remainder", fake_label)
    out = engine.run_corpus()

    assert len(out) == 5                                   # every posting present (coverage 100%)
    assert set(out["job_id"]) == {"a1", "a2", "b1", "c1", "c2"}
    assert (out["job_family"] == "DATA_ANALYST").all()     # dup siblings share the rep's label


def test_read_cache_self_heals_corrupt_file(tmp_path):
    from job_family_engine.llm_judge import _read_cache
    good = tmp_path / "good.json"
    good.write_text('{"job_family": "DATA_ANALYST"}', encoding="utf-8")
    assert _read_cache(good) == {"job_family": "DATA_ANALYST"}

    bad = tmp_path / "bad.json"
    bad.write_text("{ truncated…", encoding="utf-8")
    assert _read_cache(bad) is None        # corrupt → returns None …
    assert not bad.exists()                # … and deletes the poisoned file so it gets re-labeled
