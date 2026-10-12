# Kế hoạch triển khai chi tiết: hệ thống tối ưu Lane A, Lane B và quy trình §2
**Kế hoạch thực thi, phiên bản 1.** Thời gian là ước lượng tương đối và cần xác nhận lại sau Phase 0. Mã công việc (ví dụ P2-T4) dùng để ghi vào `tasks.md`.

---

## 1. Mục tiêu, phạm vi và nguyên tắc

### Mục tiêu
1. Có một quy trình tối ưu lặp lại được: từ yêu cầu hoặc từ phát hiện tự động, đến solution có tradeoff, đến thay đổi đã đo và đã rollout.
2. Mọi quyết định dựa trên số đo từ log thật, không dựa trên cảm giác.
3. Lane B tự phát hiện và đề xuất được, nhưng quyền tự chủ chỉ mở rộng khi có số liệu chứng minh.

### Trong phạm vi
- Xây nền tảng dùng chung (fingerprint, mẫu tài liệu, schema, kho bài học).
- Vận hành Lane A, Lane B và 8 bước của §2 trên feature thí điểm, sau đó mở rộng.

### Ngoài phạm vi (giai đoạn này)
- Đổi model hoặc đổi business rule.
- Cho Lane B tự áp dụng thay đổi mà không qua người duyệt.
- Tối ưu ở mức hạ tầng (scale, cache tầng mạng) không liên quan đến flow của feature.

**Nguyên tắc xuyên suốt:** đo trước khi sửa, xác minh trước khi tin, rẻ trước khi đắt (config, rồi prompt, rồi code). Mỗi phase có cổng kiểm tra và đường lùi riêng.

---

## 2. Giả định cần xác nhận trước khi bắt đầu

| # | Giả định | Cách xác nhận | Nếu sai |
|---|---|---|---|
| 1 | Loki có log các lần chạy thật, có label theo feature và step | Chạy truy vấn thử trên 1 feature, kiểm tra label | Phase 0 thêm việc bổ sung log, lùi lịch |
| 2 | Log có thời gian từng step và token từng prompt | Kiểm tra field trong 20 bản ghi mẫu | Metric thiếu được ghi là khoảng trống, chưa dùng làm tiêu chí |
| 3 | Truy cập được KG và code để đối chiếu config, prompt, flow | Thử đọc config của feature thí điểm | Nhờ owner cấp quyền, trong lúc chờ chỉ làm Lane A mức quan sát |
| 4 | Có người hiểu nghiệp vụ của feature thí điểm để xác nhận Business Rule Card | Chỉ định domain owner | Không có thì chưa được bật Lane B cho feature đó |
| 5 | Config đổi được mà không cần deploy lớn, và có đường lùi nhanh | Hỏi đội vận hành, thử đổi và lùi một config không quan trọng | Phase 3 chỉ làm với thay đổi có quy trình deploy rõ ràng |
| 6 | Số lần chạy của feature thí điểm đủ để có thống kê | Đếm số lần chạy 30 ngày gần nhất | Chọn feature khác hoặc kéo dài cửa sổ đo |

---

## 3. Vai trò

| Vai trò | Trách nhiệm chính |
|---|---|
| **Chủ chương trình** | Quyết định ưu tiên, duyệt tại các điểm go/no-go, giữ ngưỡng và guardrail |
| **Kỹ sư observability** | Loki, label, truy vấn baseline, bổ sung log, snapshot |
| **Kỹ sư flow/AI** | Phân tích config, prompt, code; implement từng phase; đường lùi |
| **Domain owner (nghiệp vụ)** | Xác nhận Business Rule Card, guardrail chất lượng, kiểm tra fingerprint đúng nghiệp vụ |
| **Người duyệt** | Duyệt đề xuất Lane B và danh sách sau re-rank |
| **QA** | Test từng phase, kiểm tra guardrail, kiểm tra tính hợp lệ của phép so sánh |

*Một người có thể kiêm nhiều vai trò, nhưng người implement không nên là người duy nhất xác nhận kết quả đo.*

---

## 4. Tổng quan lộ trình

