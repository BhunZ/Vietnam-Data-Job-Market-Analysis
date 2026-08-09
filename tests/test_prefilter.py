"""Tier 0 (job_family_engine/prefilter.py).

The rule spends nothing and is therefore allowed to be wrong in only one direction. Killing
a sales posting saves an LLM call; killing a real Data posting removes it from the analysis
silently and permanently. Every case below that starts "must NOT" is guarding that side.

Titles are real ones from the 2026-06-16 corpus.
"""

import pytest

from job_family_engine import prefilter


# --- fires on obvious non-Data roles ----------------------------------------------

@pytest.mark.parametrize("title, expected_rule", [
    ("Nhân Viên Bán Hàng", "sales"),
    ("nhân viên tư vấn bán hàng", "sales"),
    ("Giám Đốc Kinh Doanh", "sales"),
    ("Giám Sát Kinh Doanh Hải Phòng - Đi làm ngay", "sales"),
    ("Sales Supervisor/ Business Development - HORECA/ On Premise", "sales"),
    ("Nhân viên Vận Hành máy", "operations"),
])
def test_obvious_non_data_titles_are_settled_without_an_llm(title, expected_rule):
    not_data, rule = prefilter.classify(title)
    assert not_data is True
    assert rule == expected_rule


def test_the_sales_ad_that_advertises_a_lead_list_as_data():
    """The exact shape that made this tier necessary — 'data' here is the lead list."""
    title = ("Chuyên Viên Tư Vấn Tuyển Sinh /Bán Hàng/Kinh Doanh/Sales/Consultant "
             "(Data Sẵn, Thử Việc 100%)")
    not_data, rule = prefilter.classify(title)
    assert (not_data, rule) == (True, "sales")


# --- never fires on anything naming a Data role -----------------------------------

@pytest.mark.parametrize("title", [
    "Data Engineer",
    "Senior Data Analyst",
    "Kỹ Sư Dữ Liệu",
    "Chuyên Gia Khoa Học Dữ Liệu",
    "Business Intelligence Analyst",
    "Machine Learning Engineer",
    "Chuyên viên phân tích dữ liệu kinh doanh",
    "Analytics Engineer",
])
def test_data_roles_are_never_settled_here(title):
    assert prefilter.classify(title) == (False, None)


@pytest.mark.parametrize("title", [
    # A sales role head, but the title also names a Data role: tier 0 must abstain and let
    # something that reads the description decide.
    "Sales Operations Data Analyst",
    "Nhân viên kinh doanh kiêm phân tích dữ liệu",
    "Chuyên viên tư vấn giải pháp Business Intelligence",
    # Risk/fraud and IT audit read as finance-adjacent but are inside the taxonomy.
    "Chuyên gia Kiểm toán Công nghệ thông tin",
    "Chuyên Viên Cao Cấp Quản Lý Rủi Ro",
])
def test_a_data_role_in_the_title_vetoes_every_rule(title):
    assert prefilter.classify(title) == (False, None)


# --- abstains rather than guessing ------------------------------------------------

@pytest.mark.parametrize("title", [None, "", "   "])
def test_missing_titles_are_not_an_opinion(title):
    assert prefilter.classify(title) == (False, None)


@pytest.mark.parametrize("title", [
    "Senior Fullstack Engineer",       # measured 95.8% precise as a group — left out on purpose
    "Kế toán tổng hợp",                # measured 96.8% precise as a group — left out on purpose
    "Product Manager",
    "Giáo viên Tiếng Anh",
])
def test_groups_that_did_not_reach_full_precision_are_not_shipped(title):
    """Tier 0 is cheap, not clever. Anything it is unsure about goes downstream."""
    assert prefilter.classify(title) == (False, None)


def test_tier0_only_ever_rules_out_never_in():
    """It can say 'not Data'. It can never assign a family — that needs a reader."""
    not_data, rule = prefilter.classify("Nhân Viên Bán Hàng")
    assert not_data is True
    assert isinstance(rule, str)
    assert prefilter.TIER0_METHOD.startswith("rule:")
    assert 0 < prefilter.TIER0_CONFIDENCE <= 1.0
