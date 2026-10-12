# QUY TRÌNH TỐI ƯU HÓA: LANE A, LANE B VÀ QUY TRÌNH CHUNG §2
**Tài liệu quy trình và quy tắc nghiệp vụ — Phiên bản 1 (v1.0)**

---

## 1. Tổng quan và Nguyên tắc xuyên suốt

Hệ thống tối ưu hóa gồm hai luồng vào và một quy trình chung:
- **Lane A (Yêu cầu thủ công):** Người nêu feature cần tối ưu, hệ thống khai thác dữ liệu thực tế và đề xuất phương án.
- **Lane B (Hệ thống tự phát hiện):** AI tự quét log Loki, tự tìm bottleneck, tự đề xuất giải pháp, con người đóng vai trò người duyệt.
- **§2 (Quy trình chung):** Cả hai lane hội tụ về cùng một schema giải pháp kèm tradeoff, sau đó đi qua 8 bước nghiêm ngặt từ Re-rank đến Rollout.

### Ba Nguyên tắc Cốt lõi
| Nguyên tắc | Ý nghĩa | Hệ quả thực tế |
| :--- | :--- | :--- |
| **Đo trước khi sửa** | Không có baseline thì không có cải thiện, chỉ có cảm giác | Snapshot baseline bị đóng băng trước khi chạm vào bất kỳ thứ gì |
| **Xác minh trước khi tin** | Nguyên nhân phải có bằng chứng (Log, KG, Code), số đo phải qua kiểm tra hợp lệ | Suy đoán bị chuyển sang mục Giả thuyết, phép so sánh sai bị loại ngay |
| **Rẻ trước khi đắt** | Thử Config trước, rồi Prompt, cuối cùng mới đến Code | Các phase và kế hoạch Rollout đều tuân thủ bậc rủi ro tăng dần |

### Thuật ngữ Chuẩn hóa
- **Fingerprint:** Mã định danh `Feature + Rule Variant + Subflow Version + Environment`. Hai đợt đo chỉ được so sánh khi Fingerprint khớp $100\%$.
- **Snapshot:** Bản đóng băng duy nhất của baseline gồm khoảng thời gian, query, số mẫu, fingerprint và config thực tế.
- **Guardrail:** Ràng buộc cứng không được phép đánh đổi (ví dụ: Độ chính xác / Chất lượng không giảm).
- **Bậc rủi ro (Risk Tier):** $\text{Config} < \text{Prompt} < \text{Code}$. Config sửa nhanh và lùi dễ nhất; Code ảnh hưởng rộng nhất và lùi tốn kém nhất.
- **Business Rule Card:** Tóm tắt 1 trang về feature: chức năng, quy tắc quyết định độ phức tạp, ràng buộc không được vi phạm.

---

## 2. Lane A: Yêu cầu thủ công

### A1. Input Yêu cầu (Optimization Brief)
- **A1-R1:** Một brief chỉ bao gồm 1 feature và 1 biến thể rule. Yêu cầu dạng "tối ưu cả pipeline" bắt buộc phải tách nhỏ.
- **A1-R2:** Mọi tiêu chí phải quy ra số cụ thể và tra cứu được từ Loki, KG hoặc Code. Metric không có log phải báo ngay là "chưa đo được".
- **A1-R3:** Guardrail không bao giờ bị đánh đổi để lấy mục tiêu. Mọi brief bắt buộc có ít nhất 1 guardrail.
- **A1-R4:** Ngưỡng GIỮ ($\ge 25\%$) và REVERT ($< 10\%$) phải chốt từ đầu trước khi có số thực tế.
- **A1-R5:** Bậc rủi ro tối đa được chốt rõ. Solution nào vượt trần phải gắn cờ riêng.
- **A1-R6:** Bắt buộc lập Business Rule Card trước khi chuyển sang A2.