| Phase | Tên | Thời lượng | Phụ thuộc | Rủi ro | Cổng ra |
|---|---|---|---|---|---|
| 0 | Chuẩn bị và kiểm kê dữ liệu | 3 ngày | Không | Rất thấp | Chốt feature thí điểm, biết khoảng trống dữ liệu |
| 1 | Nền tảng dùng chung | 1 tuần | Phase 0 | Thấp | Mẫu và schema được dùng thử thành công |
| 2 | Lane A trên feature thí điểm | 2 tuần | Phase 1 | Thấp (chưa sửa hệ thống) | Danh sách solution có bằng chứng |
| 3 | §2 chạy trọn một vòng | 2 tuần | Phase 2 | Trung bình | Một vòng đủ 01 đến 08 có quyết định dựa trên số đo |
| 4 | Lane B chế độ quan sát | 2 tuần | Phase 1, nên sau Phase 2 | Thấp | Quét tìm lại được bottleneck của Lane A |
| 5 | Lane B đề xuất mức config | 2 tuần | Phase 3, 4 | Trung bình | Có số liệu duyệt và giữ lại |
| 6 | Đối chiếu, nới quyền, mở rộng | Liên tục | Phase 5 | Cao hơn | Mỗi lần nới quyền có quyết định ghi lại |

*Phase 3 và Phase 4 có thể chạy song song nếu có đủ người, vì Phase 4 chỉ đọc log. Tổng thời gian đến hết Phase 5 khoảng 10 đến 11 tuần.*

---

## 5. Chi tiết từng phase

### Phase 0: Chuẩn bị và kiểm kê dữ liệu
**Mục tiêu:** biết chắc dữ liệu nào đo được và chọn đúng feature thí điểm trước khi xây bất cứ thứ gì.
**Công việc:**
- **P0-T1.** Chọn feature thí điểm (1 đến 2 feature). Tiêu chí chọn: chạy thường xuyên (đủ mẫu trong 30 ngày), nghiệp vụ ổn định, có domain owner, có dấu hiệu bottleneck, thay đổi ở mức config an toàn. Tránh feature có nhiều biến thể rule chưa được phân loại.
- **P0-T2.** Kiểm kê Loki. Liệt kê label hiện có (feature, step, run id), field (thời gian, token, retry, lỗi), retention, có sample hay không, độ trễ log.
- **P0-T3.** Kiểm kê KG và code. Xác định chỗ chứa config, prompt, định nghĩa flow, và cách biết giá trị config đang chạy thật ở production.
- **P0-T4.** Báo cáo khoảng trống dữ liệu. Mỗi metric thuộc một trong ba nhóm: đo được ngay, đo được sau khi bổ sung log, chưa đo được. Lập kế hoạch bổ sung log cho nhóm hai.
- **P0-T5.** Chốt tham số chung. Số mẫu tối thiểu, khoảng thời gian chuẩn của baseline, quy tắc loại sự cố và deploy, định nghĩa «lần chạy hợp lệ».
- **P0-T6.** Chốt cách ghi tiến độ. Định dạng `tasks.md`: mã công việc, trạng thái, bằng chứng, lý do revert.

**Đầu ra:** danh sách feature thí điểm, báo cáo khoảng trống dữ liệu, bộ tham số chung, mẫu `tasks.md`.
**Tiêu chí xong:** mọi giả định ở mục 2 đã được xác nhận hoặc có phương án thay; có ít nhất một feature thí điểm đủ mẫu và có domain owner.
**Đường lùi:** không có thay đổi hệ thống nên không cần lùi. Nếu không feature nào đủ điều kiện thì dừng, bổ sung log rồi quay lại.

---

