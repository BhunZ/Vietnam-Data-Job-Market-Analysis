# Báo Cáo Bàn Giao P5 Insight ML

Ngày: 2026-07-11

Phạm vi: báo cáo những việc đã làm trong P5 Insight ML, gồm **Association Rules**, **Skill Clustering** và **Topic Modeling**. Tài liệu này chỉ dựa trên artifact/code/docs đang có trong repo, không thêm salary, forecasting, supervised classifier, hay kết luận ngoài bằng chứng.

---

## 1. Nguyên Tắc Đã Tuân Thủ

Theo `PROJECT_STATUS.md`, `MASTER_PLAN.md`, `WORK_DIVISION.md`, `docs/DATA_DICTIONARY.md`:

- Không làm salary.
- Không forecasting vì hiện chỉ có 1 snapshot.
- Không supervised classifier.
- Phân tích chính dùng `job_family`, không dùng legacy `role_category` làm analytical unit.
- Đi theo mạch:

```text
Business Question -> Metric -> Table -> Pipeline -> SQL -> Code
```

- Evidence phải đến từ repo: docs, source code, database, output CSV/Markdown.

---

## 2. Trạng Thái P5 Hiện Tại

| Hạng mục | Trạng thái |
|---|---|
| Association Rules | Xong |
| Skill Clustering | Xong |
| Topic Modeling | Xong |

P5 Insight ML hiện đã có đủ script, CSV output và tài liệu findings cho 3 bước chính.

---

## 3. Những Việc Đã Làm Ở Bước Này

Trong lượt làm việc này, phần được tiếp tục và hoàn tất là **Topic Modeling**, đồng thời dọn lại tài liệu/bản sao CSV để dễ đọc và bàn giao.

### 3.1. Hoàn thành Topic Modeling

Đã thêm script:

```text
analysis/topic_modeling.py
```

Script này thực hiện:

1. Đọc `jobs_silver` và join với bảng `jobs` để lấy `description_raw`.
2. Lọc đúng official analysis population:

```sql
job_family IS NOT NULL
AND job_family != 'OTHER'
AND is_active
AND is_duplicate_of IS NULL
```

3. Tạo text đầu vào từ `title_clean + skills + description_raw`.
4. Loại job có text quá ngắn.
5. Vector hóa text bằng TF-IDF.
6. Chạy NMF với nhiều giá trị `k`.
7. Chọn số topic bằng `selection_score`.
8. Gán `dominant_topic` cho từng job.
9. Tổng hợp topic theo `job_family`, `jf_domain`, `jf_subdomain`.
10. Xuất CSV và Markdown findings.

Kết quả chạy:

| Metric | Giá trị |
|---|---:|
| Official analysis base | 852 |
| Modeled jobs có usable text | 775 |
| Jobs bị loại vì text ngắn/thiếu | 77 |
| TF-IDF features | 2380 |
| Selected topics | 5 |

### 3.2. Sinh Output CSV Cho Topic Modeling

Đã sinh các file:

| File | Vai trò |
|---|---|
| `analysis/outputs/topic_summary.csv` | Tóm tắt mỗi topic: số job, % job, dominant family, top terms |
| `analysis/outputs/topic_terms.csv` | Top terms và weight của từng topic |
| `analysis/outputs/job_topics.csv` | Mỗi job và topic chính được gán |
| `analysis/outputs/topic_k_selection.csv` | Bằng chứng chọn số topic `k=5` |

Các CSV này là output chính để đọc kết quả topic model.

### 3.3. Viết Tài Liệu Báo Cáo Topic Modeling

Đã thêm/cập nhật:

| File | Nội dung |
|---|---|
| `docs/TOPIC_MODELING_FINDINGS.md` | Findings chính theo mạch Business Question -> Metric -> Table -> Pipeline -> Evidence |
| `docs/TOPIC_MODELING_EXPLAINED_VI.md` | Giải thích ngắn bằng tiếng Việt về topic modeling |
| `docs/TOPIC_MODELING_STEP_REPORT_VI.md` | Báo cáo riêng bước Topic Modeling: làm gì, đọc CSV như thế nào, CSV có tác dụng gì |

