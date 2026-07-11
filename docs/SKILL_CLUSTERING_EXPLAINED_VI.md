# Giải Thích Skill Clustering

Tài liệu này giải thích bước **Clustering skill profile** trong P5 Insight ML.

Bước này không dự đoán, không làm supervised classifier, không phân tích lương, không forecasting.
Đây là phân tích **unsupervised** để xem các job Data/AI có tự tạo thành những cụm kỹ năng tự nhiên hay không.

---

## 1. `job_family` có phải file `taxonomy_v1.yml` không?

Không.

`job_family` **không phải là file**. `job_family` là **cột nhãn nghề** trong bảng `jobs_silver`.

Ví dụ giá trị của `job_family`:

| `job_family` |
|---|
| `DATA_ENGINEER` |
| `DATA_ANALYST` |
| `BUSINESS_ANALYST` |
| `AI_ENGINEER` |
| `BI` |
| `DATA_SCIENTIST` |
| `OTHER` |

Trong khi đó, `taxonomy_v1.yml` là **file định nghĩa hệ thống nhãn**.

File taxonomy nằm ở:

```text
job_family_engine/taxonomy/taxonomy_v1.yml
```

File này định nghĩa cấu trúc phân cấp:

```text
Domain -> Sub-domain -> Family
```

Ví dụ quan hệ logic:

```text
Analytics
  -> Business / Product Analytics
      -> BUSINESS_ANALYST
      -> DATA_ANALYST
      -> PRODUCT_ANALYST

Data Engineering
  -> Data Platform / Pipeline
      -> DATA_ENGINEER
      -> BIG_DATA_ENGINEER

AI / Machine Learning
  -> Applied AI
      -> AI_ENGINEER
      -> GENAI_LLM
```

Tóm lại:

| Thành phần | Là gì? | Nằm ở đâu? | Vai trò |
|---|---|---|---|
| `taxonomy_v1.yml` | File cấu hình taxonomy | `job_family_engine/taxonomy/` | Định nghĩa danh sách domain, subdomain, family |
| `job_family` | Cột trong dữ liệu | `jobs_silver.job_family` | Nhãn nghề đã gán cho từng job |
| `jf_domain` | Cột trong dữ liệu | `jobs_silver.jf_domain` | Domain lớn của `job_family` |
| `jf_subdomain` | Cột trong dữ liệu | `jobs_silver.jf_subdomain` | Sub-domain của `job_family` |

Trong bước clustering, `job_family` **không được dùng làm feature**.

Script chỉ dùng cột `skills` để chia cụm. Sau khi chia cụm xong, mới dùng `job_family` để diễn giải:

> Cụm này chủ yếu là Data Engineer, AI Engineer, Data Analyst hay Business Analyst?

Cách làm này giúp tránh circularity/leakage: model không học trực tiếp từ nhãn nghề rồi lại được dùng để chứng minh nhãn nghề.

---

## 2. File `analysis/skill_clustering.py` làm gì?

File chính:

```text
analysis/skill_clustering.py
```

Business Question:

> Các job Data/AI ở Việt Nam có tự tách thành những cụm kỹ năng tự nhiên không, và các cụm đó khớp hay bị trộn với `job_family` như thế nào?

Luồng xử lý:

```text
jobs_silver
  -> lọc official analysis population
  -> đọc cột skills
  -> parse JSON skills thành list
  -> tạo skill vector cho mỗi job
  -> TF-IDF weighting
  -> L2 normalize
  -> thử KMeans với k=3..8
  -> chọn k theo silhouette_cosine
  -> gán cluster_id cho từng job
  -> tạo summary cho từng cluster
  -> xuất 3 file CSV + findings markdown
```

Filter SQL chính:

```sql
job_family IS NOT NULL
AND job_family != 'OTHER'
AND is_active
AND is_duplicate_of IS NULL
```

Ý nghĩa filter:

| Điều kiện | Ý nghĩa |
|---|---|
| `job_family IS NOT NULL` | Job đã có nhãn nghề |
| `job_family != 'OTHER'` | Loại job không phải Data/AI |
| `is_active` | Job còn active trong snapshot |
| `is_duplicate_of IS NULL` | Loại duplicate cross-source |

Kết quả chạy gần nhất:

| Chỉ số | Giá trị |
|---|---:|
| Official analysis base | 852 job |
| Job có skill dùng được để clustering | 806 job |
| Số skill trong vocabulary | 72 skill |
| Số cluster được chọn | 8 cluster |

---

## 3. CSV 1: `skill_clusters.csv`

Đường dẫn:

```text
analysis/outputs/skill_clusters.csv
```

### 3.1. File này có ý nghĩa gì?

Đây là file **job-level cluster assignment**.

