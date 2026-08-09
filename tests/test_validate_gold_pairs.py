"""The duplicate-aggregate check in analysis/validate_gold.py.

Four aggregates are computed twice, by two steps that nothing forces to run together:
`pipeline gold` writes the bare names, `pipeline integrate` writes the `gold_` ones. On
2026-08-09 `integrate` ran after a silver rebuild and `gold` did not, leaving
`gold_market_share` describing 202 postings while `skill_demand` still described June's
720 — two answers to the same question, sitting in one warehouse with nothing complaining.

A check that cannot fail is a report. Every test below is about making it fail.
"""

import duckdb
import pytest

import analysis.validate_gold as V

_MATCHING = {
    "skill_cooccurrence": ("skill_a VARCHAR, skill_b VARCHAR, n INTEGER",
                           [("Python", "SQL", 10), ("Excel", "SQL", 4)]),
    "gold_skill_cooccurrence": ("skill_a VARCHAR, skill_b VARCHAR, n INTEGER",
                                [("Python", "SQL", 10), ("Excel", "SQL", 4)]),
    # Column order differs between the two writers on purpose — the check names columns
    # explicitly rather than trusting position, and this is what guards that.
    "role_by_location": ("job_family VARCHAR, region VARCHAR, city VARCHAR, n INTEGER",
                         [("DATA_ENGINEER", "North", "Ha Noi", 7)]),
    "gold_location": ("region VARCHAR, city VARCHAR, job_family VARCHAR, n INTEGER",
                      [("North", "Ha Noi", "DATA_ENGINEER", 7)]),
    "company_type_demand": ("company_type VARCHAR, job_family VARCHAR, n INTEGER",
                            [("bank_finance", "BI", 3)]),
    "gold_company": ("company_type VARCHAR, job_family VARCHAR, n INTEGER",
                     [("bank_finance", "BI", 3)]),
    "role_skill_matrix": ("job_family VARCHAR, skill VARCHAR, n INTEGER, share_in_family DOUBLE",
                          [("DATA_ENGINEER", "SQL", 9, 0.75)]),
    "gold_family_skill": ("job_family VARCHAR, skill VARCHAR, n INTEGER, share_in_family DOUBLE",
                          [("DATA_ENGINEER", "SQL", 9, 0.75)]),
}


@pytest.fixture
def con(tmp_path):
    c = duckdb.connect(str(tmp_path / "wh.duckdb"))
    for table, (schema, rows) in _MATCHING.items():
        c.execute(f"CREATE TABLE {table} ({schema})")
        placeholders = ", ".join(["?"] * len(rows[0]))
        c.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
    yield c
    c.close()


def test_matching_pairs_report_no_problem(con):
    assert V.compare_duplicate_pairs(con) == []


def test_a_stale_copy_is_caught(con):
    """The 2026-08-09 shape: one writer ran, the other did not."""
    con.execute("DELETE FROM skill_cooccurrence WHERE skill_a = 'Excel'")

    problems = V.compare_duplicate_pairs(con)

    assert len(problems) == 1
    assert "skill_cooccurrence" in problems[0] and "gold_skill_cooccurrence" in problems[0]
    assert "stale" in problems[0]


def test_same_row_count_but_different_numbers_is_caught(con):
    """Row counts can match while the values behind them do not."""
    con.execute("UPDATE gold_company SET n = 999")

    problems = V.compare_duplicate_pairs(con)

    assert any("company_type_demand" in p for p in problems)


def test_column_order_alone_is_not_a_mismatch(con):
    """role_by_location leads with job_family, gold_location with region. Same data."""
    assert not any("role_by_location" in p for p in V.compare_duplicate_pairs(con))


def test_a_float_that_only_differs_past_four_places_is_not_a_mismatch(con):
    """share_in_family is a ratio; rounding noise must not raise an alarm."""
    con.execute("UPDATE gold_family_skill SET share_in_family = 0.75000001")

    assert not any("role_skill_matrix" in p for p in V.compare_duplicate_pairs(con))


def test_a_real_difference_in_that_float_is_a_mismatch(con):
    con.execute("UPDATE gold_family_skill SET share_in_family = 0.9")

    assert any("role_skill_matrix" in p for p in V.compare_duplicate_pairs(con))


def test_a_missing_table_is_reported_rather_than_crashing(con):
    con.execute("DROP TABLE gold_company")

    problems = V.compare_duplicate_pairs(con)

    assert any("company_type_demand" in p and "cannot compare" in p for p in problems)


def test_every_pair_is_actually_checked(con):
    """Each pair must be able to fail on its own, or it is decoration."""
    for legacy, family, _cols in V.DUPLICATE_PAIRS:
        con.execute(f"CREATE OR REPLACE TABLE {legacy}_backup AS SELECT * FROM {legacy}")
        con.execute(f"DELETE FROM {legacy}")
        assert any(legacy in p for p in V.compare_duplicate_pairs(con)), (
            f"emptying {legacy} did not make the check complain")
        con.execute(f"INSERT INTO {legacy} SELECT * FROM {legacy}_backup")


def test_seniority_tables_are_not_compared():
    """`seniority_progression` is seniority × skill; `gold_seniority` is seniority × family.
    Same-looking names, different grain — comparing them would fail forever."""
    pairs = {(a, b) for a, b, _ in V.DUPLICATE_PAIRS}
    assert ("seniority_progression", "gold_seniority") not in pairs