Trong `TOPIC_MODELING_STEP_REPORT_VI.md`, đã giải thích rõ cách đọc từng CSV:

- `topic_summary.csv`: đọc đầu tiên để hiểu mỗi topic.
- `topic_terms.csv`: đọc để xem term/weight chi tiết.
- `job_topics.csv`: đọc để drill-down từng job.
- `topic_k_selection.csv`: đọc để hiểu vì sao chọn `k=5`.

### 3.4. Gom CSV Vào `docs` Để Dễ Đọc

Đã copy các CSV output từ `analysis/outputs/` sang:

```text
docs/csv_outputs/
```

Cấu trúc đã tạo:

```text
docs/csv_outputs/
  README.md
  01_association_rules/
    association_rules.csv
  02_skill_clustering/
    skill_clusters.csv
    skill_cluster_summary.csv
    skill_cluster_k_selection.csv
    skill_cluster_skill_share.csv
  03_topic_modeling/
    job_topics.csv
    topic_summary.csv
    topic_terms.csv
    topic_k_selection.csv
```

Lưu ý: đây là **bản sao để đọc/báo cáo**. Output gốc vẫn nằm ở `analysis/outputs/` để script và pipeline tiếp tục dùng.

### 3.5. Chuẩn Hóa Tài Liệu Tiếng Việt Có Dấu

Đã chỉnh các file Markdown tiếng Việt không dấu sang tiếng Việt có dấu:

| File | Trạng thái |
|---|---|
| `docs/P5_HANDOFF_REPORT_VI.md` | Đã viết lại có dấu và cập nhật trạng thái P5 |
| `docs/TOPIC_MODELING_STEP_REPORT_VI.md` | Đã viết có dấu |
| `docs/TOPIC_MODELING_EXPLAINED_VI.md` | Đã viết có dấu |
| `docs/csv_outputs/README.md` | Đã viết có dấu |

Không chỉnh các term trong CSV như `gia; ngan; te...` vì đó là output trực tiếp từ model sau normalize text, không phải phần văn bản báo cáo.

### 3.6. Kiểm Tra Sau Khi Làm

Đã kiểm tra:

- `analysis/topic_modeling.py` compile được.
- `analysis/topic_modeling.py` chạy thành công và sinh đủ CSV.
- `analysis/validate_gold.py` vẫn pass, không ảnh hưởng Gold/analysis base.

Kết luận của bước này: **Topic Modeling đã hoàn thành và sẵn sàng dùng trong báo cáo P5**.

---

## 4. Validation Đã Chạy Lại

Đã chạy:

```bash
python analysis/validate_gold.py
```

Kết quả quan trọng:

| Check | Kết quả |
|---|---:|
| Analysis base | 852 |
| `gold_market_share.SUM(n)` | 852 |
| `gold_market_share.SUM(pct)` | 99.9 |
| Duplicate grain `gold_family_skill` | 0 |
| Duplicate grain `gold_company` | 0 |
| Duplicate grain `gold_location` | 0 |
| Duplicate grain `gold_seniority` | 0 |
| Duplicate grain `gold_skill_cooccurrence` | 0 |

Giải thích `99.9`: do làm tròn 1 chữ số thập phân, không phải lỗi dữ liệu.

Top 5 market share từ validation:

| Rank | Job family | n | pct |
|---:|---|---:|---:|
| 1 | `BUSINESS_ANALYST` | 181 | 21.2 |
| 2 | `DATA_ENGINEER` | 149 | 17.5 |
| 3 | `DATA_ANALYST` | 125 | 14.7 |
| 4 | `AI_ENGINEER` | 118 | 13.8 |
| 5 | `RISK_FRAUD_ANALYST` | 52 | 6.1 |

---

## 5. Association Rules

### Mục tiêu

Tìm các skill thường xuất hiện cùng nhau trong JD để hỗ trợ câu hỏi learning path: biết skill A thì thường nên học/đi kèm skill B nào.

