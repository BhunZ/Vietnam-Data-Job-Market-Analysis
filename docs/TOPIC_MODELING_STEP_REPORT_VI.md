# Báo Cáo Bước Topic Modeling

Ngày cập nhật: 2026-07-11

Phạm vi file này: chỉ báo cáo riêng bước **Topic Modeling** trong P5 Insight-ML. Không báo cáo lại Association Rules, Skill Clustering, EDA, Gold, salary, forecasting hay supervised classifier.

---

## 1. Mục Tiêu Của Bước Này

Topic Modeling được làm để trả lời câu hỏi:

> Ngoài các skill tag đã được normalize, nội dung JD của các job Data/AI ở Việt Nam còn thể hiện những chủ đề công nghệ, nhiệm vụ, hay yêu cầu ẩn nào?

Nói ngắn gọn: bước này đọc free-text trong JD để tìm các **chủ đề lặp lại** như Data Engineering/ETL, AI/ML/LLM, BI/reporting, business analytics.

Đây là model **unsupervised/exploratory**, không phải model dự đoán và không dùng để thay thế `job_family`.

---

## 2. Đầu Vào Đã Dùng

Script mới:

```text
analysis/topic_modeling.py
```

Script đọc dữ liệu từ DuckDB:

```text
data/warehouse.duckdb
```

Bảng đầu vào:

| Bảng | Vai trò |
|---|---|
| `jobs_silver` | Lấy job đã clean, `job_family`, domain/subdomain, company, skills, seniority |
| `jobs` | Lấy JD gốc từ cột `description_raw` |

Hai bảng được join bằng:

```sql
USING (source, source_job_id)
```

Filter dùng đúng population chính thức của phân tích:

```sql
job_family IS NOT NULL
AND job_family != 'OTHER'
AND is_active
AND is_duplicate_of IS NULL
```

Text đưa vào model gồm:

```text
title_clean + skills + description_raw
```

Trong đó JD được trim nhẹ boilerplate và cắt độ dài để tránh một JD quá dài chi phối model.

---

## 3. Cách Làm

Pipeline trong script:

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

Model được dùng:

```text
TF-IDF + NMF
```

Lý do chọn NMF:

- Nhẹ, reproducible, chạy bằng `scikit-learn`.
- Top terms của mỗi topic dễ đọc và dễ giải thích hơn.
- Phù hợp với mục tiêu Data Analyst: khám phá theme, không benchmark học thuật.

---

## 4. Kết Quả Chạy

| Metric | Giá trị |
|---|---:|
| Official analysis base | 852 job |
| Job có text đủ dùng để model | 775 job |
| Job bị loại vì text ngắn/thiếu | 77 job |
| TF-IDF features | 2380 |
| Số topic được chọn | 5 |

File kết quả chính:

```text
analysis/outputs/topic_summary.csv
analysis/outputs/topic_terms.csv
analysis/outputs/job_topics.csv
analysis/outputs/topic_k_selection.csv
```

File diễn giải:

```text
docs/TOPIC_MODELING_FINDINGS.md
docs/TOPIC_MODELING_EXPLAINED_VI.md
```

---

## 5. Cách Đọc Các File CSV

### 5.1. `topic_summary.csv`

Đường dẫn:

```text
analysis/outputs/topic_summary.csv
```

Mỗi dòng = **một topic**.

Đây là file nên đọc đầu tiên vì nó trả lời nhanh:

- Có bao nhiêu topic?
- Mỗi topic có bao nhiêu job?
- Topic đó nghiêng về job family nào?
- Top terms nào đại diện cho topic?

| Cột | Cách đọc | Tác dụng |
|---|---|---|
| `topic_id` | Mã topic do model tạo | Dùng để nói topic 0/1/2... trong các file khác |
| `n_jobs` | Số job có dominant topic là topic này | Đo quy mô của topic |
| `pct_jobs` | Tỷ lệ job trong tập modeled | Biết topic nào lớn/nhỏ |
| `dominant_family` | Job family xuất hiện nhiều nhất trong topic | Xem topic có gắn với family nào |
| `dominant_family_share` | % của family lớn nhất trong topic | Đo mức độ topic “sạch” hay bị trộn |
| `top_families` | Các family nhiều nhất trong topic | Xem topic có bị mix BA/DA/DE/AI không |
| `top_domains` | Domain nhiều nhất trong topic | Nhìn ở cấp domain lớn hơn |
| `top_terms` | Từ/cụm từ đại diện topic | Dùng để đặt tên/diễn giải topic |
| `sample_titles` | Một số title đại diện | Kiểm tra topic có hợp lý không |

