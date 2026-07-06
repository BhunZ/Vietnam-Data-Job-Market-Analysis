# Association Rules Findings

Milestone 9 deliverable: tìm các cụm skill thường đi cùng nhau để gợi ý learning path.

## Mục Tiêu Kinh Doanh

**Business Question**  
Người học nên học skill nào cùng nhau để tăng độ khớp với JD Data/AI ở Việt Nam?

**Metric**  
Association rules dùng:

| Metric | Ý nghĩa |
|---|---|
| `both_n` | Số job chứa cả antecedent và consequent |
| `support_pct` | Tỷ lệ job chứa cả hai phía của rule |
| `confidence` | Xác suất thấy consequent khi antecedent xuất hiện |
| `lift` | Mức liên kết cao hơn ngẫu nhiên; `lift > 1` là có liên kết dương |

**Input**  
`jobs_silver.skills`, lọc đúng analysis population:

```sql
job_family IS NOT NULL
AND job_family != 'OTHER'
AND is_active
AND is_duplicate_of IS NULL
```

Script: `analysis/association_rules.py`  
Output: `analysis/outputs/association_rules.csv`

## Kết Quả Chạy

```text
transactions: 711
rules: 1834
```

Lưu ý: `transactions` là các job có ít nhất 2 skill. Tổng analysis base là 852 job, nhưng association
rules cần job có nhiều hơn một skill để tạo rule.

## Finding 1: SQL Là Trục Trung Tâm

**Quan sát**  
SQL xuất hiện trong các rule có support cao nhất.

**Bằng chứng**

| Rule | both_n | support_pct | confidence | lift |
|---|---:|---:|---:|---:|
| Python -> SQL | 220 | 30.94 | 0.659 | 1.269 |
| SQL -> Python | 220 | 30.94 | 0.596 | 1.269 |
| Reporting -> SQL | 188 | 26.44 | 0.629 | 1.212 |
| Data Analysis -> SQL | 185 | 26.02 | 0.578 | 1.114 |

**Diễn giải**  
SQL là skill nền nối nhiều hướng nghề khác nhau: analytics, reporting, Python/data processing.

**Khuyến nghị**  
Người học nên xem SQL là skill nền bắt buộc trước khi chọn nhánh DA/BI, DE hoặc AI/ML.

**Hạn chế**  
SQL phổ biến không có nghĩa là chỉ cần SQL là đủ. Các rule cho thấy SQL cần đi kèm skill ứng dụng.

## Finding 2: Nhánh DA/BI Có Bundle Rõ Ràng

**Quan sát**  
Power BI, Reporting, Data Analysis, Tableau và SQL tạo thành một cụm kỹ năng rất chặt.

**Bằng chứng**

| Rule | both_n | support_pct | confidence | lift |
|---|---:|---:|---:|---:|
| Tableau -> Power BI | 101 | 14.21 | 0.927 | 3.344 |
| SQL + Tableau -> Power BI | 87 | 12.24 | 0.946 | 3.413 |
| Data Analysis + Tableau -> Power BI | 82 | 11.53 | 0.976 | 3.523 |
| Reporting + SQL -> Power BI | 119 | 16.74 | 0.633 | 2.285 |
| Power BI + Reporting -> SQL | 119 | 16.74 | 0.850 | 1.638 |

**Diễn giải**  
DA/BI không chỉ là "biết phân tích". JD thường ghép phân tích với báo cáo, BI tool và SQL.

**Khuyến nghị**  
Learning path cho DA/BI nên là:

1. SQL
2. Data Analysis
3. Reporting
4. Power BI hoặc Tableau

**Hạn chế**  
Power BI và Tableau có thể cùng xuất hiện trong JD như nhóm BI tools, không nhất thiết yêu cầu dùng cả hai
ở mức chuyên sâu.

## Finding 3: Nhánh AI/ML Tập Trung Quanh Python