### Artifact

| Artifact | Vai trò |
|---|---|
| `analysis/association_rules.py` | Script mine association rules |
| `analysis/outputs/association_rules.csv` | Output rules |
| `docs/ASSOCIATION_RULES_FINDINGS.md` | Diễn giải findings |
| `docs/csv_outputs/01_association_rules/association_rules.csv` | Bản sao CSV trong docs để dễ đọc |

### Filter

```sql
job_family IS NOT NULL
AND job_family != 'OTHER'
AND is_active
AND is_duplicate_of IS NULL
```

### Kết quả

| Metric | Giá trị |
|---|---:|
| Transactions | 711 |
| Rules | 1834 |

### Cách diễn giải

- Association rules chỉ nói skill cùng xuất hiện trong JD, không phải quan hệ nhân quả.
- Job có dưới 2 skill không tham gia mining.
- Không dùng rules để nói trend tăng/giảm vì chỉ có 1 snapshot.
- Không có salary nên không kết luận skill bundle nào có lương cao hơn.

---

## 6. Skill Clustering

### Business Question

> Các job Data/AI ở Việt Nam có tự tách thành những cụm skill tự nhiên không, và các cụm đó khớp hay bị trộn với `job_family` như thế nào?

### Artifact

| Artifact | Vai trò |
|---|---|
| `analysis/skill_clustering.py` | Script clustering skill profile |
| `analysis/outputs/skill_clusters.csv` | Mỗi dòng = 1 job đã được gán cluster |
| `analysis/outputs/skill_cluster_summary.csv` | Tóm tắt mỗi cluster |
| `analysis/outputs/skill_cluster_k_selection.csv` | Evidence chọn k |
| `analysis/outputs/skill_cluster_skill_share.csv` | Skill share/lift chi tiết theo cluster |
| `docs/SKILL_CLUSTERING_FINDINGS.md` | Findings clustering |
| `docs/SKILL_CLUSTERING_EXPLAINED_VI.md` | Giải thích tiếng Việt về clustering |
| `docs/csv_outputs/02_skill_clustering/` | Bản sao CSV trong docs để dễ đọc |

### Cách làm

1. Đọc `jobs_silver`.
2. Lọc official analysis population.
3. Parse cột `skills`.
4. Tạo skill vector cho mỗi job.
5. Áp dụng TF-IDF weighting.
6. Normalize vector.
7. Chạy KMeans với nhiều giá trị `k`.
8. Chọn `k` bằng `silhouette_cosine`.
9. Xuất cluster assignment, cluster summary, k-selection evidence, skill-share-by-cluster.

`job_family` không dùng làm feature. `job_family` chỉ dùng sau clustering để diễn giải cluster.

### Kết quả

| Metric | Giá trị |
|---|---:|
| Official analysis base | 852 |
| Jobs có usable skills | 806 |
| Vocabulary skills | 72 |
| Selected k | 8 |

### Tóm tắt cluster

| Cluster | Jobs | Dominant family | Dominant family share | Top skills |
|---:|---:|---|---:|---|
| 2 | 192 | `DATA_ENGINEER` | 61.5 | SQL, Data Warehouse, Python, ETL, Big Data, Reporting |
| 4 | 180 | `AI_ENGINEER` | 61.7 | Machine Learning, Python, AI, LLM, English, Deep Learning |
| 3 | 159 | `DATA_ANALYST` | 40.3 | Power BI, SQL, Data Analysis, Reporting, Tableau, Python |
| 1 | 80 | `BUSINESS_ANALYST` | 43.8 | Excel, Data Analysis, Reporting, English, SQL, Power BI |
| 0 | 59 | `BUSINESS_ANALYST` | 30.5 | English, Data Analysis, Reporting, SQL, Python, Data Governance |
| 7 | 59 | `BUSINESS_ANALYST` | 47.5 | Data Analysis, Statistics, Business Intelligence, SQL, C++, Data Governance |
| 6 | 40 | `BUSINESS_ANALYST` | 75.0 | Agile, English, SQL, Data Analysis, Azure, Reporting |
| 5 | 37 | `BUSINESS_ANALYST` | 40.5 | Reporting, Data Analysis, SQL, Data Governance, Oracle, Big Data |