Mỗi dòng là 1 job đã được clustering.

File này trả lời câu hỏi:

> Job này thuộc cluster nào?

Ví dụ:

| job_id | job_family | n_skills | cluster_id |
|---|---|---:|---:|
| `vietnamworks:...` | `DATA_ENGINEER` | 8 | 2 |
| `itviec:...` | `AI_ENGINEER` | 10 | 4 |
| `topcv:...` | `DATA_ANALYST` | 7 | 3 |

### 3.2. Các cột chính

| Cột | Ý nghĩa |
|---|---|
| `job_id` | ID duy nhất của job |
| `title_clean` | Tiêu đề job đã làm sạch |
| `company` | Tên công ty |
| `job_family` | Nhãn nghề đã gán bởi Job Family Labeling Engine |
| `jf_domain` | Domain lớn của job family |
| `jf_subdomain` | Sub-domain của job family |
| `seniority` | Cấp bậc |
| `city` | Thành phố |
| `company_type` | Loại công ty |
| `n_skills` | Số skill của job |
| `cluster_id` | Cụm skill mà KMeans gán cho job |

### 3.3. Tính toán như thế nào?

Bước 1: mỗi job có một danh sách skill.

Ví dụ:

```text
Job A: SQL, Python, ETL
Job B: SQL, Power BI, Reporting
Job C: Python, Machine Learning, LLM
```

Bước 2: tạo vocabulary skill.

Ví dụ:

```text
SQL, Python, ETL, Power BI, Reporting, Machine Learning, LLM
```

Bước 3: biến mỗi job thành vector.

```text
Job A = [1, 1, 1, 0, 0, 0, 0]
Job B = [1, 0, 0, 1, 1, 0, 0]
Job C = [0, 1, 0, 0, 0, 1, 1]
```

Bước 4: áp dụng TF-IDF để giảm độ áp đảo của skill quá phổ biến.

Công thức IDF trong script:

```text
idf(skill) = log((1 + số_job) / (1 + số_job_có_skill)) + 1
```

Ví dụ trực giác:

- `SQL` rất phổ biến nên vẫn quan trọng, nhưng không được để lấn át toàn bộ clustering.
- `LLM`, `ETL`, `Power BI`, `Agile` có thể đặc trưng hơn cho một số cụm.

Bước 5: normalize vector.

Mục đích: job có nhiều skill không tự động áp đảo job có ít skill.

Bước 6: KMeans gán mỗi job vào 1 `cluster_id`.

Kết quả cuối cùng được ghi vào `skill_clusters.csv`.

---

## 4. CSV 2: `skill_cluster_summary.csv`

Đường dẫn:

```text
analysis/outputs/skill_cluster_summary.csv
```

### 4.1. File này có ý nghĩa gì?

Đây là file **cluster-level summary**.

Mỗi dòng là 1 cluster.

File này trả lời câu hỏi:

> Mỗi cluster đại diện cho nhóm skill nào, gồm bao nhiêu job, và gần với job family nào nhất?

### 4.2. Các cột chính

| Cột | Ý nghĩa |
|---|---|
| `cluster_id` | ID của cluster |
| `n_jobs` | Số job trong cluster |
| `pct_jobs` | Tỷ lệ job trong cluster trên tổng số job clustered |
| `dominant_family` | Job family xuất hiện nhiều nhất trong cluster |
| `dominant_family_n` | Số job của dominant family trong cluster |
| `dominant_family_share` | Tỷ lệ dominant family trong cluster |
| `top_families` | Top job family trong cluster |
| `top_domains` | Top domain trong cluster |
| `top_skills` | Skill nổi bật trong cluster |

### 4.3. Tính `dominant_family_share` như thế nào?

Công thức:

```text
dominant_family_share = dominant_family_n / n_jobs * 100
```

Ví dụ cluster 2:

```text
n_jobs = 192
dominant_family = DATA_ENGINEER
dominant_family_n = 118
```

Tính:

```text
118 / 192 * 100 = 61.5%
```

Nghĩa là cluster 2 có 61.5% job là `DATA_ENGINEER`.

### 4.4. Tính `top_skills` như thế nào?

Với mỗi skill trong cluster:

```text
skill_share_in_cluster = số_job_trong_cluster_có_skill / số_job_trong_cluster
```

Sau đó tính lift:

```text
lift = skill_share_in_cluster / skill_share_overall
```

Ý nghĩa:

| Lift | Diễn giải |
|---:|---|
| `> 1` | Skill xuất hiện trong cluster nhiều hơn mức chung |
| `= 1` | Skill xuất hiện ngang mức chung |
| `< 1` | Skill kém đặc trưng cho cluster |

Ví dụ:

