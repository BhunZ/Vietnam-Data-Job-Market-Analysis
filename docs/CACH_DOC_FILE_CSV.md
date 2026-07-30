# Cách đọc các file CSV kết quả phân tích (P5)

> **Không còn bản sao CSV trong `docs/`.** Trước đây có 9 file CSV copy tay từ `analysis/outputs/`. Vì
> không có bước tái sinh, chúng lệch dần: đến 2026-07-25 thì **7/9 file đã sai** (ví dụ
> `association_rules.csv` giữ 1.834 dòng trong khi bản thật lúc đó là 1.049). Đã xoá để chỉ còn **một
> nguồn duy nhất**. Bài học: đừng bao giờ copy số liệu sang file thứ hai mà không có script sinh lại.
>
> **Nguồn thật: `analysis/outputs/*.csv`** — tái sinh bằng:
>
> ```bash
> python analysis/association_rules.py
> python analysis/skill_clustering.py
> python analysis/topic_modeling.py
> ```

Tài liệu này chỉ giữ phần hữu ích: **đọc từng file như thế nào**.

## 1. Association rules — `analysis/outputs/association_rules.csv`

Mỗi dòng là một luật "tin tuyển dụng yêu cầu A thì cũng yêu cầu B".

| Cột | Ý nghĩa |
|---|---|
| `antecedent` / `consequent` | A (có thể 2 skill) → B (luôn 1 skill) |
| `both_n` | Số tin có **cả** A và B. Đây là cột đáng tin nhất — sắp xếp mặc định theo nó |
| `support_pct` | % trên **các tin có ≥2 skill**, KHÔNG phải trên toàn analysis base |
| `confidence` | P(B \| A) |
| `lift` | >1 nghĩa là A và B xuất hiện cùng nhau nhiều hơn mức ngẫu nhiên |
| `p_value` | Fisher exact một phía |
| `significant_bonferroni` | `True` = còn ý nghĩa sau hiệu chỉnh family-wise ở alpha = 0,05/**4060 giả thuyết đã test**. **Chỉ trích dẫn cột này** |
| `significant_at_kept_alpha` | Ngưỡng CŨ, quá lỏng (0,05/số luật giữ lại). Giữ để so sánh — **đừng dùng để trích dẫn** |

> **Số hiện tại (2026-07-28):** 663 transaction · 1649 luật · **1244 luật vượt Bonferroni**.
> `support_pct` chia cho **663** tin có ≥2 kỹ năng, KHÔNG phải 720 — cao hơn share thật khoảng 1,09 lần.
> Mỗi cặp 1-1 xuất hiện **hai chiều** (`Python→SQL` và `SQL→Python` là 2 dòng) nên số dòng ≠ số phát hiện.

⚠️ Đọc trước: `docs/ASSOCIATION_RULES_FINDINGS.md` (file này **tự sinh**, không sửa tay).

## 2. Skill clustering — `analysis/outputs/skill_cluster_*.csv`

Đọc theo thứ tự: `skill_cluster_summary.csv` → `skill_cluster_k_selection.csv` → `skill_clusters.csv`.

| Cột quan trọng | Ý nghĩa |
|---|---|
| `most_common_skills` | Skill phổ biến nhất trong cụm — "họ tuyển gì" |
| `most_distinctive_skills` | Skill có lift cao nhất — "cụm này **khác** ở đâu". Một skill có thể phổ biến mà không đặc trưng |
| `mean_silhouette` | Độ chặt của cụm. **Dưới ~0,10 nghĩa là thành viên gần cụm khác ngang gần cụm của mình** |
| `mean_n_skills` | Số tag trung bình. Gần 1–2 nghĩa là cụm đang gom *tin ít tag*, không phải gom nghề |
| `quality_flag` | `low_confidence` → **không dùng làm kết luận thị trường** |

⚠️ `skill_cluster_k_selection.csv` cho thấy silhouette dao động **0,13–0,20 qua toàn bộ k=2..20** → theo
quy ước là **không có cấu trúc cụm đáng kể**. k=8 được chọn để **dễ trình bày**, không phải vì tối ưu.
Cluster ID **thay đổi giữa các lần chạy** — đừng trích dẫn theo số, hãy trích theo dominant family + skill.

## 3. Topic modeling — `analysis/outputs/topic_*.csv`

Đọc theo thứ tự: `topic_summary.csv` → `topic_terms.csv` → `job_topics.csv`.

| Cột quan trọng | Ý nghĩa |
|---|---|
| `top_terms` | Term đại diện của topic |
| `interpretable` | `False` = top terms **không chứa từ vựng chuyên môn nào** → là boilerplate còn sót (mẫu liên hệ của nhà tuyển dụng, syllable tiếng Việt bị bỏ dấu). **Loại khỏi phần diễn giải** |
| `dominant_family_share` | % tin trong topic thuộc family áp đảo |

⚠️ `topic_k_selection.csv` chọn k theo **NPMI coherence** (cao hơn là tốt hơn).
`reconstruction_error` và `mean_dominant_topic_share` **giảm đơn điệu theo k về mặt toán học** nên chỉ để
tham khảo, KHÔNG dùng làm tiêu chí chọn.
