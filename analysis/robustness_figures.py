"""Figures that show UNCERTAINTY and ROBUSTNESS, not "which bar is taller".

The five existing figures (`market_insights.py`) all answer "which is bigger". The three hardest claims
in this report are not size claims:

  * family-level shares must NOT be ranked            -> forest plot, overlapping CIs make that visible
  * entry-rate differs by branch                      -> forest plot + omnibus p, the bars overlap
  * sample composition reflects COLLECTION, not market -> small multiples per job board
  * a headline number moved because the RULER moved   -> slope chart across four measurement versions
  * "industry X hires branch Y"                       -> residual heatmap on the collapsed table

Design rules are inherited wholesale from `market_insights.py` (palette, chrome, PNG+HTML export). Two
rules matter most here and are enforced by hand:
  * ONE question per figure.
  * NO interpretive text drawn on the figure. Titles state what is measured; the reading goes in prose.

Run:  python analysis/robustness_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.utils.analysis_base import ANALYSIS_BASE_WHERE          # noqa: E402
import market_insights as mi                                          # noqa: E402

DB = ROOT / "data" / "warehouse.duckdb"

#: Junior+Intern share after each successive change to HOW seniority is measured, on data that never
#: changed. These are historical outputs of superseded pipeline versions and cannot be recomputed from
#: the shipped warehouse — so they are declared here with their provenance, and `fig_measurement_slope`
#: ASSERTS that the final value still matches the live warehouse before drawing anything. If that assert
#: ever fires, the constant is stale and the figure must not be published.
#: Source: docs/INSIGHTS_BRAINSTORM.md A3 · docs/BAT_DAU_PHAN_TICH.md §4.
#: (nhãn trục, mô tả quy tắc, giá trị). Nhãn trục giữ một dòng: nhãn ba dòng đẩy tiêu đề trục xuống
#: đúng dải của dòng nguồn và hai thứ chồng lên nhau. Mô tả quy tắc chuyển lên phụ đề.
SENIORITY_VERSIONS = [
    ("v1", "default: Mid", 5.6),
    ("v2", "bỏ default", 11.7),
    ("v3", "đọc số năm trong JD", 21.9),
    ("v4", "trường số năm = sàn", 20.0),
]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval. Not normal-approximation: at n=18 and k=0 the normal CI has zero width."""
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (100 * max(centre - half, 0.0), 100 * min(centre + half, 1.0))


def _forest(fig, labels, pct, lo, hi, colors, hover) -> None:
    """Dot + CI whisker per row. Whiskers are drawn as shapes so they keep their width on any zoom."""
    for i, (a, b) in enumerate(zip(lo, hi)):
        fig.add_shape(type="line", x0=a, x1=b, y0=i, y1=i,
                      line=dict(color=colors[i], width=2.5), opacity=0.55)
        for x in (a, b):
            fig.add_shape(type="line", x0=x, x1=x, y0=i - 0.17, y1=i + 0.17,
                          line=dict(color=colors[i], width=2), opacity=0.55)
    fig.add_trace(go.Scatter(
        x=pct, y=list(range(len(labels))), mode="markers",
        marker=dict(size=11, color=colors, line=dict(color=mi.SURFACE, width=1.5)),
        customdata=hover, hovertemplate="%{customdata}<extra></extra>"))
    fig.update_yaxes(tickmode="array", tickvals=list(range(len(labels))), ticktext=labels,
                     tickfont=dict(size=11.5, color=mi.INK))


# --- 1. family share with CI — the figure that makes "do not rank" self-evident ----------------------
def fig_family_forest(con, note: str) -> None:
    d = con.execute("SELECT job_family, jf_domain, n FROM gold_market_share ORDER BY n").df()
    total = int(d["n"].sum())
    ci = [wilson(int(n), total) for n in d["n"]]
    pct = [100 * n / total for n in d["n"]]
    colors = [mi.DOMAIN_COLORS.get(x, mi.NEUTRAL) for x in d["jf_domain"]]
    labels = [mi.PRETTY.get(c, c) for c in d["job_family"]]
    fig = go.Figure()
    _forest(fig, labels, pct, [a for a, _ in ci], [b for _, b in ci], colors,
            [f"<b>{l}</b><br>{n} tin · {p:.1f}%<br>KTC 95%: {a:.1f}–{b:.1f}%"
             for l, n, p, (a, b) in zip(labels, d["n"], pct, ci)])
    fig.update_xaxes(range=[0, 26], ticksuffix="%", title_text="Thị phần trong 720 tin (KTC Wilson 95%)")
    fig.update_layout(margin=dict(l=200, r=60, t=105, b=135))
    chips = "  ".join(f"<span style='color:{c}'>■</span> {n}" for n, c in mi.DOMAIN_COLORS.items())
    fig.add_annotation(text=chips, xref="paper", yref="paper", x=0.0, y=-0.135, showarrow=False,
                       xanchor="left", font=dict(size=10.5, color=mi.INK2))
    mi._shell(fig, "Thị phần theo nghề, kèm khoảng tin cậy 95%", note, 760,
              subtitle=f"Chấm = ước lượng điểm · thanh ngang = khoảng tin cậy Wilson 95% · mẫu số {total} tin")
    mi._save(fig, "family_share_forest", 1100, 760)


