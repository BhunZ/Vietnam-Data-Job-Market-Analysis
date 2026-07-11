"""Topic modeling over job-description text for VN Data/AI postings.

Business question:
    Beyond normalized skill tags, what hidden technology, task, or requirement
    themes appear in Data/AI job descriptions in Vietnam?

Reads `jobs_silver` joined with raw `jobs.description_raw`, keeps the official
analysis population, builds TF-IDF features over title + skills + JD text, fits
NMF for several topic counts, and writes analysis-ready CSV/Markdown artifacts.

Run:
    python analysis/topic_modeling.py
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse.duckdb"
OUT = Path(__file__).resolve().parent / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

SEED = 42
WS = re.compile(r"\s+")
BOILERPLATE = re.compile(
    r"(benefits?|why you'?ll love|about us|company overview|equal opportunity|how to apply|"
    r"quyen loi|phuc loi|che do|ve chung toi|cach thuc ung tuyen|nop ho so)",
    re.I,
)


def _parse_skills(raw: object) -> list[str]:
    if not isinstance(raw, str):
        return []
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(values, list):
        return []
    return sorted({s.strip() for s in values if isinstance(s, str) and s.strip()})


def _ascii_fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _role_view(title: str | None, jd: str | None, skills: list[str]) -> str:
    jd = jd or ""
    jd = _ascii_fold(jd)
    title = _ascii_fold(title or "")
    kept = [line for line in jd.splitlines() if line.strip() and not BOILERPLATE.search(_ascii_fold(line))]
    jd_clean = WS.sub(" ", " ".join(kept)).strip()
    parts = [
        title.strip(),
        ("Skills: " + ", ".join(skills)) if skills else "",
        jd_clean[:5000],
    ]
    return WS.sub(" ", " \n".join(part for part in parts if part)).strip()


def load_jobs() -> pd.DataFrame:
    con = duckdb.connect(str(DB), read_only=True)
    df = con.execute(
        """
        SELECT
            s.job_id,
            s.source,
            s.source_job_id,
            s.title_clean,
            s.company,
            s.job_family,
            s.jf_domain,
            s.jf_subdomain,
            s.seniority,
            s.city,
            s.company_type,
            s.skills,
            s.n_skills,
            j.title_raw,
            j.description_raw
        FROM jobs_silver s
        JOIN jobs j USING (source, source_job_id)
        WHERE s.job_family IS NOT NULL
          AND s.job_family != 'OTHER'
          AND s.is_active
          AND s.is_duplicate_of IS NULL
        """
    ).df()
    con.close()

    df["skill_list"] = df["skills"].apply(_parse_skills)
    df["text"] = [
        _role_view(row.title_clean or row.title_raw, row.description_raw, row.skill_list)
        for row in df.itertuples(index=False)
    ]
    df["text_len"] = df["text"].str.len()
    return df.reset_index(drop=True)


def stop_words() -> set[str]:
    # Accent-folded Vietnamese + generic English recruiting words. Keep technology
    # and task terms so topics stay interpretable for the Data/AI market.
    words = """
    a an and are as at be by can cho cac can co cua duoc de den do doi du dung for from he
    her his hoac in into is it la lam moi mot nay of on or our qua se the their them this
    to trong tu va ve voi we will with you your
    ability able bachelor ban bao benefit benefits cao cap candidate candidates chinh chuyen
    company cong cong ty dau day degree dinh doanh doi experience experienced good hang he hieu
    hoc hop job jobs join ke khach kinh knowledge ky nang lam lien lieu linh luong ly management
    mo mo ta must nam nganh nghe nghiep nghiem nhan nhieu opportunity phai phan phat position
    preferred quan quyen related required requirement requirements responsibility responsibilities
    role san skills strong support tai team teams thang theo thong thuc tich tin tien toan toi
    tot tri trien trinh tro ung uu vien vu van viec work working xay years yeu cau
    """
    return {w.strip() for w in words.split() if w.strip()}


def vectorize_text(df: pd.DataFrame, *, min_df: int, max_df: float, max_features: int):
    from sklearn.feature_extraction.text import TfidfVectorizer

    vectorizer = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        stop_words=sorted(stop_words()),
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9+#.]{1,}\b",
        ngram_range=(1, 2),
        min_df=min_df,
        max_df=max_df,
        max_features=max_features,
        sublinear_tf=True,
    )
    X = vectorizer.fit_transform(df["text"])
    return X, vectorizer


def top_terms_for_model(model, terms: list[str], top_n: int) -> dict[int, list[tuple[str, float]]]:
    topics: dict[int, list[tuple[str, float]]] = {}
    for topic_id, weights in enumerate(model.components_):
        top_ids = weights.argsort()[::-1][:top_n]
        topics[topic_id] = [(terms[i], float(weights[i])) for i in top_ids]
    return topics


def topic_diversity(topics: dict[int, list[tuple[str, float]]]) -> float:
    terms = [term for values in topics.values() for term, _ in values]
    return len(set(terms)) / len(terms) if terms else 0.0


def choose_k(X, terms: list[str], *, k_min: int, k_max: int, top_n: int):
    from sklearn.decomposition import NMF

    rows = []
    models = {}
    upper = min(k_max, X.shape[0] - 1, X.shape[1] - 1)
    for k in range(k_min, upper + 1):
        model = NMF(
            n_components=k,
            init="nndsvda",
            random_state=SEED,
            max_iter=1000,
            solver="cd",
            beta_loss="frobenius",
        )
        W = model.fit_transform(X)
        topics = top_terms_for_model(model, terms, top_n=top_n)
        dominant = W.max(axis=1)
        total = W.sum(axis=1)
        dominant_share = dominant / total.clip(min=1e-12)
        diversity = topic_diversity(topics)
        # Heuristic score for exploratory reporting: prefer distinct topics and
        # documents with a clear dominant topic, with a small penalty for many k.
        score = (0.6 * diversity) + (0.4 * float(dominant_share.mean())) - (0.01 * k)
        rows.append(
            {
                "k": k,
                "reconstruction_error": round(float(model.reconstruction_err_), 4),
                "topic_diversity": round(float(diversity), 4),
                "mean_dominant_topic_share": round(float(dominant_share.mean()), 4),
                "selection_score": round(float(score), 4),
            }
        )
        models[k] = (model, W, topics)

    if not rows:
        raise ValueError(f"No valid k in range {k_min}-{k_max} for matrix shape {X.shape}.")

    scores = pd.DataFrame(rows)
    best_k = int(scores.sort_values(["selection_score", "topic_diversity"], ascending=False).iloc[0]["k"])
    model, W, topics = models[best_k]
    return best_k, scores, model, W, topics


def _fmt_counter(counter: Counter[str], total: int, top_n: int) -> str:
    parts = []
    for key, n in counter.most_common(top_n):
        parts.append(f"{key} ({n}, {100 * n / total:.1f}%)")
    return "; ".join(parts)


def build_topic_terms(topics: dict[int, list[tuple[str, float]]]) -> pd.DataFrame:
    rows = []
    for topic_id, values in topics.items():
        for rank, (term, weight) in enumerate(values, start=1):
            rows.append(
                {
                    "topic_id": int(topic_id),
                    "rank": int(rank),
                    "term": term,
                    "weight": round(weight, 6),
                }
            )
    return pd.DataFrame(rows)


def build_job_topics(df: pd.DataFrame, W) -> pd.DataFrame:
    import numpy as np

    dominant_topic = W.argmax(axis=1)
    dominant_weight = W.max(axis=1)
    total_weight = W.sum(axis=1)
    dominant_share = dominant_weight / np.clip(total_weight, 1e-12, None)

    out = df[
        [
            "job_id",
            "title_clean",
            "company",
            "job_family",
            "jf_domain",
            "jf_subdomain",
            "seniority",
            "city",
            "company_type",
            "n_skills",
            "text_len",
        ]
    ].copy()
    out["dominant_topic"] = dominant_topic.astype(int)
    out["topic_weight"] = [round(float(v), 6) for v in dominant_weight]
    out["dominant_topic_share"] = [round(float(v), 4) for v in dominant_share]
    return out.sort_values(["dominant_topic", "topic_weight"], ascending=[True, False]).reset_index(drop=True)


def summarize_topics(job_topics: pd.DataFrame, topic_terms: pd.DataFrame, top_n: int) -> pd.DataFrame:
    rows = []
    total = len(job_topics)
    for topic_id, part in job_topics.groupby("dominant_topic"):
        family_counts = Counter(part["job_family"])
        domain_counts = Counter(part["jf_domain"])
        dominant_family, dominant_n = family_counts.most_common(1)[0]
        top_terms = topic_terms[topic_terms["topic_id"] == topic_id].head(top_n)["term"].tolist()
        sample_titles = "; ".join(part.head(5)["title_clean"].fillna("").astype(str).tolist())
        rows.append(
            {
                "topic_id": int(topic_id),
                "n_jobs": int(len(part)),
                "pct_jobs": round(100 * len(part) / total, 1),
                "dominant_family": dominant_family,
                "dominant_family_n": int(dominant_n),
                "dominant_family_share": round(100 * dominant_n / len(part), 1),
                "top_families": _fmt_counter(family_counts, len(part), top_n=5),
                "top_domains": _fmt_counter(domain_counts, len(part), top_n=4),
                "top_terms": "; ".join(top_terms),
                "sample_titles": sample_titles,
            }
        )
    return pd.DataFrame(rows).sort_values("n_jobs", ascending=False).reset_index(drop=True)


def write_findings(
    *,
    base_n: int,
    modeled_n: int,
    dropped_short_text_n: int,
    n_features: int,
    best_k: int,
    k_scores: pd.DataFrame,
    summary: pd.DataFrame,
) -> None:
    k_rows = "\n".join(
        "| {k} | {reconstruction_error:.4f} | {topic_diversity:.4f} | {mean_dominant_topic_share:.4f} | {selection_score:.4f} |".format(
            **row
        )
        for row in k_scores.to_dict("records")
    )
    topic_rows = "\n".join(
        "| {topic_id} | {n_jobs} | {pct_jobs} | `{dominant_family}` | {dominant_family_share} | {top_terms} |".format(
            **row
        )
        for row in summary.to_dict("records")
    )
    doc = f"""# Topic Modeling Findings

