# Giải Thích Topic Modeling

Topic modeling ở đây dùng để đọc phần JD/free-text và tìm các chủ đề lặp lại trong tin tuyển dụng Data/AI. Đây là bước khám phá, không phải mô hình dự đoán.

## Cách Hiểu Nhanh

- `topic_id`: mã chủ đề do NMF tìm ra.
- `top_terms`: các từ/cụm từ có trọng số cao nhất, dùng để diễn giải topic.
- `dominant_topic`: topic mạnh nhất của một job.
- `topic_weight`: mức độ job gắn với topic đó.

Model không học từ `job_family`. `job_family` chỉ được dùng sau khi đã gán topic để xem topic nào nghiêng về family nào.

## Kết Quả Chính

Script chọn `5` topic.

| Topic | Số job | % job | Family nổi bật | Top terms |
|---:|---:|---:|---|---|
| 1 | 256 | 33.0 | `BUSINESS_ANALYST` | gia; ngan; te; vi; so; chi; hinh; quy; pham; hanh |
| 4 | 197 | 25.4 | `BUSINESS_ANALYST` | business; analytics; development; analysis; systems; performance; science; product; across; technical |
| 2 | 131 | 16.9 | `AI_ENGINEER` | ai; learning; machine learning; machine; llm; engineer ai; ai engineer; llm machine; python; pytorch |
| 3 | 101 | 13.0 | `DATA_ANALYST` | power bi; power; bi; reporting sql; reporting; data analysis; bi python; tableau; sql; analysis |
| 0 | 90 | 11.6 | `DATA_ENGINEER` | etl; data warehouse; warehouse; data engineer; sql; lake; spark; data lake; elt; modeling data |

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