# --- 2. entry rate with CI + the omnibus test that says not to read the gaps -------------------------
#: Excluded from the omnibus test, and greyed out in the figure, for a reason that is NOT statistical.
#: `Data Leadership` is a management tier: a 0/18 Junior+Intern count there is what the label MEANS, not
#: an entry barrier the market imposes. Leaving it in flips the test (chi2(4)=12.37, p=0.015 with it;
#: chi2(3)=7.61, p=0.055 without) purely on a definitional cell that also breaks the expected-count rule
#: (expected 3.6 < 5). Reporting the significant version would be manufacturing a result out of a
#: tautology, so the exclusion is declared here, drawn on the figure, and stated in the subtitle.
ENTRY_TEST_EXCLUDED = ("Data Leadership",)


def fig_entry_forest(con, note: str) -> None:
    from scipy.stats import chi2_contingency
    d = con.execute(f"""SELECT jf_domain,
                          SUM(CASE WHEN seniority IN ('Junior','Intern') THEN 1 ELSE 0 END) k,
                          COUNT(*) n
                        FROM jobs_silver WHERE {ANALYSIS_BASE_WHERE}
                        GROUP BY 1 ORDER BY n""").df()
    d["in_test"] = ~d.jf_domain.isin(ENTRY_TEST_EXCLUDED)
    tested = d[d.in_test]
    tab = np.array([[int(r.k), int(r.n - r.k)] for r in tested.itertuples()])
    chi2, p, dof, exp = chi2_contingency(tab)
    ci = [wilson(int(r.k), int(r.n)) for r in d.itertuples()]
    pct = [100 * r.k / r.n for r in d.itertuples()]
    colors = [mi.DOMAIN_COLORS.get(r.jf_domain, mi.NEUTRAL) if r.in_test else mi.NEUTRAL
              for r in d.itertuples()]
    labels = [r.jf_domain if r.in_test else f"{r.jf_domain}<br><i>(ngoài kiểm định)</i>"
              for r in d.itertuples()]
    fig = go.Figure()
    _forest(fig, labels, pct, [a for a, _ in ci], [b for _, b in ci], colors,
            [f"<b>{r.jf_domain}</b><br>{int(r.k)}/{int(r.n)} · {100*r.k/r.n:.1f}%<br>"
             f"KTC 95%: {a:.1f}–{b:.1f}%" for r, (a, b) in zip(d.itertuples(), ci)])
    fig.update_xaxes(range=[0, 40], ticksuffix="%",
                     title_text="% tin ở cấp Junior hoặc Intern (KTC Wilson 95%)")
    fig.update_layout(margin=dict(l=245, r=60, t=132, b=125))
    mi._shell(fig, "Tỉ lệ Junior + Intern theo nhánh, kèm khoảng tin cậy 95%", note, 560,
              subtitle=f"Kiểm định χ² đồng thời trên {len(tested)} nhánh: χ²({dof}) = {chi2:.2f}; "
                       f"p = {p:.3f}; Cramér's V = "
                       f"{np.sqrt(chi2/(tab.sum()*(min(tab.shape)-1))):.3f} (kỳ vọng nhỏ nhất {exp.min():.1f})"
                       f"<br>{', '.join(ENTRY_TEST_EXCLUDED)} nằm ngoài kiểm định: đây là cấp quản lý, "
                       f"tỉ lệ Junior bằng 0 là do định nghĩa nhãn, không phải rào cản tuyển dụng")
    mi._save(fig, "entry_rate_forest", 1100, 560)