### A2. Đo Baseline thật (Baseline Report)
- **A2-R1:** Chỉ dùng log các lần chạy thật đã có trong Loki. Tuyệt đối không chạy thử riêng để đo.
- **A2-R2:** Chỉ lấy các lần chạy có Fingerprint khớp $100\%$. Chặn lỗi so sánh hai feature khác nhau.
- **A2-R3:** Loại bỏ các lần chạy trong đợt sự cố, deploy hoặc tải bất thường. Mẫu $< 30$ phải gắn cờ "Baseline yếu".
- **A2-R4:** Báo cáo phân phối đầy đủ ($p_{50}, p_{90}, p_{99}$), không chỉ báo trung bình.
- **A2-R5:** Đối chiếu số trong log với Config và Code thực tế đang chạy trên Production.
- **A2-R6:** Đóng băng Snapshot ID duy nhất làm mẫu số đối chứng cho bước Đo lại.
- **A2-R7:** Metric thiếu log ghi nhận là khoảng trống dữ liệu, không điền số ước chừng.

### A3. Lên Solutions kèm Tradeoff (Solutions List)
- **A3-R1:** Nguyên nhân gốc phải được xác minh bằng bằng chứng (Log/KG/Code). Chưa có bằng chứng phải đưa vào mục "Giả thuyết chưa xác minh".
- **A3-R2:** Một solution chỉ đổi duy nhất một biến.
- **A3-R3:** Mỗi solution gắn bậc rủi ro và không vượt trần A1-R5.
- **A3-R4:** Pros/Cons bắt buộc đối chiếu với cả tiêu chí mục tiêu lẫn guardrails.
- **A3-R5:** Tác động kỳ vọng ghi dạng khoảng (ví dụ: $-10\%$ đến $-20\%$).
- **A3-R6:** Bắt buộc có kế hoạch đo lại và phương án Rollback viết sẵn.
- **A3-R7:** Sắp xếp danh sách solution theo bậc rủi ro tăng dần (Config $\rightarrow$ Prompt $\rightarrow$ Code).

---

## 3. Lane B: Hệ thống tự phát hiện

### B0. Tiền đề Cấu hình nền (Policy)
- **B0-R1:** Không có Policy thì Lane B không được phép chạy. Policy đóng vai trò làm A1 ẩn (Feature registry, tiêu chí/guardrail mặc định, Risk Ceiling, Scanning budget).

### B1. Tự quét Bottleneck & Tự lấy Baseline
- **B1-R1:** Chỉ sử dụng dữ liệu log Loki thực tế có sẵn.
- **B1-R2:** Log không suy ra được Fingerprint phải đánh dấu "Không so sánh được", tuyệt đối không gom bừa.
- **B1-R3:** Báo động giả: Bottleneck phải lặp lại qua nhiều kỳ quét mới được coi là cấu trúc.
- **B1-R4:** Xếp hạng theo công thức: $\text{Score} = \text{Tỷ trọng} \times \text{Tần suất chạy} \times \text{Độ ổn định}$.
- **B1-R5:** Baseline yếu (thiếu mẫu) không được đẩy sang B2.
- **B1-R6:** Tra cứu Kho bài học. Bottleneck đã xử lý hoặc bị REVERT không được đề xuất lại.
- **B1-R7:** Đối chiếu Config thực tế đang chạy ở Production.

### B2. Tự lên Solution rồi Propose
- **B2-R1:** AI chỉ đề xuất, tuyệt đối không tự động áp dụng bất kỳ thay đổi nào.
- **B2-R2:** Mỗi nguyên nhân phải dẫn tới bằng chứng cụ thể.
- **B2-R3:** Self-Criticism trước khi gửi: Kiểm tra Guardrail, xung đột dữ liệu và kho bài học.
- **B2-R4:** Gắn chỉ số tin cậy (Confidence Score) cho từng đề xuất.
- **B2-R5:** Không đề xuất vượt Risk Ceiling của Policy. Bắt buộc có đường lùi.
- **B2-R6:** Giới hạn số lượng đề xuất mỗi kỳ để tránh gây duyệt theo quán tính.
- **B2-R7:** Đọc Business Rule Card trước khi đề xuất.
- **B2-R8:** Mở quyền theo giai đoạn (Config $\rightarrow$ Prompt $\rightarrow$ Code) dựa trên tỷ lệ duyệt & giữ.