Milestone P5 deliverable: NMF topic modeling on job-description text to surface hidden technology, task, and requirement themes beyond normalized skill tags.

## Business Question

Beyond normalized skill tags, what hidden technology, task, or requirement themes appear in Vietnamese Data/AI job descriptions?

## Metric

| Metric | Meaning |
|---|---|
| `topic_id` | Exploratory NMF topic identifier |
| `top_terms` | Highest-weight TF-IDF terms for the topic |
| `dominant_topic` | Topic with the largest NMF weight for a job |
| `topic_weight` | NMF weight of the dominant topic for a job |
| `pct_jobs` | Share of modeled jobs whose dominant topic is this topic |
| `dominant_family_share` | Share of the largest `job_family` inside the topic |

## Table

Input tables: `jobs_silver` joined with `jobs` on `(source, source_job_id)`.

Official analysis filter:

```sql
job_family IS NOT NULL
AND job_family != 'OTHER'
AND is_active
AND is_duplicate_of IS NULL
```

Text input: `title_clean` + normalized `skills` + `jobs.description_raw`, with light boilerplate trimming. `job_family` is used only after modeling for interpretation.

## Pipeline

Script: `analysis/topic_modeling.py`

Outputs:

| Artifact | Purpose |
|---|---|
| `analysis/outputs/topic_terms.csv` | Top terms per topic |
| `analysis/outputs/job_topics.csv` | One row per modeled job with dominant topic |
| `analysis/outputs/topic_summary.csv` | Topic size, dominant family/domain, representative terms |
| `analysis/outputs/topic_k_selection.csv` | Evidence for selected topic count |