# --- 3. small multiples per board — sample composition is a collection artefact ----------------------
def fig_board_composition(con, note: str) -> None:
    from plotly.subplots import make_subplots
    d = con.execute(f"""SELECT source, jf_domain, COUNT(*) n FROM jobs_silver
                        WHERE {ANALYSIS_BASE_WHERE} GROUP BY 1,2""").df()
    piv = d.pivot_table(index="source", columns="jf_domain", values="n", fill_value=0)
    share = piv.div(piv.sum(axis=1), axis=0) * 100
    pooled = piv.sum(axis=0) / piv.values.sum() * 100
    doms = list(mi.DOMAIN_COLORS)
    doms = [x for x in doms if x in share.columns]
    boards = list(share.sum(axis=1).index)
    boards = list(piv.sum(axis=1).sort_values(ascending=False).index)

    fig = make_subplots(rows=1, cols=len(boards), shared_yaxes=True, horizontal_spacing=0.012,
                        subplot_titles=[f"{b}<br><span style='font-size:10px'>n = {int(piv.loc[b].sum())}</span>"
                                        for b in boards])
    for j, b in enumerate(boards, start=1):
        fig.add_trace(go.Bar(x=[share.loc[b, x] for x in doms], y=doms, orientation="h",
                             marker=dict(color=[mi.DOMAIN_COLORS[x] for x in doms]),
                             hovertemplate=f"<b>{b}</b><br>%{{y}}: %{{x:.1f}}%<extra></extra>"),
                      row=1, col=j)
        # Pooled share as a reference tick per category, so "this board vs all boards" is one glance.
        for x in doms:
            fig.add_shape(type="line", x0=pooled[x], x1=pooled[x],
                          y0=doms.index(x) - 0.42, y1=doms.index(x) + 0.42,
                          line=dict(color=mi.INK, width=1.6, dash="dot"), row=1, col=j)
        fig.update_xaxes(range=[0, 70], ticksuffix="%", dtick=30, row=1, col=j)
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=11, color=mi.INK))
    fig.update_layout(margin=dict(l=205, r=40, t=170, b=125), bargap=0.35)
    # Only the per-board subplot titles exist at this point (`_shell` adds subtitle + source afterwards).
    # They are nudged up out of the subtitle's band, which they collided with on the first render.
    for a in fig.layout.annotations:
        a.font = dict(size=11.5, color=mi.INK2)
        a.yshift = 22
    mi._shell(fig, "Cơ cấu nhánh nghề, tách riêng theo từng job board", note, 560,
              subtitle="Vạch chấm đứng = tỉ lệ khi gộp cả 6 board · mỗi khung dùng chung một trục 0–70%")
    mi._save(fig, "board_composition", 1350, 560)


# --- 4. the ruler moved, not the market -------------------------------------------------------------
def fig_measurement_slope(con, note: str) -> None:
    live = con.execute(f"""SELECT 100.0 * SUM(CASE WHEN seniority IN ('Junior','Intern') THEN 1 ELSE 0 END)
                                  / COUNT(*) FROM jobs_silver WHERE {ANALYSIS_BASE_WHERE}""").fetchone()[0]
    last = SENIORITY_VERSIONS[-1][2]
    assert abs(live - last) < 0.15, (
        f"SENIORITY_VERSIONS is stale: constant says {last}%, warehouse now says {live:.1f}%. "
        "Update the constant (and its provenance) before publishing this figure.")
    labels = [v[0] for v in SENIORITY_VERSIONS]
    vals = [v[2] for v in SENIORITY_VERSIONS]
    rules = " · ".join(f"<b>{k}</b> {desc}" for k, desc, _ in SENIORITY_VERSIONS)
    fig = go.Figure(go.Scatter(
        x=labels, y=vals, mode="lines+markers+text",
        line=dict(color=mi.S1, width=3), marker=dict(size=13, color=mi.S1,
                                                     line=dict(color=mi.SURFACE, width=2)),
        text=[f"<b>{v:.1f}%</b>" for v in vals], textposition="top center",
        textfont=dict(size=13, color=mi.INK),
        hovertemplate="%{x}<br>Junior+Intern: %{y:.1f}%<extra></extra>"))
    fig.update_yaxes(range=[0, 27], ticksuffix="%", title_text="% tin ở cấp Junior hoặc Intern")
    fig.update_xaxes(title_text="Phiên bản của CÁCH ĐO cấp bậc", title_standoff=10)
    fig.update_layout(margin=dict(l=95, r=60, t=132, b=125))
    mi._shell(fig, "Tỉ lệ Junior + Intern qua bốn phiên bản của cách đo", note, 560,
              subtitle="Dữ liệu gốc không đổi một dòng giữa bốn phiên bản; chỉ quy tắc suy ra cấp bậc "
                       f"thay đổi<br>{rules}")
    mi._save(fig, "seniority_measurement_slope", 1050, 560)