Ví dụ cách đọc:

- Topic có top terms `etl; data warehouse; sql; spark; data lake` và dominant family `DATA_ENGINEER` có thể diễn giải là **Data Engineering / Data Platform**.
- Topic có top terms `ai; machine learning; llm; python; pytorch` và dominant family `AI_ENGINEER` có thể diễn giải là **AI/ML/LLM Engineering**.
- Topic có top terms `power bi; reporting; tableau; sql` và dominant family `DATA_ANALYST` có thể diễn giải là **BI / Reporting Analytics**.

Tác dụng trong báo cáo:

- Làm bảng tổng hợp topic.
- Chọn 3-5 theme chính để viết narrative.
- So sánh topic với `job_family` để xem JD text có ủng hộ taxonomy hay không.

---

### 5.2. `topic_terms.csv`

Đường dẫn:

```text
analysis/outputs/topic_terms.csv
```

Mỗi dòng = **một term trong một topic**.

| Cột | Cách đọc | Tác dụng |
|---|---|---|
| `topic_id` | Topic chứa term này | Join/đối chiếu với `topic_summary.csv` |
| `rank` | Thứ hạng term trong topic | Rank 1 là term mạnh nhất |
| `term` | Từ/cụm từ của topic | Dùng để đặt tên topic |
| `weight` | Trọng số của term trong topic | Weight cao hơn nghĩa là term đại diện topic mạnh hơn |

File này chi tiết hơn `topic_summary.csv`. Nếu `topic_summary.csv` chỉ show top terms đã gom lại thành chuỗi, thì `topic_terms.csv` cho từng term riêng để lọc, vẽ bảng, hoặc plot.

Tác dụng trong báo cáo:

- Tạo bảng “Top terms per topic”.
- Đặt nhãn diễn giải cho topic.
- Kiểm tra topic có bị nhiễm từ chung/generic không.

Lưu ý:

- Term có weight cao không có nghĩa là skill đó quan trọng nhất thị trường.
- Nó chỉ có nghĩa là term đó đại diện mạnh cho topic text trong NMF.

---

### 5.3. `job_topics.csv`

Đường dẫn:

```text
analysis/outputs/job_topics.csv
```

Mỗi dòng = **một job đã được gán dominant topic**.

| Cột | Cách đọc | Tác dụng |
|---|---|---|
| `job_id` | ID job | Đối chiếu về job gốc |
| `title_clean` | Title đã clean | Đọc mẫu job trong topic |
| `company` | Công ty | Có thể xem topic theo employer |
| `job_family` | Nhãn nghề chính thức | So sánh topic với family |
| `jf_domain`, `jf_subdomain` | Domain/subdomain của family | Phân tích ở cấp lớn hơn |
| `seniority` | Cấp bậc | Xem topic có nghiêng về junior/mid/senior không |
| `city` | Thành phố | Có thể crosstab topic theo địa điểm |
| `company_type` | Loại công ty | Có thể crosstab topic theo loại công ty |
| `n_skills` | Số skill tag | Kiểm tra job có nhiều/ít skill |
| `text_len` | Độ dài text đưa vào model | Kiểm tra chất lượng text |
| `dominant_topic` | Topic mạnh nhất của job | Cột chính của file này |
| `topic_weight` | Trọng số topic mạnh nhất | Đo mức độ job gắn với topic |
| `dominant_topic_share` | Tỷ trọng topic mạnh nhất trên tổng topic weight | Cao hơn = job rõ topic hơn |

Tác dụng trong báo cáo/phân tích:

- Drill-down từng job trong một topic.
- Lấy ví dụ title/job đại diện cho topic.
- Crosstab topic với `job_family`, seniority, city, company type.
- Kiểm tra các job có `dominant_topic_share` thấp để phát hiện job hybrid.

Ví dụ cách dùng:

```text
Lọc dominant_topic = 0
-> đọc các title top topic_weight
-> nếu nhiều Data Engineer và top terms là ETL/DWH/Spark
-> có thể diễn giải topic 0 là Data Engineering / Data Platform
```

---

### 5.4. `topic_k_selection.csv`

Đường dẫn:

```text
analysis/outputs/topic_k_selection.csv
```

Mỗi dòng = **một giá trị k đã thử**.