### Phase 1: Nền tảng dùng chung
**Mục tiêu:** tạo các mẫu và quy ước mà cả hai lane và §2 cùng dùng, để kết quả có thể so sánh với nhau.
**Công việc:**
- **P1-T1.** Đặc tả fingerprint. Gồm feature, biến thể rule, số bước subflow, môi trường. Viết cách suy ra từ log và từ config. Quy định rõ trường hợp không suy ra được thì gắn «không so sánh được».
- **P1-T2.** Business Rule Card. Mẫu một trang: feature làm gì, rule nào quyết định độ phức tạp, đầu vào và đầu ra, ràng buộc không được vi phạm. Viết card cho feature thí điểm, domain owner xác nhận.
- **P1-T3.** Mẫu Optimization Brief (A1). Trường bắt buộc: fingerprint, tiêu chí kèm số, mục tiêu và guardrail, ngưỡng GIỮ và REVERT, bậc rủi ro tối đa, phạm vi.
- **P1-T4.** Mẫu Baseline Report và snapshot (A2, B1). Snapshot gồm khoảng thời gian, query, số mẫu, fingerprint, giá trị config lúc đo, người tạo.
- **P1-T5.** Schema solution card. Các trường: ID, nguồn (Lane A hoặc B), fingerprint, snapshot ID, nguyên nhân kèm bằng chứng và trạng thái xác minh, mô tả thay đổi, bậc rủi ro, pros/cons theo từng tiêu chí, tác động kỳ vọng dạng khoảng, công sức, kế hoạch đo lại, đường lùi, độ tin cậy (bắt buộc với Lane B), phụ thuộc và xung đột.
- **P1-T6.** Kho bài học. Mỗi mục gồm solution, fingerprint, kết quả đo, quyết định, lý do. Bắt đầu bằng ví dụ thật: STEP3_SUBFLOW_MAX_STEPS 6 xuống 3, đo đúng cặp cùng feature, không có bằng chứng tốt hơn, revert về 6.
- **P1-T7.** Checklist hợp lệ của phép so sánh. Cùng fingerprint, điều kiện tương đương, đủ mẫu, khác biệt chỉ là biến đã đổi.
- **P1-T8.** Bộ truy vấn Loki mẫu. Thời gian theo step, token theo prompt, tỷ lệ retry và lỗi, phân phối p50/p90/p99. Kiểm thử trên dữ liệu thật, đối chiếu thủ công vài mẫu.

**Đầu ra:** bộ mẫu và schema, card của feature thí điểm, bộ truy vấn đã kiểm thử, kho bài học khởi tạo.
**Tiêu chí xong:** hai người độc lập cùng gán fingerprint cho cùng một lô log ra kết quả giống nhau; schema chứa được ví dụ thật ở P1-T6 mà không phải bỏ trường; truy vấn mẫu cho số khớp với đối chiếu thủ công.
**Đường lùi:** chỉ là tài liệu nên có thể sửa tự do, nhưng mọi thay đổi schema sau Phase 2 phải ghi lại để không làm vỡ dữ liệu cũ.

---

### Phase 2: Lane A trên feature thí điểm
**Mục tiêu:** chạy A1, A2, A3 trọn vẹn để kiểm chứng mẫu và tạo danh sách solution đầu tiên. Phase này không sửa hệ thống thật.
**Công việc:**
- **P2-T1.** Lập Optimization Brief (A1). Cùng domain owner chốt tiêu chí thành số, guardrail, ngưỡng, bậc rủi ro tối đa. Qua Cổng 1.
- **P2-T2.** Kéo baseline (A2). Chạy bộ truy vấn trên khoảng thời gian chuẩn, lọc theo fingerprint, loại sự cố, kiểm tra số mẫu.
- **P2-T3.** Phân rã và thống kê. Tỷ trọng thời gian và token theo step, tuần tự hay song song, phân phối p50/p90/p99.
- **P2-T4.** Đối chiếu config, prompt, code. So giá trị trong log với giá trị đang chạy thật; giải thích mọi chỗ lệch.
- **P2-T5.** Đóng băng snapshot và đối chiếu chéo. Người khác chạy lại query, kết quả phải khớp. Qua Cổng 2.
- **P2-T6.** Truy nguyên nhân (A3). Với mỗi bottleneck, tìm nguyên nhân bằng log, KG, code. Ghi rõ cách đã xác minh.
- **P2-T7.** Soạn solution card. Sắp từ config đến code, tách riêng giả thuyết chưa xác minh. Mỗi solution chỉ đổi một biến.
- **P2-T8.** Review với domain owner. Kiểm tra nghiệp vụ và guardrail, loại solution có nguy cơ làm sai rule.

**Đầu ra:** Optimization Brief, Baseline Report kèm snapshot, danh sách solution card, mục giả thuyết chưa xác minh, danh sách bổ sung log cần làm.
**Tiêu chí xong:** qua Cổng 1 và Cổng 2; 100% solution chính có bằng chứng; mỗi solution có đo lại và đường lùi; domain owner đã review.
**Rủi ro:** baseline nhiễm sự cố (loại bằng P0-T5); số mẫu thấp (kéo dài cửa sổ hoặc gắn cờ baseline yếu).