```text
Cluster AI có LLM (59%, lift 4.0)
```

Diễn giải:

> 59% job trong cluster AI có skill LLM, và LLM xuất hiện trong cluster này cao gấp 4 lần mức chung.

### 4.5. Kết quả đáng chú ý

| Cluster | Dominant family | Diễn giải nhanh |
|---:|---|---|
| 2 | `DATA_ENGINEER` | SQL, Data Warehouse, Python, ETL, Big Data |
| 4 | `AI_ENGINEER` | Machine Learning, Python, AI, LLM, Deep Learning |
| 3 | `DATA_ANALYST` | Power BI, SQL, Data Analysis, Reporting, Tableau |
| 1 | `BUSINESS_ANALYST` | Excel, Data Analysis, Reporting, English |
| 6 | `BUSINESS_ANALYST` | Agile, English, SQL, Data Analysis |

Insight:

- Data Engineering và AI/ML tách khá rõ theo skill.
- DA/BI/BA có sự chồng lắp lớn hơn.
- Điều này giải thích vì sao chỉ dùng title/rule để gán nhãn nghề sẽ dễ sai.

---

## 5. CSV 3: `skill_cluster_k_selection.csv`

Đường dẫn:

```text
analysis/outputs/skill_cluster_k_selection.csv
```

### 5.1. File này có ý nghĩa gì?

Đây là file **chọn số cluster k**.

Script thử nhiều giá trị k:

```text
k = 3, 4, 5, 6, 7, 8
```

Mỗi k sẽ chạy KMeans một lần, rồi tính metric đánh giá cluster.

File này trả lời câu hỏi:

> Tại sao chọn 8 cluster mà không phải 3, 4, 5, 6, 7?

### 5.2. Các cột chính

| Cột | Ý nghĩa |
|---|---|
| `k` | Số cluster thử nghiệm |
| `silhouette_cosine` | Độ tách biệt cluster theo cosine distance; cao hơn là tốt hơn |
| `calinski_harabasz` | Metric phụ; cao hơn thường tốt hơn |
| `davies_bouldin` | Metric phụ; thấp hơn thường tốt hơn |

### 5.3. Chọn k như thế nào?

Script chọn k theo ưu tiên:

```text
silhouette_cosine cao nhất
nếu bằng nhau thì xem thêm calinski_harabasz
```

Kết quả:

| k | silhouette_cosine |
|---:|---:|
| 3 | 0.1387 |
| 4 | 0.1534 |
| 5 | 0.1669 |
| 6 | 0.1835 |
| 7 | 0.1885 |
| 8 | 0.1905 |

`k=8` có silhouette cao nhất, nên script chọn:

```text
selected_k = 8
```

Lưu ý:

Silhouette không quá cao. Điều này bình thường với dữ liệu skill JD vì:

- Nhiều role dùng chung skill như SQL, Python, Reporting.
- BA, DA, BI, Risk có skill overlap.
- Skill tag chỉ là binary mention, không biết mức độ thành thạo.

Vì vậy cluster dùng để **hỗ trợ insight**, không dùng để thay thế `job_family`.

---

## 6. Nên đọc 3 CSV theo thứ tự nào?

Nên đọc theo thứ tự:

1. `skill_cluster_k_selection.csv`
   - Để biết vì sao chọn `k=8`.

2. `skill_cluster_summary.csv`
   - Để hiểu mỗi cluster đại diện cho skill profile nào.

3. `skill_clusters.csv`
   - Để drill-down xem từng job nằm trong cluster nào.

---

## 7. Kết luận cho báo cáo

Kết quả clustering ủng hộ 3 insight chính:

1. **Data Engineering có skill profile rõ**
   - SQL, Data Warehouse, ETL, Python, Big Data.

2. **AI/ML có skill profile rõ**
   - Python, Machine Learning, AI, LLM, Deep Learning.

3. **Analytics roles bị chồng lắp**
   - Data Analyst, BI, Business Analyst, Risk/Fraud Analyst có nhiều skill giao nhau:
     SQL, Reporting, Data Analysis, Excel, Power BI.

Ý nghĩa business:

- Người học không nên chỉ học từng skill riêng lẻ.
- Nên học theo cụm skill:
  - DE: SQL + Python + ETL + Data Warehouse.
  - AI/ML: Python + ML + AI/LLM.
  - DA/BI: SQL + Data Analysis + Reporting + Power BI/Tableau.
  - BA/Product: Excel + Analysis + Agile + business context.

Hạn chế:

- Chỉ có 1 snapshot, không được diễn giải thành trend.
- Không có salary, không kết luận về lương.
- Clustering là unsupervised, không phải classifier.
- Skill extraction chỉ cho biết JD có nhắc skill hay không, không đo proficiency.

