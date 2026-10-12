# Business Rule Card: Feature_X_v2

> Trạng thái: **DRAFT - chờ domain owner xác nhận (P1-T2 / A1-V6).**
> Chưa xác nhận thì Lane A không qua Cổng 1, Lane B không được quét feature này.

## 1. Feature làm gì
- Tóm tắt một đoạn: feature xử lý đầu vào nào, trả về kết quả gì cho người dùng.

## 2. Quy tắc nào quyết định độ phức tạp
- rule_set / rule_variant đang chạy: `v2`
- Số bước subflow ảnh hưởng độ phức tạp: `6`
- Các biến thể chưa phân loại (nếu có): liệt kê rõ, feature có biến thể chưa phân loại thì không làm thí điểm.

## 3. Đầu vào và đầu ra
- Đầu vào: ...
- Đầu ra: ...

## 4. Ràng buộc không được vi phạm (guardrail nghiệp vụ)
- `quality_score` không được thấp hơn baseline.
- `error_rate` không được cao hơn baseline.
- Các step bắt buộc giữ nguyên (dùng cho B2-C6): ...

## 5. Xác nhận
| Vai trò | Người | Ngày xác nhận |
|---|---|---|
| Domain owner | PENDING_DOMAIN_OWNER | chưa xác nhận |