---

### Phase 3: Quy trình §2 chạy trọn một vòng
**Mục tiêu:** chứng minh 8 bước hoạt động bằng một thay đổi thật, rủi ro thấp.
**Công việc:**
- **P3-T1.** Re-rank hoặc để người quyết (bước 01). Lọc theo guardrail, xếp theo tiêu chí A1, ghi lý do chọn và loại. Chọn một solution mức config làm vòng đầu.
- **P3-T2.** Lập plan và task list (bước 02). Chia phase theo bậc rủi ro, mỗi phase có tiêu chí xong, test, cách đo lại, đường lùi.
- **P3-T3.** Implement phase đầu (bước 03). Một phase một lần sửa, đánh dấu để lùi độc lập.
- **P3-T4.** Test (bước 04). Build và test ngay, gồm kiểm tra guardrail chất lượng.
- **P3-T5.** Đo lại (bước 05). Chờ đủ cửa sổ đo và đủ mẫu. Chạy checklist hợp lệ trước khi tin số. Nếu cặp so sánh không hợp lệ, tìm đúng cặp rồi đo lại.
- **P3-T6.** Quyết định (bước 06). So với ngưỡng đã chốt ở A1: GIỮ, SỬA 1 PHẦN hoặc REVERT. REVERT thì ghi lý do vào `tasks.md` và kho bài học.
- **P3-T7.** Report (bước 07). Ba loại: xong thật, đơn giản hóa có lý do, còn thiếu.
- **P3-T8.** Rollout (bước 08). Bật dần, mỗi nấc có đường lùi và theo dõi đúng các metric A1.
- **P3-T9.** Retrospective. Mẫu nào thừa, bước nào thiếu, thời gian thực tế so với ước lượng.

**Đầu ra:** một vòng hoàn chỉnh có số đo trước và sau, report ba loại, mục mới trong kho bài học, danh sách điều chỉnh quy trình.
**Tiêu chí xong:** có quyết định dựa trên số đo hợp lệ. Nếu kết quả là REVERT mà có ghi lý do đầy đủ thì vẫn đạt, vì quy trình đã làm đúng việc của nó.
**Đường lùi:** mỗi phase có thể lùi độc lập; với thay đổi config thì đưa về giá trị cũ ghi trong snapshot.

---

### Phase 4: Lane B chế độ quan sát
**Mục tiêu:** kiểm tra khả năng tự phát hiện của hệ thống mà chưa đề xuất gì, để đo độ tin cậy trước khi cho nó nói.
**Công việc:**
- **P4-T1.** Viết policy. Tiêu chí và guardrail mặc định, bậc rủi ro tối đa được tự đề xuất (giai đoạn đầu: config và prompt), ngân sách quét.
- **P4-T2.** Feature registry. Danh sách feature, fingerprint, step, liên kết tới Business Rule Card.
- **P4-T3.** Quét tự động. Chạy theo lịch, truy vấn Loki, nhóm theo fingerprint, làm sạch mẫu, phân rã bottleneck.
- **P4-T4.** Xếp hạng ứng viên. Tỷ trọng nhân tần suất chạy, kèm độ ổn định qua nhiều kỳ.
- **P4-T5.** Lọc báo động giả. Bottleneck phải lặp lại qua ít nhất N kỳ quét mới được coi là cấu trúc.
- **P4-T6.** Chống trùng bằng kho bài học. Loại ứng viên đã xử lý hoặc đã revert nếu không có điều kiện mới.
- **P4-T7.** Chạy shadow 2 tuần. Chỉ ghi kết quả, không gửi cho ai.
- **P4-T8.** Đối chiếu với Lane A. Lane B có tìm lại được các bottleneck mà Lane A đã xác định không? Baseline tự lấy có khớp baseline thủ công không?

**Đầu ra:** policy, registry, job quét, báo cáo đối chiếu A và B.
**Tiêu chí xong:** tìm lại được các bottleneck đã biết từ Lane A; baseline tự lấy lệch baseline thủ công trong biên đã định; báo động giả ở mức chấp nhận được.
**Đường lùi:** tắt job quét. Không có tác động tới hệ thống thật.

---