### Hạn chế

- Skill tag chỉ cho biết JD có nhắc skill hay không, không đo proficiency.
- Job không có usable skills sau vocabulary filter bị loại khỏi clustering.
- KMeans ép mỗi job vào một cluster.
- Cluster dùng để hỗ trợ insight, không thay thế `job_family`.
- Chỉ có 1 snapshot, không diễn giải thành trend.
- Không có salary, không suy luận về thu nhập.

---

## 7. Topic Modeling

### Business Question

> Ngoài skill tags đã normalize, nội dung JD của các job Data/AI ở Việt Nam còn thể hiện những chủ đề công nghệ, nhiệm vụ, hay yêu cầu ẩn nào?

### Artifact

| Artifact | Vai trò |
|---|---|
| `analysis/topic_modeling.py` | Script NMF topic modeling trên JD/text |
| `analysis/outputs/topic_terms.csv` | Top terms mỗi topic |
| `analysis/outputs/job_topics.csv` | Mỗi job và dominant topic |
| `analysis/outputs/topic_summary.csv` | Topic size, dominant family/domain, representative terms |
| `analysis/outputs/topic_k_selection.csv` | Evidence chọn số topic |
| `docs/TOPIC_MODELING_FINDINGS.md` | Findings theo framework |
| `docs/TOPIC_MODELING_EXPLAINED_VI.md` | Giải thích tiếng Việt |
| `docs/TOPIC_MODELING_STEP_REPORT_VI.md` | Báo cáo riêng bước Topic Modeling |
| `docs/csv_outputs/03_topic_modeling/` | Bản sao CSV trong docs để dễ đọc |

### Cách làm

Pipeline:

```text
jobs_silver + jobs.description_raw
  -> filter analysis population
  -> tạo text field từ title + skills + JD
  -> loại job có text quá ngắn
  -> TF-IDF vectorization
  -> NMF topic modeling với nhiều giá trị k
  -> chọn k bằng selection_score
  -> gán dominant topic cho từng job
  -> tổng hợp topic theo job_family/domain
  -> xuất CSV + findings Markdown
```

Model dùng:

```text
TF-IDF + NMF
```

Lý do chọn NMF:

- Không cần dependency mới ngoài `scikit-learn`.
- Top terms dễ đọc và dễ giải thích.
- Phù hợp với mục tiêu exploratory trong báo cáo Data Analyst.

### Kết quả

| Metric | Giá trị |
|---|---:|
| Official analysis base | 852 |
| Modeled jobs có usable text | 775 |
| Jobs bị loại vì text ngắn/thiếu | 77 |
| TF-IDF features | 2380 |
| Selected topics | 5 |

### Topic Summary

| Topic | Jobs | Dominant family | Top terms |
|---:|---:|---|---|
| 1 | 256 | `BUSINESS_ANALYST` | gia; ngan; te; vi; so; chi; hinh; quy; pham; hanh |
| 4 | 197 | `BUSINESS_ANALYST` | business; analytics; development; analysis; systems; performance; science; product |
| 2 | 131 | `AI_ENGINEER` | ai; learning; machine learning; llm; python; pytorch |
| 3 | 101 | `DATA_ANALYST` | power bi; reporting; data analysis; tableau; sql |
| 0 | 90 | `DATA_ENGINEER` | etl; data warehouse; sql; data lake; spark |

Lưu ý: topic 1 là cụm text nghiệp vụ/tài chính/quy trình bằng tiếng Việt còn khá rộng; cần diễn giải thận trọng như một theme JD, không phải nhãn nghề hay công nghệ riêng.

### Hạn chế

