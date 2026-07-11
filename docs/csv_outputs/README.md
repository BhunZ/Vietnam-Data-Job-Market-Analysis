# CSV Outputs Dễ Đọc

Thư mục này là bản sao các CSV output từ `analysis/outputs/`, được gom theo từng bước để dễ đọc và gửi kèm báo cáo. Output gốc vẫn nằm ở `analysis/outputs/` để script/pipeline tiếp tục dùng.

## 01 Association Rules

Thư mục:

```text
docs/csv_outputs/01_association_rules/
```

| File | Đọc để làm gì |
|---|---|
| `association_rules.csv` | Các rule skill đi cùng nhau, ví dụ biết skill A thì thường gặp skill B |

Nên đọc khi cần viết phần learning path / skill bundle.

## 02 Skill Clustering

Thư mục:

```text
docs/csv_outputs/02_skill_clustering/
```

| File | Đọc để làm gì |
|---|---|
| `skill_cluster_summary.csv` | Đọc đầu tiên: tóm tắt mỗi cluster, dominant family, top skills |
| `skill_clusters.csv` | Drill-down từng job được gán cluster nào |
| `skill_cluster_k_selection.csv` | Bằng chứng chọn số cluster k |
| `skill_cluster_skill_share.csv` | Chi tiết skill share/lift trong từng cluster |

Nên đọc khi cần viết phần các nhóm skill tự nhiên và so sánh với `job_family`.

## 03 Topic Modeling

Thư mục:

```text
docs/csv_outputs/03_topic_modeling/
```

| File | Đọc để làm gì |
|---|---|
| `topic_summary.csv` | Đọc đầu tiên: tóm tắt mỗi topic, top terms, dominant family |
| `topic_terms.csv` | Chi tiết top terms và weight của từng topic |
| `job_topics.csv` | Drill-down từng job được gán dominant topic nào |
| `topic_k_selection.csv` | Bằng chứng chọn số topic k |

Nên đọc khi cần viết phần chủ đề ẩn trong JD/free-text.