### Phase 5: Lane B đề xuất mức config
**Mục tiêu:** cho B2 đề xuất, người duyệt từng đề xuất, và thu số liệu về chất lượng của chính Lane B.
**Công việc:**
- **P5-T1.** Sinh đề xuất. Truy nguyên nhân, phân loại bằng chứng, sinh solution mức config theo schema chung.
- **P5-T2.** Tự phê bình. Kiểm tra vi phạm guardrail, mâu thuẫn dữ liệu, trùng bài học cũ. Thiếu đường lùi thì không được gửi.
- **P5-T3.** Độ tin cậy. Cao khi có bằng chứng trực tiếp, thấp khi suy luận gián tiếp.
- **P5-T4.** Đóng gói để duyệt. Vấn đề, đề xuất, đánh đổi, bằng chứng có liên kết, quyết định cần người đưa ra.
- **P5-T5.** Giới hạn số lượng. Số đề xuất tối đa mỗi kỳ, xếp theo giá trị, để tránh duyệt theo quán tính.
- **P5-T6.** Quy trình duyệt. Ai duyệt, thời hạn, cách từ chối kèm lý do (lý do từ chối cũng vào kho bài học).
- **P5-T7.** Chạy 2 đến 3 kỳ. Đề xuất được duyệt đi vào §2 như bình thường.
- **P5-T8.** Thu số liệu. Tỷ lệ đề xuất được duyệt, tỷ lệ được giữ sau khi đo lại, tỷ lệ revert, số lần vi phạm guardrail.

**Đầu ra:** các đề xuất đã đi qua §2, báo cáo chất lượng Lane B.
**Tiêu chí xong:** hoàn thành 2 đến 3 kỳ; có số liệu để quyết định nới quyền hay không; không có thay đổi nào được áp dụng mà không qua người duyệt.
**Đường lùi:** tắt B2, Lane B quay về chế độ quan sát; các thay đổi đã áp dụng lùi theo đường lùi của từng solution.

---

### Phase 6: Đối chiếu, nới quyền và mở rộng
**Mục tiêu:** mở rộng có kiểm soát, mỗi lần nới quyền đều dựa trên số liệu.
**Công việc:**
- **P6-T1.** So sánh A với B trên một số feature: Lane B bỏ sót gì, đề xuất sai gì, tốt hơn ở đâu.
- **P6-T2.** Quy tắc nới quyền. Chỉ nới từ config lên prompt khi tỷ lệ đề xuất đúng đủ cao qua nhiều kỳ, tỷ lệ revert thấp, chưa có vi phạm guardrail. Ngưỡng cụ thể do chủ chương trình chốt trước.
- **P6-T3.** Mở rộng feature theo đợt. Mỗi feature mới cần Business Rule Card, fingerprint và domain owner trước khi vào registry.
- **P6-T4.** Rà soát định kỳ. Policy, ngưỡng, kho bài học, mẫu tài liệu mỗi quý.

**Tiêu chí xong:** liên tục; mỗi lần nới quyền hoặc mở rộng có một quyết định được ghi lại, kèm số liệu.

---

## 6. Lịch dự kiến

| Tuần | Hoạt động chính |
|---|---|
| 1 | Phase 0 (3 ngày), bắt đầu Phase 1 |
| 2 | Hoàn tất Phase 1 |
| 3 đến 4 | Phase 2 (Lane A trên feature thí điểm) |
| 5 đến 6 | Phase 3 (vòng §2 đầu tiên, gồm thời gian chờ đủ dữ liệu để đo lại) |
| 5 đến 6 | Phase 4 chạy song song nếu đủ người (chỉ đọc log) |
| 7 đến 8 | Hoàn tất Phase 4, đối chiếu với Lane A |
| 9 đến 10 | Phase 5 (Lane B đề xuất, người duyệt) |
| 11 trở đi | Phase 6 (nới quyền, mở rộng) |

---

## 7. Điểm quyết định (go/no-go)

| Sau | Câu hỏi | Người quyết |
|---|---|---|
| **Phase 0** | Feature thí điểm nào? Có cần bổ sung log trước không? | Chủ chương trình |
| **Phase 2** | Danh sách solution đủ tin cậy để thử thay đổi thật không? | Chủ chương trình, domain owner |
| **Phase 3** | Quy trình §2 chạy ổn chưa, có bật Lane B đề xuất không? | Chủ chương trình |
| **Phase 5** | Có nới Lane B lên mức prompt không? | Chủ chương trình, người duyệt |