## Run Evidence

- Official analysis base: {base_n} jobs
- Modeled jobs with usable text: {modeled_n}
- Dropped for short/empty text: {dropped_short_text_n}
- TF-IDF features: {n_features}
- Selected topics: {best_k}

### Topic Count Selection

`selection_score` is a lightweight interpretability proxy: topic diversity plus mean dominant-topic share, with a small penalty for larger k. It is used for reproducible exploratory reporting, not as a formal benchmark.

| k | reconstruction_error | topic_diversity | mean_dominant_topic_share | selection_score |
|---:|---:|---:|---:|---:|
{k_rows}

### Topic Summary

| Topic | Jobs | % | Dominant family | Dominant family share | Top terms |
|---:|---:|---:|---|---:|---|
{topic_rows}

## Interpretation

Topic modeling shows recurring JD themes that are not fully captured by simple market-share tables. A topic with a high dominant-family share is close to one family. A mixed topic means the same language or work theme crosses multiple job families.

## Recommendation

Use these topics as supporting evidence for learning paths and report narrative:

1. Pair topic themes with skill clustering to name practical tracks, such as BI/reporting, data engineering/cloud, and AI/ML delivery.
2. Use mixed topics to explain why some postings blur across BA, DA, DE, and AI roles.
3. Keep `job_family` as the main reporting unit; use topics only as exploratory text evidence.

## Limitations

- Topic labels are model-derived themes, not official job labels.
- JD text is bilingual and noisy; some terms may reflect generic recruiting language despite stop-word filtering.
- The model uses one snapshot only, so topics cannot be interpreted as increasing or decreasing trends.
- Salary is not available in this repo, so topics cannot imply compensation differences.
- This is unsupervised exploration, not a supervised classifier and not a replacement for `job_family`.
"""
    (ROOT / "docs" / "TOPIC_MODELING_FINDINGS.md").write_text(doc, encoding="utf-8")


def write_explained_vi(best_k: int, summary: pd.DataFrame) -> None:
    topic_rows = "\n".join(
        f"| {int(row.topic_id)} | {int(row.n_jobs)} | {row.pct_jobs} | `{row.dominant_family}` | {row.top_terms} |"
        for row in summary.itertuples(index=False)
    )
    doc = f"""# Giải Thích Topic Modeling