| Cột | Cách đọc | Tác dụng |
|---|---|---|
| `k` | Số topic đã thử | Ứng viên số topic |
| `reconstruction_error` | Lỗi tái tạo của NMF | Thấp hơn thường tốt hơn, nhưng không phải tiêu chí duy nhất |
| `topic_diversity` | Độ đa dạng của top terms giữa các topic | Cao hơn = topic ít trùng lặp hơn |
| `mean_dominant_topic_share` | Trung bình mức rõ topic của job | Cao hơn = mỗi job có topic chính rõ hơn |
| `selection_score` | Điểm tổng hợp để chọn k | Điểm cao nhất được chọn |

Kết quả hiện tại:

```text
k = 5
```

Lý do:

- `k=5` có `selection_score` cao nhất.
- Topic diversity cao.
- Mean dominant topic share cao hơn các k lớn hơn.
- K lớn hơn giảm reconstruction error nhưng topic bị chia nhỏ và kém rõ hơn.

Tác dụng trong báo cáo:

- Làm bằng chứng rằng số topic không chọn tùy tiện.
- Giải thích vì sao dùng 5 topic.
- Bảo vệ tính reproducible của bước topic modeling.

---

## 6. Nên Diễn Giải Topic Như Thế Nào

Từ `topic_summary.csv`, có thể diễn giải các topic chính như sau:

| Topic | Diễn giải đề xuất | Bằng chứng terms |
|---:|---|---|
| 0 | Data Engineering / Data Platform | `etl`, `data warehouse`, `sql`, `data lake`, `spark` |
| 2 | AI/ML/LLM Engineering | `ai`, `machine learning`, `llm`, `python`, `pytorch` |
| 3 | BI / Reporting Analytics | `power bi`, `reporting`, `tableau`, `sql`, `data analysis` |
| 4 | Business Analytics / Product-Systems Analytics | `business`, `analytics`, `systems`, `performance`, `product` |
| 1 | Business/finance/process Vietnamese JD theme | `gia`, `ngan`, `te`, `so`, `quy`, `pham`, `hanh` |

Lưu ý riêng topic 1:

Topic 1 là topic lớn nhất nhưng top terms còn khá chung và bị ảnh hưởng bởi tiếng Việt không dấu sau khi normalize. Không nên đặt tên quá mạnh như “Financial Analytics” nếu chưa đọc thêm job mẫu. Nên diễn giải thận trọng là **nhóm JD nghiệp vụ/tài chính/quy trình bằng tiếng Việt**, và dùng `sample_titles` + `job_topics.csv` để kiểm tra thêm.

---

## 7. Bước Này Có Tác Dụng Gì

Topic Modeling bổ sung cho skill tags ở 3 điểm:

1. **Bắt được theme trong JD free-text**
   Skill tags chỉ là danh sách skill đã normalize. JD có thể nói về platform, process, product, business context mà skill tag không bắt hết.

2. **Kiểm tra xem topic text có khớp với `job_family` không**
   Ví dụ Data Engineering topic có dominant family `DATA_ENGINEER` cao thì ủng hộ taxonomy. Topic nào mix nhiều family thì cho thấy thị trường có vùng giao thoa.

3. **Tạo narrative cho báo cáo**
   Thay vì chỉ nói “SQL/Python/Power BI xuất hiện nhiều”, topic modeling giúp nói thành các track:
   - Data Platform / ETL / Warehouse
   - BI / Reporting
   - AI / ML / LLM
   - Business Analytics

---

## 8. Hạn Chế

- Topic là chủ đề text, không phải nhãn nghề chính thức.
- JD song ngữ Việt-Anh và nhiều JD tiếng Việt không dấu làm topic có thể bị nhiều term generic.
- `topic_weight` không phải mức độ quan trọng của skill trên thị trường.
- Model chỉ dùng một snapshot, không được diễn giải thành xu hướng tăng/giảm.
- Không có salary, không suy luận topic nào có lương cao hơn.
- Đây không phải supervised classifier, không dùng để predict job family.

---

## 9. Definition Of Done Của Bước Này

Bước Topic Modeling đã hoàn thành vì có đủ:

| Yêu cầu | Trạng thái |
|---|---|
| Script chạy được | Đạt: `analysis/topic_modeling.py` |
| Output CSV | Đạt: 4 file CSV trong `analysis/outputs/` |
| Findings Markdown | Đạt: `docs/TOPIC_MODELING_FINDINGS.md` |
| Giải thích tiếng Việt | Đạt: `docs/TOPIC_MODELING_EXPLAINED_VI.md` |
| Cập nhật status/checklist | Đạt: `PROJECT_STATUS.md`, `WORK_DIVISION.md`, `P5_HANDOFF_REPORT_VI.md` |
| Không vi phạm scope | Đạt: không salary, không forecasting, không supervised classifier |