# --- 5. industry x domain, as residuals rather than raw counts ---------------------------------------
def fig_industry_residuals(con, note: str) -> None:
    from scipy.stats import chi2_contingency
    d = con.execute(f"SELECT company_type, jf_domain FROM jobs_silver WHERE {ANALYSIS_BASE_WHERE}").df()
    #: Industries under this many postings are pooled. The ungrouped 15x5 table puts 57% of cells below
    #: expected 5 (min 0.03) — chi-square is not defined on that, and the residuals it produces are noise.
    MIN_INDUSTRY_N = 30
    sizes = d.company_type.value_counts()
    small = set(sizes[sizes < MIN_INDUSTRY_N].index)
    d["ind"] = d.company_type.where(~d.company_type.isin(small), "other_industry")
    t = pd.crosstab(d.ind, d.jf_domain)
    chi2, p, dof, exp = chi2_contingency(t)
    n = t.values.sum()
    rs, cs = t.values.sum(1, keepdims=True), t.values.sum(0, keepdims=True)
    adj = (t.values - exp) / np.sqrt(exp * (1 - rs / n) * (1 - cs / n))
    # Bonferroni-corrected two-sided cut for a standard normal over every cell tested.
    from scipy.stats import norm
    crit = float(norm.ppf(1 - 0.05 / (2 * adj.size)))

    rows = [mi.INDUSTRY_VI.get(x, "Ngành khác (gộp)") if x != "other_industry" else "Ngành khác (gộp)"
            for x in t.index]
    fig = go.Figure(go.Heatmap(
        z=adj, x=list(t.columns), y=rows, zmid=0, zmin=-4.5, zmax=4.5, xgap=2, ygap=2,
        colorscale=[[0.0, "#8c3a10"], [0.25, "#eb6834"], [0.5, "#f4f3ee"],
                    [0.75, "#2a78d6"], [1.0, "#12386b"]],
        colorbar=dict(title=dict(text="phần dư<br>chuẩn hoá", font=dict(size=10.5, color=mi.INK2)),
                      thickness=12, len=0.7, tickfont=dict(size=10, color=mi.INK2), outlinewidth=0),
        hovertemplate="<b>%{y}</b><br>%{x}<br>phần dư điều chỉnh: %{z:.2f}<extra></extra>"))
    for iy in range(adj.shape[0]):
        for ix in range(adj.shape[1]):
            v = adj[iy][ix]
            mark = "*" if abs(v) > crit else ""
            # Label colour flips with the FILL's lightness, not with significance. The diverging ramp is
            # already saturated by |z| ~ 2.4, so dark ink stopped being readable well before the cutoff.
            fig.add_annotation(x=list(t.columns)[ix], y=rows[iy], text=f"{v:.1f}{mark}", showarrow=False,
                               font=dict(size=11, color="#f7f5f0" if abs(v) >= 2.4 else mi.INK2))
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=11.5, color=mi.INK))
    fig.update_xaxes(side="bottom", tickangle=0, tickfont=dict(size=10.5, color=mi.INK2))
    fig.update_layout(margin=dict(l=230, r=120, t=125, b=130))
    mi._shell(fig, "Ngành của nhà tuyển dụng × nhánh nghề — phần dư so với kỳ vọng", note, 560,
              subtitle=f"χ²({dof}) = {chi2:.1f}; p = {p:.2g}; Cramér's V = "
                       f"{np.sqrt(chi2/(n*(min(t.shape)-1))):.3f} · * = |z| > {crit:.2f} (Bonferroni "
                       f"cho {adj.size} ô) · ngành < {MIN_INDUSTRY_N} tin đã gộp")
    mi._save(fig, "industry_domain_residuals", 1150, 560)


def main() -> None:
    con = duckdb.connect(str(DB), read_only=True)
    note = mi._source(con)
    print("Rendering figures → analysis/figures/")
    fig_family_forest(con, note)
    fig_entry_forest(con, note)
    fig_board_composition(con, note)
    fig_measurement_slope(con, note)
    fig_industry_residuals(con, note)
    con.close()
    print("Done.")


if __name__ == "__main__":
    main()