- Topic model phụ thuộc chất lượng JD.
- JD song ngữ Việt-Anh có thể làm term bị tách hoặc normalize không dấu.
- Topic là chủ đề text, không phải nhãn nghề.
- Topic không nói skill nào tăng/giảm theo thời gian.
- Không suy luận salary.

---

## 8. Giải Thích `job_family`, Domain, Subdomain

Theo `docs/DATA_DICTIONARY.md` và taxonomy:

| Cột/File | Ý nghĩa |
|---|---|
| `job_family` | Cột nhãn nghề trong `jobs_silver`, ví dụ `DATA_ENGINEER`, `DATA_ANALYST`, `AI_ENGINEER` |
| `jf_domain` | Nhóm nghề lớn của `job_family` |
| `jf_subdomain` | Nhóm nhỏ hơn trong domain |
| `taxonomy_v1.yml` | File định nghĩa cây taxonomy Domain -> Sub-domain -> Family |

Quan hệ:

```text
Domain -> Sub-domain -> Job family
```

Trong clustering và topic modeling:

- Feature đầu vào không dùng `job_family`.
- `job_family`, `jf_domain`, `jf_subdomain` chỉ dùng để diễn giải sau khi model đã chạy.

---

## 9. Cách Đọc CSV Đã Gom Trong `docs`

Các CSV output đã được copy sang:

```text
docs/csv_outputs/
```

Cấu trúc:

```text
docs/csv_outputs/
  README.md
  01_association_rules/
    association_rules.csv
  02_skill_clustering/
    skill_clusters.csv
    skill_cluster_summary.csv
    skill_cluster_k_selection.csv
    skill_cluster_skill_share.csv
  03_topic_modeling/
    job_topics.csv
    topic_summary.csv
    topic_terms.csv
    topic_k_selection.csv
```

File nên đọc trước:

| Bước | File đọc trước |
|---|---|
| Association Rules | `association_rules.csv` |
| Skill Clustering | `skill_cluster_summary.csv` |
| Topic Modeling | `topic_summary.csv` |

---

## 10. Lệnh Hữu Ích

Validate Gold:

```bash
python analysis/validate_gold.py
```

Chạy lại Association Rules:

```bash
python analysis/association_rules.py
```

Chạy lại Skill Clustering:

```bash
python analysis/skill_clustering.py
```

Chạy lại Topic Modeling:

```bash
python analysis/topic_modeling.py
```

---

## 11. Tóm Tắt Ngắn

P5 Insight ML đã xong:

- Association Rules:
  - `analysis/association_rules.py`
  - `analysis/outputs/association_rules.csv`
  - `docs/ASSOCIATION_RULES_FINDINGS.md`
  - Kết quả: `711 transactions`, `1834 rules`

- Skill Clustering:
  - `analysis/skill_clustering.py`
  - `analysis/outputs/skill_clusters.csv`
  - `analysis/outputs/skill_cluster_summary.csv`
  - `analysis/outputs/skill_cluster_k_selection.csv`
  - `analysis/outputs/skill_cluster_skill_share.csv`
  - `docs/SKILL_CLUSTERING_FINDINGS.md`
  - `docs/SKILL_CLUSTERING_EXPLAINED_VI.md`
  - Kết quả: `852 analysis base`, `806 clustered jobs`, `72 skills`, `k=8`

- Topic Modeling:
  - `analysis/topic_modeling.py`
  - `analysis/outputs/topic_terms.csv`
  - `analysis/outputs/job_topics.csv`
  - `analysis/outputs/topic_summary.csv`
  - `analysis/outputs/topic_k_selection.csv`
  - `docs/TOPIC_MODELING_FINDINGS.md`
  - `docs/TOPIC_MODELING_EXPLAINED_VI.md`
  - `docs/TOPIC_MODELING_STEP_REPORT_VI.md`
  - Kết quả: `852 analysis base`, `775 modeled jobs`, `2380 TF-IDF features`, `5 topics`

Nguyên tắc tiếp tục:

- Không salary.
- Không forecasting.
- Không supervised classifier.
- Không dùng cluster/topic model để thay thế `job_family`.
