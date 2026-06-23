"""Business-style market-insight figures for the VN Data job market (Plotly).

Reads the shipped DuckDB warehouse (gold_* tables built by the Job Family Engine) and renders three
report-grade figures (PNG + interactive HTML) into analysis/figures/:

  1. market_overview   — KPI cards + market share by job family (the hero figure)
  2. skill_dna         — heatmap of skill share within each family ("skill fingerprint" per role)
  3. employers_seniority — who hires (company type) + at what level (seniority structure)

Run:  python analysis/market_insights.py
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse.duckdb"
OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# --- professional, muted palette (navy / teal / coral) -----------------------
INK = "#22303C"
MUTED = "#6B7280"
GRID = "#E6EBF0"
ACCENT = "#E8743B"          # coral highlight
DOMAIN_COLORS = {
    "Analytics": "#2C7FB8",
    "Data Engineering": "#3B5A78",
    "AI / Machine Learning": "#E8743B",
    "Governance & Architecture": "#7E5A9B",
    "Data Leadership": "#9AA6B2",
}
FONT = "Arial"
PRETTY = {  # code → readable label
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
COMPANY_VI = {"bank_fintech": "Ngân hàng / Fintech", "outsourcing": "Outsourcing / Dịch vụ",
              "ecommerce": "Thương mại điện tử", "product": "Product / Công nghệ",
              "other": "Khác / Chưa phân loại"}


def _base_layout(fig, title, subtitle, h):
    fig.update_layout(
        template="plotly_white", font=dict(family=FONT, size=13, color=INK),
        paper_bgcolor="white", plot_bgcolor="white",
        height=h, margin=dict(l=70, r=40, t=110, b=64),
        showlegend=False,
        title=dict(text=f"<b>{title}</b>", x=0.012, y=0.965, xanchor="left",
                   font=dict(size=21, color=INK)),
    )
    fig.add_annotation(text=subtitle, xref="paper", yref="paper", x=0.012, y=1.045,
                       showarrow=False, xanchor="left", font=dict(size=13, color=MUTED))
    fig.add_annotation(text="Nguồn: 852 tin tuyển dụng Data/AI (6 job board VN, 1 snapshot) · "
                            "nhãn nghề bởi Job Family Labeling Engine",
                       xref="paper", yref="paper", x=0.012, y=-0.13, showarrow=False,
                       xanchor="left", font=dict(size=10.5, color=MUTED))
    return fig


def _save(fig, name, w, h):
    fig.write_image(str(OUT / f"{name}.png"), width=w, height=h, scale=2)
    fig.write_html(str(OUT / f"{name}.html"), include_plotlyjs="cdn", full_html=True)
    print(f"  -> figures/{name}.png + .html")


# --- 1. Market overview (KPI cards + market share) ---------------------------
def fig_overview(con):
    df = con.execute("SELECT job_family, jf_domain, n, pct FROM gold_market_share "
                     "ORDER BY n DESC").df()
    total = int(df["n"].sum())
    top4 = round(df.head(4)["pct"].sum(), 1)
    lead, lead_pct = PRETTY[df.iloc[0]["job_family"]], df.iloc[0]["pct"]

    fig = make_subplots(
        rows=2, cols=4, row_heights=[0.2, 0.8], vertical_spacing=0.14,
        specs=[[{"type": "indicator"}] * 4, [{"type": "xy", "colspan": 4}, None, None, None]],
    )
    kpis = [(f"{total}", "Vị trí Data/AI"), (f"{lead_pct:.1f}%", f"Dẫn đầu: {lead}"),
            (f"{top4:.0f}%", "Top-4 nhánh chiếm"), ("20", "Nhánh nghề")]
    for i, (val, lab) in enumerate(kpis, 1):
        fig.add_trace(go.Indicator(
            mode="number", value=0,
            number=dict(font=dict(size=1)),  # placeholder; real text via annotation below
        ), row=1, col=i)
    # KPI cards drawn as annotations for full styling control
    for i, (val, lab) in enumerate(kpis):
        x = 0.04 + i * 0.255
        fig.add_annotation(text=f"<b>{val}</b>", xref="paper", yref="paper", x=x, y=0.99,
                           showarrow=False, xanchor="left",
                           font=dict(size=30, color=ACCENT if i in (1, 2) else INK))
        fig.add_annotation(text=lab, xref="paper", yref="paper", x=x, y=0.875, showarrow=False,
                           xanchor="left", font=dict(size=12, color=MUTED))

    d = df.sort_values("n")  # ascending → largest on top in horizontal bar
    labels = [PRETTY.get(c, c) for c in d["job_family"]]
    colors = [DOMAIN_COLORS.get(dm, MUTED) for dm in d["jf_domain"]]
    fig.add_trace(go.Bar(
        y=labels, x=d["pct"], orientation="h", marker=dict(color=colors),
        text=[f"{p:.1f}%" for p in d["pct"]], textposition="outside",
        textfont=dict(size=11, color=INK),
        customdata=d["n"], hovertemplate="%{y}: %{x:.1f}% (%{customdata} tin)<extra></extra>",
    ), row=2, col=1)
    fig.update_xaxes(title_text="Thị phần (% trên 852 tin Data/AI)", range=[0, 24],
                     gridcolor=GRID, row=2, col=1)
    fig.update_yaxes(tickfont=dict(size=11.5), row=2, col=1)
    # domain legend (manual chips)
    for j, (dm, c) in enumerate(DOMAIN_COLORS.items()):
        fig.add_annotation(text=f"<span style='color:{c}'>■</span> {dm}", xref="paper", yref="paper",
                           x=0.40 + (j % 3) * 0.20, y=0.40 - (j // 3) * 0.05, showarrow=False,
                           xanchor="left", font=dict(size=10.5, color=MUTED))

    _base_layout(fig, "Toàn cảnh thị trường nhân lực Data Việt Nam",
                 "4 nhánh dẫn đầu (Business Analyst · Data Engineer · Data Analyst · AI Engineer) "
                 "chiếm 2/3 thị trường", 720)
    _save(fig, "market_overview", 1180, 720)


# --- 2. Skill DNA heatmap ----------------------------------------------------
def fig_skill_dna(con):
    fams = con.execute("SELECT job_family FROM gold_market_share ORDER BY n DESC LIMIT 9").df()["job_family"].tolist()
    skills = con.execute("SELECT skill, SUM(n) t FROM gold_family_skill GROUP BY 1 "
                         "ORDER BY 2 DESC LIMIT 12").df()["skill"].tolist()
    fs = con.execute("SELECT job_family, skill, share_in_family FROM gold_family_skill").df()
    piv = (fs[fs["job_family"].isin(fams) & fs["skill"].isin(skills)]
           .pivot_table(index="job_family", columns="skill", values="share_in_family", fill_value=0)
           .reindex(index=fams, columns=skills))
    z = piv.values
    yl = [PRETTY.get(c, c) for c in piv.index]

    fig = go.Figure(go.Heatmap(
        z=z, x=skills, y=yl, colorscale="Teal", zmin=0, zmax=80,
        text=[[f"{v:.0f}" if v >= 8 else "" for v in row] for row in z],
        texttemplate="%{text}", textfont=dict(size=10, color="white"),
        colorbar=dict(title="% trong<br>nhánh", thickness=14, len=0.7),
        hovertemplate="%{y} · %{x}: %{z:.0f}% số tin trong nhánh<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=11.5))
    fig.update_xaxes(side="top", tickangle=-35, tickfont=dict(size=11))
    _base_layout(fig, "Bản đồ kỹ năng theo nhánh nghề (Skill DNA)",
                 "Mỗi ô = % số tin trong nhánh có yêu cầu kỹ năng đó → “dấu vân tay” kỹ năng của từng nghề", 620)
    fig.update_layout(margin=dict(l=150, r=40, t=185, b=64))
    _save(fig, "skill_dna", 1180, 660)


# --- 3. Employers + seniority ------------------------------------------------
def fig_employers_seniority(con):
    comp = con.execute("SELECT company_type, SUM(n) n FROM gold_company GROUP BY 1 "
                       "ORDER BY 2 DESC").df()
    sen = con.execute("SELECT seniority, SUM(n) n FROM gold_seniority GROUP BY 1 ORDER BY 2 DESC").df()
    order = ["Intern", "Junior", "Mid", "Senior", "Lead", "Manager"]
    sen = sen.set_index("seniority").reindex(order).dropna().reset_index()

    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.18)
    cc = comp.sort_values("n")
    comp_colors = [ACCENT if t == "bank_fintech" else "#9AA6B2" for t in cc["company_type"]]
    fig.add_trace(go.Bar(
        y=[COMPANY_VI.get(t, t) for t in cc["company_type"]], x=cc["n"], orientation="h",
        marker_color=comp_colors, text=cc["n"], textposition="outside",
        hovertemplate="%{y}: %{x} tin<extra></extra>"), row=1, col=1)

    sen_colors = [ACCENT if s == "Mid" else "#3B5A78" for s in sen["seniority"]]
    fig.add_trace(go.Bar(
        x=sen["seniority"], y=sen["n"], marker_color=sen_colors,
        text=sen["n"], textposition="outside",
        hovertemplate="%{x}: %{y} tin<extra></extra>"), row=1, col=2)

    fig.update_xaxes(gridcolor=GRID, row=1, col=1)
    fig.update_yaxes(tickfont=dict(size=11.5), row=1, col=1)
    fig.update_yaxes(gridcolor=GRID, title_text="Số tin", row=1, col=2)
    _base_layout(fig, "Cầu lao động: nhà tuyển dụng & cấp bậc",
                 "Ngân hàng/Fintech là khối tuyển nhiều nhất (có thể nhận dạng); thị trường lệch hẳn về "
                 "Mid-level, rất ít Junior/Intern", 560)
    fig.update_layout(margin=dict(l=70, r=40, t=130, b=64))
    fig.add_annotation(text="<b>Ai đang tuyển?</b> (theo loại công ty)", xref="paper", yref="paper",
                       x=0.0, y=0.90, showarrow=False, xanchor="left", font=dict(size=13, color=INK))
    fig.add_annotation(text="<b>Tuyển cấp nào?</b> (theo seniority)", xref="paper", yref="paper",
                       x=0.62, y=0.90, showarrow=False, xanchor="left", font=dict(size=13, color=INK))
    _save(fig, "employers_seniority", 1180, 560)


def main():
    con = duckdb.connect(str(DB), read_only=True)
    print("Rendering figures → analysis/figures/")
    fig_overview(con)
    fig_skill_dna(con)
    fig_employers_seniority(con)
    con.close()
    print("Done.")


if __name__ == "__main__":
    main()