**Quan sát**  
Machine Learning, AI, LLM, PyTorch/TensorFlow đều kéo mạnh về Python.

**Bằng chứng**

| Rule | both_n | support_pct | confidence | lift |
|---|---:|---:|---:|---:|
| Machine Learning -> Python | 168 | 23.63 | 0.724 | 1.542 |
| Machine Learning + SQL -> Python | 96 | 13.50 | 0.842 | 1.793 |
| LLM -> Python | 95 | 13.36 | 0.805 | 1.714 |
| AI + Python -> Machine Learning | 90 | 12.66 | 0.804 | 2.463 |
| TensorFlow -> PyTorch | 58 | 8.16 | 0.983 | 11.458 |

**Diễn giải**  
Với nhánh AI/ML, Python là nền tảng. Các framework deep learning như TensorFlow/PyTorch có lift rất cao,
nhưng support thấp hơn SQL/Python nên nên xem là skill chuyên sâu hơn.

**Khuyến nghị**  
Learning path cho AI/ML:

1. Python
2. Machine Learning
3. LLM hoặc AI application
4. PyTorch/TensorFlow nếu đi sâu vào deep learning

**Hạn chế**  
Lift rất cao của PyTorch/TensorFlow một phần do hai skill này thường được liệt kê cùng nhau trong nhóm JD
AI/deep learning. Không nên hiểu là mọi AI role đều cần cả hai framework.

## Finding 4: Nhánh Data Engineering Gắn Với SQL, Data Warehouse Và ETL

**Quan sát**  
Các skill hạ tầng dữ liệu có confidence cao khi dẫn về SQL.

**Bằng chứng**

| Rule | both_n | support_pct | confidence | lift |
|---|---:|---:|---:|---:|
| Data Warehouse -> SQL | 121 | 17.02 | 0.823 | 1.586 |
| ETL -> SQL | 110 | 15.47 | 0.827 | 1.594 |
| Big Data + Spark -> Hadoop | 32 | 4.50 | 0.640 | 11.376 |

**Diễn giải**  
Data Engineering trong dataset này vẫn có lõi SQL rất rõ. ETL và Data Warehouse là nhánh ứng dụng của SQL
trong bối cảnh pipeline/hạ tầng dữ liệu.

**Khuyến nghị**  
Learning path cho Data Engineering:

1. SQL
2. Python
3. ETL
4. Data Warehouse
5. Spark/Hadoop nếu nhắm vào Big Data

**Hạn chế**  
Big Data rule có support thấp hơn, nên chỉ nên xem là hướng chuyên biệt, không phải yêu cầu phổ quát cho mọi
Data Engineer.

## Learning Path Tổng Hợp

| Mục tiêu nghề | Skill bundle nên ưu tiên |
|---|---|
| Nền tảng chung | SQL + Python |
| Data Analyst / BI | SQL + Data Analysis + Reporting + Power BI/Tableau |
| Data Engineer | SQL + Python + ETL + Data Warehouse |
| AI/ML | Python + Machine Learning + LLM/AI + PyTorch/TensorFlow |

## Design Decision

Script tự tính association rules bằng Python thay vì phụ thuộc `mlxtend`, vì `mlxtend` nằm trong optional
dependency `analysis` và có thể chưa được cài ở mọi môi trường. Cách này giúp milestone chạy được với
dependency core hiện có của repo.

## Hạn Chế Chung

- Association rules đo đồng xuất hiện skill trong JD, không đo quan hệ nhân quả.
- Rule mạnh không có nghĩa là skill consequent phải học sau antecedent.
- Job không có đủ 2 skill không tham gia mining, nên kết quả nghiêng về các JD có skill list phong phú hơn.
- Đây vẫn là 1 snapshot, không dùng để nói skill nào đang tăng/giảm theo thời gian.
- Không có salary trong repo, nên không kết luận skill bundle nào có lương cao hơn.