---

## 8. Chỉ số theo dõi

### Chỉ số quy trình
- Tỷ lệ baseline đạt đủ mẫu và qua Cổng 2.
- Tỷ lệ phép so sánh bị loại vì không hợp lệ (số cao nghĩa là fingerprint hoặc quy ước chưa tốt).
- Thời gian từ yêu cầu đến có solution (Lane A) và từ phát hiện đến có đề xuất (Lane B).

### Chỉ số chất lượng Lane B
- Tỷ lệ đề xuất được duyệt.
- Tỷ lệ được giữ sau khi đo lại, và tỷ lệ revert.
- Tỷ lệ báo động giả của B1.
- Số lần đề xuất vi phạm guardrail (mục tiêu là 0).

### Chỉ số kết quả
- Mức cải thiện thực đo so với khoảng kỳ vọng trong solution card (để hiệu chỉnh khả năng ước lượng).
- Mức cải thiện trên tiêu chí mục tiêu của A1 và việc guardrail có được giữ không.

---

## 9. Quản lý rủi ro

| Rủi ro | Khả năng | Tác động | Giảm thiểu |
|---|---|---|---|
| Log thiếu field cần thiết | Trung bình | Cao | Phase 0 phát hiện sớm, bổ sung log trước khi đo |
| So sánh sai khác feature hoặc khác độ phức tạp rule | Trung bình | Cao | Fingerprint bắt buộc, checklist hợp lệ ở bước 05 |
| Baseline nhiễm sự cố hoặc tải bất thường | Trung bình | Cao | Quy tắc loại sự cố, khoảng thời gian chuẩn, báo phân phối |
| Feature thí điểm quá phức tạp | Thấp | Trung bình | Chọn feature theo tiêu chí P0-T1 |
| Lane B hiểu sai nghiệp vụ nên đề xuất làm giảm chất lượng | Trung bình | Cao | Business Rule Card, guardrail, chỉ mức config ban đầu, domain owner review |
| Người duyệt bấm đồng ý hàng loạt | Trung bình | Trung bình | Giới hạn số đề xuất mỗi kỳ, gắn độ tin cậy, kiểm tra chọn mẫu |
| Gộp nhiều thay đổi nên không biết nguyên nhân khi có lỗi | Trung bình | Cao | Một phase một biến, một phase một lần sửa |
| Thư viện solution thành đáp án có sẵn, bỏ qua xác minh | Thấp | Trung bình | Mỗi lần dùng lại vẫn bắt buộc có bằng chứng từ dữ liệu mới |
| Form A1 quá nặng nên bị bỏ qua | Trung bình | Thấp | Chỉ vài trường bắt buộc |
| Ước lượng thời gian sai | Cao | Thấp | Ước lượng lại sau Phase 0 và sau Phase 3 |

---

## 10. Tài liệu và quản trị thay đổi

- **`tasks.md`:** ghi mã công việc, trạng thái, bằng chứng, và mọi lý do revert. Cập nhật ngay khi có thay đổi, không dồn lại cuối.
- **Report ba loại ở mỗi vòng:** xong thật, đơn giản hóa có lý do, còn thiếu.
- **Kho bài học:** mỗi vòng thêm một mục; Lane B tra trước khi đề xuất.
- **Thay đổi schema hoặc mẫu:** ghi phiên bản và lý do, để dữ liệu cũ vẫn đọc được.
- **Đường lùi cho mọi thay đổi được ghi trước khi implement**, không đợi đến lúc cần.

---

## 11. Việc cần bạn xác nhận để bắt đầu

1. Feature nào làm thí điểm, và ai là domain owner của nó?
2. Loki hiện có những label và field nào cho feature đó (đặc biệt thời gian từng step và token từng prompt)?
3. Tiêu chí ưu tiên của feature thí điểm là gì (thời gian, token, chất lượng) và guardrail nào không được vi phạm?
4. Ai là người duyệt đề xuất của Lane B?
5. Đội có thể dành bao nhiêu người cho chương trình, để quyết định chạy song song Phase 3 và Phase 4 hay tuần tự?