---

## 4. §2: Quy trình chung (Tái lập & Kiểm chứng)

- **S01-R1 đến S01-R4 (Re-rank):** Re-rank theo đúng tiêu chí A1/Policy. Solution vi phạm Guardrail bị loại lập tức. Ghi rõ lý do chọn/loại. Solution xung đột không chọn cùng lúc.
- **S02-R1 đến S02-R4 (Plan & Task list):** Chia Phase theo đúng bậc rủi ro (`P1: Config` $\rightarrow$ `P2: Prompt` $\rightarrow$ `P3: Code`). Mỗi Phase đổi đúng 1 biến và có tiêu chí "xong" độc lập.
- **S03-R1 đến S03-R3 (Implementation):** Mỗi Phase là 1 lần sửa độc lập. Không gộp Phase. Đánh dấu commit/chú thích theo từng Phase.
- **S04-R1 đến S04-R3 (Testing):** Test ngay sau mỗi Phase. Kiểm tra cả chức năng lẫn Guardrail trước khi sang Phase tiếp theo.
- **S05-R1 đến S05-R4 (Đo lại):**
  - **S05-R3 (Danh sách kiểm tra hợp lệ):** Cùng Fingerprint + Khoảng điều kiện tương đương + Đủ số mẫu + Chỉ lệch đúng 1 biến đã đổi.
  - Phép so sánh không hợp lệ phải hủy số liệu và đo lại.
- **S06-R1 đến S06-R4 (Quyết định):**
  - **GIỮ:** Đạt ngưỡng $\ge 25\%$ & Guardrail an toàn $\rightarrow$ Chuyển S07 Report.
  - **SỬA 1 PHẦN:** Đúng hướng nhưng 1 phase chưa đạt $\rightarrow$ Quay lại S03 sửa đúng phase đó.
  - **REVERT:** $< 10\%$ hoặc vi phạm Guardrail $\rightarrow$ Quay lại S01 chọn solution tiếp theo, ghi rõ lý do vào Kho bài học.
- **S07-R1 đến S07-R3 (Report):** Phân loại rõ 3 mục (Xong thật, Đơn giản hóa có lý do, Còn thiếu). Đưa bài học vào Kho bài học.
- **S08-R1 đến S08-R3 (Rollout):** Bật dần theo nấc rủi ro tăng dần. Sẵn sàng đường lùi ở mỗi nấc.

---

## 5. Bảng ma trận Quy tắc & Gate kiểm soát

| Mã Node | Đầu ra chính | Cổng kiểm soát (Gate) | Mã quy tắc trọng yếu |
| :--- | :--- | :--- | :--- |
| **A1** | Optimization Brief | Gate 1: Đo được, không mâu thuẫn | `A1-R1` đến `A1-R6` |
| **A2** | Baseline Report + Snapshot ID | Gate 2: Đủ mẫu, chuẩn Fingerprint | `A2-R1` đến `A2-R7` |
| **A3** | Solution List + Tradeoff Matrix | Gate 3: Bằng chứng 100%, có đường lùi | `A3-R1` đến `A3-R7` |
| **B1** | Ranked Bottlenecks + Baseline | Gate B1: Lặp lại qua nhiều kỳ, deduplicated | `B1-R1` đến `B1-R7` |
| **B2** | Executive Proposal Package | Gate B2: Qua Self-Critique, có Confidence | `B2-R1` đến `B2-R8` |
| **§2 (01-08)** | Retest Report & Decision | Step 06 Gate: KEEP / MODIFY / REVERT | `S01-R1` đến `S08-R3` |