Topic modeling ở đây dùng để đọc phần JD/free-text và tìm các chủ đề lặp lại trong tin tuyển dụng Data/AI. Đây là bước khám phá, không phải model dự đoán.

## Cách Hiểu Nhanh

- `topic_id`: mã chủ đề do NMF tìm ra.
- `top_terms`: các từ/cụm từ có trọng số cao nhất, dùng để diễn giải topic.
- `dominant_topic`: topic mạnh nhất của một job.
- `topic_weight`: mức độ job gắn với topic đó.

Model không học từ `job_family`. `job_family` chỉ được dùng sau khi đã gán topic để xem topic nào nghiêng về family nào.

## Kết Quả Chính

Script chọn `{best_k}` topic.

| Topic | Số job | % job | Family nổi bật | Top terms |
|---:|---:|---:|---|---|
{topic_rows}

Lưu ý: `top_terms` là output trực tiếp từ model nên có thể không dấu, đặc biệt với JD tiếng Việt đã được normalize.

## Nên Dùng Kết Quả Này Thế Nào

Dùng topic modeling để bổ sung cho:

1. Market share theo `job_family`.
2. Association rules giữa các skill.
3. Skill clustering.

Topic nào có nhiều family trộn lẫn thì nên đọc như một chủ đề công việc chung, không đọc như một nhãn nghề mới.

## Hạn Chế

- JD có cả tiếng Việt và tiếng Anh nên term có thể có nhiều biến thể.
- Topic là chủ đề text, không phải nhãn nghề chính thức.
- Dữ liệu chỉ là một snapshot, không suy ra xu hướng tăng/giảm.
- Không có salary, không suy luận về thu nhập.
"""
    (ROOT / "docs" / "TOPIC_MODELING_EXPLAINED_VI.md").write_text(doc, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NMF topic modeling over Data/AI JD text.")
    parser.add_argument("--min-text-len", type=int, default=80)
    parser.add_argument("--min-df", type=int, default=5)
    parser.add_argument("--max-df", type=float, default=0.55)
    parser.add_argument("--max-features", type=int, default=2500)
    parser.add_argument("--k-min", type=int, default=5)
    parser.add_argument("--k-max", type=int, default=10)
    parser.add_argument("--top-n", type=int, default=10)
    args = parser.parse_args()

    jobs = load_jobs()
    base_n = len(jobs)
    modeled = jobs[jobs["text_len"] >= args.min_text_len].reset_index(drop=True)
    if modeled.empty:
        raise ValueError("No jobs with usable text after filtering.")

    X, vectorizer = vectorize_text(
        modeled,
        min_df=args.min_df,
        max_df=args.max_df,
        max_features=args.max_features,
    )
    terms = list(vectorizer.get_feature_names_out())
    best_k, k_scores, model, W, topics = choose_k(
        X,
        terms,
        k_min=args.k_min,
        k_max=args.k_max,
        top_n=args.top_n,
    )

    topic_terms = build_topic_terms(topics)
    job_topics = build_job_topics(modeled, W)
    summary = summarize_topics(job_topics, topic_terms, top_n=args.top_n)

    topic_terms.to_csv(OUT / "topic_terms.csv", index=False, encoding="utf-8")
    job_topics.to_csv(OUT / "job_topics.csv", index=False, encoding="utf-8")
    summary.to_csv(OUT / "topic_summary.csv", index=False, encoding="utf-8")
    k_scores.to_csv(OUT / "topic_k_selection.csv", index=False, encoding="utf-8")
    write_findings(
        base_n=base_n,
        modeled_n=len(modeled),
        dropped_short_text_n=base_n - len(modeled),
        n_features=len(terms),
        best_k=best_k,
        k_scores=k_scores,
        summary=summary,
    )
    write_explained_vi(best_k, summary)

    print(f"analysis_base {base_n}")
    print(f"modeled_jobs {len(modeled)}")
    print(f"dropped_short_text {base_n - len(modeled)}")
    print(f"tfidf_features {len(terms)}")
    print(f"selected_topics {best_k}")
    print(f"outputs {OUT / 'topic_summary.csv'}")
    print(summary.to_string(index=False).encode("ascii", errors="replace").decode("ascii"))


if __name__ == "__main__":
    main()
