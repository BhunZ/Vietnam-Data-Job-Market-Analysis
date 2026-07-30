"""Report-grade market-insight figures for the VN Data job market (Plotly).

Reads the shipped DuckDB warehouse (`gold_*`, built by the Job Family Engine) and renders each figure as
PNG + interactive HTML into `analysis/figures/`.

Design rules applied (see the repo's chart notes in docs/INSIGHT_FRAMEWORK.md):
  * ONE message per figure. The previous version crammed KPI cards and a 20-row bar chart into one
    subplot grid, so labels collided and nothing was legible.
  * Horizontal bars whenever category names are long — vertical bars force rotated, overlapping ticks.
  * Every bar carries a DIRECT value label; three palette slots sit below 3:1 contrast on the light
    surface, and a visible label is the required relief.
  * Colours come from a validated categorical palette (adjacent-pair CVD ΔE >= 8, normal-vision >= 15).
    Colour follows the ENTITY (a domain keeps its hue in every figure), never rank.
  * `unknown` buckets are drawn in muted grey and never highlighted: they are missing data, not a finding.
  * No dual axes anywhere; counts and percentages never share a scale.

Run:  python analysis/market_insights.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))                     # so `analysis/x.py` runs standalone, not just -m

from pipeline.utils.analysis_base import ANALYSIS_BASE_WHERE   # noqa: E402

DB = ROOT / "data" / "warehouse.duckdb"
OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# --- validated palette (light surface #fcfcfb) --------------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
S1, S2, S3, S4, S5 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
NEUTRAL = "#c3c2b7"          # for "unknown"/unclassified — never a highlight colour
FONT = "Segoe UI, system-ui, sans-serif"

# Domain keeps ONE hue across every figure (colour follows the entity).
DOMAIN_COLORS = {
    "Analytics": S1,
    "AI / Machine Learning": S2,
    "Data Engineering": S3,
    "Governance & Architecture": S4,
    "Data Leadership": S5,
}
PRETTY = {
    "BUSINESS_ANALYST": "Business Analyst", "DATA_ENGINEER": "Data Engineer",
    "DATA_ANALYST": "Data Analyst", "AI_ENGINEER": "AI Engineer",
    "RISK_FRAUD_ANALYST": "Risk / Fraud Analyst", "BI": "BI Analyst",
    "DATA_SCIENTIST": "Data Scientist", "DATA_GOVERNANCE": "Data Governance",
    "PRODUCT_ANALYST": "Product Analyst", "DATA_LEADERSHIP": "Data Leadership",
    "DBA_DATABASE": "DBA / Database", "CV_NLP": "Computer Vision / NLP",
    "DATA_ARCHITECT": "Data Architect", "ML_ENGINEER": "ML Engineer",
    "GENAI_LLM": "GenAI / LLM", "ANALYTICS_ENGINEER": "Analytics Engineer",
    "RESEARCH_SCIENTIST": "Research Scientist", "DATAOPS": "DataOps",
    "MLOPS": "MLOps", "BIG_DATA_ENGINEER": "Big Data Engineer",
}
INDUSTRY_VI = {
    "bank_finance": "Ngân hàng / Tài chính", "tech_software": "Công nghệ / Phần mềm",
    "telecom": "Viễn thông", "manufacturing": "Sản xuất", "retail_consumer": "Bán lẻ / Tiêu dùng",
    "consulting_audit": "Tư vấn / Kiểm toán", "logistics": "Logistics", "ecommerce": "Thương mại điện tử",
    "media_gaming": "Truyền thông / Game", "education": "Giáo dục",
    "healthcare_pharma": "Y tế / Dược", "real_estate_construction": "BĐS / Xây dựng",
    "energy_agri": "Năng lượng / Nông nghiệp", "public_sector": "Khu vực công",
    "recruitment_agency": "Công ty tuyển dụng (ẩn NTD thật)", "unknown": "Chưa phân loại được",
}
SEN_VI = {"Intern": "Intern", "Junior": "Junior", "Mid": "Mid", "Senior": "Senior",
          "Lead": "Lead", "Manager": "Manager", "Unknown": "Không xác định"}


def _shell(fig, title, note, h, subtitle=None):
    """Common chrome: recessive grid/axes, ink-token text, one short source line.

    Titles are DESCRIPTIVE, never editorial: the chart states what is measured and the reader draws the
    conclusion. Interpretation ("cửa vào nghề rất hẹp", "chỉ 1/9 thị trường") belongs in the report prose
    beside the figure, not stamped on every chart — repeated on five figures it became noise and competed
    with the data for attention. `subtitle` exists only for a caveat the numbers cannot carry themselves.
    """
    fig.update_layout(
        template="plotly_white", font=dict(family=FONT, size=13, color=INK),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        height=h, showlegend=False,
        title=dict(text=f"<b>{title}</b>", x=0.01, y=0.97, xanchor="left",
                   font=dict(size=20, color=INK)),
    )
    # Anchor the subtitle to its BOTTOM edge so extra lines grow upward into the margin instead of down
    # into the plot (a 2-line subtitle anchored at its middle overlapped the first bar), and anchor the
    # source note to its TOP edge so it grows downward, away from the x-axis title.
    if subtitle:
        fig.add_annotation(text=subtitle, xref="paper", yref="paper", x=0.01, y=1.02,
                           showarrow=False, xanchor="left", yanchor="bottom", align="left",
                           font=dict(size=12, color=INK2))
    fig.add_annotation(text=note, xref="paper", yref="paper", x=0.01, y=-0.20,
                       showarrow=False, xanchor="left", yanchor="top", align="left",
                       font=dict(size=10, color=MUTED))
    fig.update_xaxes(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS,
                     tickfont=dict(size=11, color=INK2))
    fig.update_yaxes(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS,
                     tickfont=dict(size=11, color=INK2))
    return fig


def _save(fig, name, w, h):
    fig.write_image(str(OUT / f"{name}.png"), width=w, height=h, scale=2)
    fig.write_html(str(OUT / f"{name}.html"), include_plotlyjs="cdn", full_html=True)
    print(f"  -> figures/{name}.png + .html")


def _source(con) -> str:
    """Provenance note stamped on every figure.

    It used to read "≥2 LLM judge đồng thuận", which was true of a minority of the rows: the cascade
    settles most postings at the title-rule tier and those never reach a judge. The mix is read from the
    data instead of asserted, so the note cannot drift away from what actually produced the labels.
    """
    n = con.execute("SELECT SUM(n) FROM gold_market_share").fetchone()[0]
    mix = con.execute(f"""SELECT
            SUM(CASE WHEN jf_method = 'rule' THEN 1 ELSE 0 END),
            SUM(CASE WHEN jf_method LIKE 'vote%' THEN 1 ELSE 0 END),
            SUM(CASE WHEN jf_method LIKE 'refine%' THEN 1 ELSE 0 END)
        FROM jobs_silver WHERE {ANALYSIS_BASE_WHERE}""").fetchone()
    rule, vote, refine = (int(x or 0) for x in mix)
    tot = max(rule + vote + refine, 1)
    return (f"Nguồn: {int(n)} tin Data/AI (6 job board VN, 1 snapshot 06/2026) · nhãn nghề: "
            f"rule tiêu đề {100*rule/tot:.0f}% · LLM đồng thuận {100*(vote+refine)/tot:.0f}% · "
            f"1 snapshot ⇒ không suy ra xu hướng")


# --- 1. Domain share — the headline, and the only level a ranking survives at --
def fig_domain(con):
    d = con.execute("SELECT jf_domain, n, pct FROM gold_domain_share ORDER BY n").df()
    labels = list(d["jf_domain"])
    fig = go.Figure(go.Bar(
        y=labels, x=d["pct"], orientation="h",
        marker=dict(color=[DOMAIN_COLORS.get(x, NEUTRAL) for x in labels],
                    line=dict(color=SURFACE, width=2)),   # 2px surface gap between adjacent fills
        text=[f"<b>{p:.1f}%</b>  ({int(n)} tin)" for p, n in zip(d["pct"], d["n"])],
        textposition="outside", textfont=dict(size=12.5, color=INK), cliponaxis=False,
        hovertemplate="%{y}<br>%{x:.1f}% · %{customdata} tin<extra></extra>", customdata=d["n"],
    ))
    fig.update_xaxes(range=[0, 60], ticksuffix="%")
    fig.update_layout(margin=dict(l=200, r=110, t=95, b=105))
    _shell(fig, "Thị phần tuyển dụng Data theo nhánh (domain)", _source(con), 460)
    _save(fig, "domain_share", 1100, 460)


# --- 2. Family detail — explicitly NOT a ranking ------------------------------
def fig_family(con):
    d = con.execute("SELECT job_family, jf_domain, n, pct FROM gold_market_share "
                    "ORDER BY n").df()
    labels = [PRETTY.get(c, c) for c in d["job_family"]]
    fig = go.Figure(go.Bar(
        y=labels, x=d["pct"], orientation="h",
        marker=dict(color=[DOMAIN_COLORS.get(x, NEUTRAL) for x in d["jf_domain"]],
                    line=dict(color=SURFACE, width=1.5)),
        text=[f"{p:.1f}%" for p in d["pct"]], textposition="outside",
        textfont=dict(size=11, color=INK2), cliponaxis=False,
        hovertemplate="%{y}<br>%{x:.1f}% · %{customdata} tin<extra></extra>", customdata=d["n"],
    ))
    fig.update_xaxes(range=[0, 24], ticksuffix="%")
    fig.update_layout(margin=dict(l=195, r=80, t=95, b=125))
    # Legend: colour = domain, so identity is never carried by colour alone in the caption either.
    chips = "  ".join(f"<span style='color:{c}'>■</span> {n}" for n, c in DOMAIN_COLORS.items())
    fig.add_annotation(text=chips, xref="paper", yref="paper", x=0.01, y=-0.075,
                       showarrow=False, xanchor="left", font=dict(size=10.5, color=INK2))
    _shell(fig, "Thị phần tuyển dụng theo 20 nhánh nghề (job family)", _source(con), 720)
    _save(fig, "family_share", 1100, 720)


# --- 3. Skill fingerprint: what a family asks for vs what makes it distinctive -
def fig_skill_dna(con):
    fams = con.execute("SELECT job_family FROM gold_market_share ORDER BY n DESC LIMIT 8"
                       ).df()["job_family"].tolist()
    skills = con.execute("SELECT skill, SUM(n) t FROM gold_family_skill GROUP BY 1 "
                         "ORDER BY 2 DESC LIMIT 11").df()["skill"].tolist()
    fs = con.execute("SELECT job_family, skill, share_in_family FROM gold_family_skill").df()
    piv = (fs[fs["job_family"].isin(fams) & fs["skill"].isin(skills)]
           .pivot_table(index="job_family", columns="skill", values="share_in_family", fill_value=0)
           .reindex(index=fams, columns=skills))
    z = piv.values
    fig = go.Figure(go.Heatmap(
        z=z, x=skills, y=[PRETTY.get(c, c) for c in piv.index],
        # Sequential = ONE hue, light->dark. The old version used a rainbow-ish scale.
        colorscale=[[0.0, "#f2f7fd"], [0.25, "#9ec5f4"], [0.5, "#5598e7"],
                    [0.75, "#256abf"], [1.0, "#0d366b"]],
        zmin=0, zmax=85, xgap=2, ygap=2,      # 2px surface gap between cells
        colorbar=dict(title=dict(text="% tin trong<br>nhánh", font=dict(size=10.5, color=INK2)),
                      thickness=12, len=0.62, tickfont=dict(size=10, color=INK2), outlinewidth=0),
        hovertemplate="<b>%{y}</b><br>%{x}: %{z:.0f}% số tin trong nhánh<extra></extra>",
    ))
    # Per-cell value labels drawn as annotations, because a heatmap's `textfont` takes ONE colour for the
    # whole grid: dark ink on the dark high-value cells was unreadable (77, 81, 89 all disappeared).
    # Text on a coloured fill must flip with the fill's lightness.
    for iy, fam in enumerate(piv.index):
        for ix, sk in enumerate(piv.columns):
            v = z[iy][ix]
            if v < 5:
                continue
            fig.add_annotation(
                x=sk, y=PRETTY.get(fam, fam), text=f"{v:.0f}", showarrow=False,
                font=dict(size=10.5, color="#eaf2fd" if v >= 45 else INK2),
            )
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=11.5, color=INK))
    # Horizontal tick labels at the BOTTOM: rotated top labels were the main collision source.
    fig.update_xaxes(side="bottom", tickangle=0, tickfont=dict(size=10.5, color=INK2))
    fig.update_layout(margin=dict(l=180, r=115, t=95, b=105))
    _shell(fig, "% tin trong mỗi nhánh có yêu cầu kỹ năng", _source(con), 580)
    _save(fig, "skill_dna", 1150, 580)


# --- 4. Who hires — industry, with `unknown` shown honestly -------------------
def fig_industry(con):
    d = con.execute("SELECT company_type, SUM(n) n FROM gold_company GROUP BY 1 "
                    "ORDER BY n").df()
    d = d[d["n"] >= 3]
    labels = [INDUSTRY_VI.get(t, t) for t in d["company_type"]]
    total = con.execute("SELECT SUM(n) FROM gold_market_share").fetchone()[0]
    colors = []
    for t in d["company_type"]:
        colors.append(NEUTRAL if t in ("unknown", "recruitment_agency")
                      else S1 if t == "bank_finance" else S3 if t == "tech_software" else "#9ec5f4")
    fig = go.Figure(go.Bar(
        y=labels, x=d["n"], orientation="h",
        marker=dict(color=colors, line=dict(color=SURFACE, width=2)),
        text=[f"<b>{int(n)}</b>  ({100*n/total:.1f}%)" for n in d["n"]],
        textposition="outside", textfont=dict(size=11.5, color=INK), cliponaxis=False,
        hovertemplate="%{y}: %{x} tin<extra></extra>",
    ))
    fig.update_xaxes(range=[0, max(d["n"]) * 1.28])
    fig.update_layout(margin=dict(l=255, r=95, t=95, b=115))
    _shell(fig, "Số tin tuyển dụng Data theo ngành của nhà tuyển dụng", _source(con), 600)
    _save(fig, "industry_share", 1100, 600)


# --- 5. Seniority — with the honest Unknown bucket ---------------------------
def fig_seniority(con):
    d = con.execute("SELECT seniority, SUM(n) n FROM gold_seniority GROUP BY 1").df()
    order = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager", "Unknown"]
    d = d.set_index("seniority").reindex(order).dropna().reset_index()
    total = d["n"].sum()
    colors = [NEUTRAL if s == "Unknown" else S1 for s in d["seniority"]]
    fig = go.Figure(go.Bar(
        x=[SEN_VI.get(s, s) for s in d["seniority"]], y=d["n"],
        marker=dict(color=colors, line=dict(color=SURFACE, width=2)),
        text=[f"<b>{int(n)}</b><br>{100*n/total:.1f}%" for n in d["n"]],
        textposition="outside", textfont=dict(size=11.5, color=INK), cliponaxis=False,
        hovertemplate="%{x}: %{y} tin<extra></extra>",
    ))
    fig.update_yaxes(range=[0, max(d["n"]) * 1.30])
    fig.update_layout(margin=dict(l=85, r=55, t=95, b=120))
    _shell(fig, "Số tin tuyển dụng Data theo cấp bậc", _source(con), 500)
    _save(fig, "seniority_share", 1000, 500)


def main():
    con = duckdb.connect(str(DB), read_only=True)
    print("Rendering figures → analysis/figures/")
    fig_domain(con)
    fig_family(con)
    fig_skill_dna(con)
    fig_industry(con)
    fig_seniority(con)
    con.close()
    print("Done.")


if __name__ == "__main__":
    main()
