# Optimization System - Modular Monolith Architecture (Python / FastAPI)

Nền tảng tối ưu hóa hiệu năng hệ thống tự động & thủ công (**Lane A** & **Lane B**) xây dựng theo kiến trúc **Modular Monolith (FastAPI / Pydantic v2)**, tuân thủ bộ quy tắc nghiệp vụ phiên bản mới nhất **v1.0**.

---

## 🤖 Hướng dẫn AI Agent (Agent Operational Guidelines)

- 🤖 **[agent.md - Hướng dẫn Vận hành cho AI Agent](file:///e:/Training/optimize/agent.md)**  
  *Quy định đọc/ghi, quyền tự chủ, định tuyến Lane A/B/§2, 10 điều tuyệt đối không làm & checklists trước phiên làm việc.*

---

## 📚 Bộ Tài liệu Chuẩn (V1 Latest Documentation Suite)

1. 🎨 **[Thiết kế Chi tiết Lane A: Yêu cầu Thủ công (v1.0)](file:///e:/Training/optimize/docs/01_LANE_A_DESIGN.md)**  
   *Mô hình dữ liệu JSON Brief/Baseline, Cổng 1 (A1-V1..V6), Cổng 2 (A2-V1..V6), Cổng 3 (A3-V1..V6) & LogQL queries mẫu.*

2. 🤖 **[Thiết kế Chi tiết Lane B: Hệ thống Tự phát hiện (v1.0)](file:///e:/Training/optimize/docs/02_LANE_B_DESIGN.md)**  
   *Policy & Feature Registry JSON, Cổng B1 (B1-V1..V6), Cổng B2 / Self-Criticism (B2-C1..C6), Score Ranker & Kill Switches.*

3. 🔄 **[Thiết kế Phần dùng chung & Quy trình §2 (v1.0)](file:///e:/Training/optimize/docs/03_SHARED_AND_SECTION_2_DESIGN.md)**  
   *Fingerprint (FP-1..4), Snapshot Store, SolutionCard Schema, Lesson Store, Checklist Hợp lệ (V-1..V-6) & 8 bước Re-rank ➔ Rollout.*

4. 📄 **[Tài liệu Quy trình & Quy tắc Nghiệp vụ (v1.0)](file:///e:/Training/optimize/docs/PROCESS_SPECIFICATION_V1.md)**  
   *Trích dẫn mã quy tắc: `A1-R1`..`A3-R7` (Lane A), `B0-R1`..`B2-R8` (Lane B), `S01-R1`..`S08-R3` (§2).*

5. 🗺️ **[Kế hoạch Triển khai Kỹ thuật Chi tiết (v1.0)](file:///e:/Training/optimize/docs/IMPLEMENTATION_PLAN_V1.md)**  
   *Theo dõi mã công việc: `P0-T1` đến `P6-T4`, Giả định, Ma trận rủi ro & Mẫu ghi vết `tasks.md`.*

---

## 📐 Cấu trúc Dự án (Modular Monolith Layout)

```
e:\Training\optimize
├── agent.md                    # Hướng dẫn quy trình vận hành dành riêng cho AI Agent
├── docs/                       # TÀI LIỆU CHUẨN V1 (MỚI NHẤT)
│   ├── agent.md                   # Bản sao lưu hướng dẫn agent
│   ├── 01_LANE_A_DESIGN.md        # Thiết kế chi tiết Lane A: Intake, Baseline, Solutions, Gates A1-A3
│   ├── 02_LANE_B_DESIGN.md        # Thiết kế chi tiết Lane B: Policy, Scanner, Proposer, Gates B1-B2
│   ├── 03_SHARED_AND_SECTION_2_DESIGN.md # Schema dùng chung (FP, Snapshot, SolutionCard) & Quy trình §2 (S01-S08)
│   ├── PROCESS_SPECIFICATION_V1.md # Quy trình & Mã quy tắc (A1-R1 -> S08-R3)
│   └── IMPLEMENTATION_PLAN_V1.md  # Kế hoạch thực thi theo Phase (P0-T1 -> P6-T4)
│
├── app/                        # DELIVERY / FASTAPI API GATEWAY
│   ├── main.py                 # FastAPI App & Swagger OpenAPI Gateway
│   ├── config.py               # Environment Configuration
│   └── api/                    # API Routers (Lane A, Lane B, Policy, Section 2)
│
├── src/                        # BOUNDED CONTEXTS & DOMAIN LOGIC
│   ├── core/                   # Shared Kernel (Adapters, Schemas, Events)
│   └── modules/                # Core Modules
│       ├── lane_a/             # Lane A: Brief (A1), Baseline (A2), Solutions (A3)
│       ├── lane_b/             # Lane B: Scanner (B1), Proposer & Self-Criticism (B2)
│       ├── policy_registry/    # System Policy & Guardrails (B0)
│       └── section_2/          # Decision & Verification Engine (S01 - S08)
│
└── tests/                      # AUTOMATED TEST SUITE
    └── unit/                   # Tests cho Gates & Verification Engine

├── optimization_data/          # KHO DỮ LIỆU VẬN HÀNH (FileStore)
│   ├── policy/policy.json         # Chính sách Lane B (B0-R1) — chủ chương trình duyệt
│   ├── registry/features.json     # Feature registry (mode, fingerprint, domain owner)
│   ├── registry/cards/*.md        # Business Rule Card (chỉ domain owner sửa)
│   ├── briefs/ snapshots/ solutions/ plans/ measurements/ reports/
│   ├── raw_runs/ sources/ uploads/  # Số đo đo được + nguồn bài test (path / upload)
│   ├── lessons/lessons.jsonl      # Kho bài học (append-only)
│   ├── queue/review/ observations/
│   └── ...
└── tasks.md                    # Tiến độ & lý do revert (agent.md 3.3)
```

---

## ⚡ Hướng dẫn Khởi chạy & Kiểm thử

1. **Kiểm thử Unit Tests:**
   ```bash
   python -m unittest discover -s tests -p "test_*.py"
   ```

2. **Khởi chạy API Server:**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   *Swagger UI xem tại:* `http://localhost:8000/docs`

---

## 🎯 App web: đưa folder vào → chọn lane → chạy test → chạy

1. **Mở app:** `http://localhost:8000/ui` (server chạy bằng `uvicorn app.main:app`).

2. **① Nguồn bài test** — 2 cách đưa vào:
   - Dán đường dẫn folder trên máy → `POST /api/v1/optimize/sources/from-path` (không copy dữ liệu).
   - Bấm *Chọn folder* / *Chọn file & zip* → `POST /api/v1/optimize/sources/upload` (multipart; trường `paths` là JSON array giữ cấu trúc thư mục) → lưu vào `optimization_data/uploads/<source_id>/`.
   - An toàn: chặn `..`/đĩa tuyệt đối, giới hạn 2000 file & 200MB; chỉ đọc trong folder đã chọn (không đụng `.env`, venv, cache).
   - Xem lại: `GET /api/v1/optimize/sources`, `GET /api/v1/optimize/sources/{id}`.

3. **② Chọn lane** — bấm *Chọn Lane A* hoặc *Chọn Lane B* (lựa lại được bất cứ lúc nào):
   - Chọn **Lane A** → khối **③ Brief** mới hiện ra (Lane B bỏ qua Brief, đi thẳng lấy số đo).

4. **③ Brief** — bắt buộc với Lane A (Cổng 1, `A1-V1..V6`); form được chia **7 khối hỏi – đáp bằng ngôn ngữ thường ngày** (không phải thuật ngữ):
   - mỗi khối có câu hỏi lớn (VD “tôi muốn cải thiện tới mức nào?”, “điều gì không được hỏng?”), dòng giải thích vì sao cần, ô điền có placeholder ví dụ thật; nút **“Điền ví dụ mẫu (chatbot RAG)”** điền sẵn một phiếu đầy đủ để đối chiếu, nút **“Xóa form”**, và mục **“Xem trước Brief sẽ lưu”** (JSON cập nhật realtime);
   - lỗi Cổng 1 (`A1-V1..V6`) giờ kèm **diễn giải tiếng Việt** ngay dưới dòng lỗi (mục nào thiếu, đi đâu mà sửa);
   - 1..n `optimization_target` (metric, unit, direction, target, **nguồn đo**, priority) + 1..n `guardrail` (cần ≥1 `hard` = “ranh giới đỏ”);
   - ngưỡng `keep_improvement_pct > revert_improvement_pct > 0`, bậc rủi ro tối đa, scope IN/OUT, business context, đường dẫn Business Rule Card + tick xác nhận của domain owner (UI không tick thay), data gaps (tuỳ chọn).
   - Bấm *Kiểm tra & lưu Brief* → `POST /api/v1/lane-a/brief` (201 = qua Cổng 1, kèm `brief_id`; 422 = `detail.errors` hiện đỏ kèm mã `A1-V2/A1-V3/A1-V4/A1-V6` + diễn giải); brief cũ chọn lại được ở dropdown `GET /api/v1/lane-a/briefs`.
   ```bash
   curl -X POST "http://localhost:8000/api/v1/lane-a/brief?base_dir=optimization_data" ^
        -H "Content-Type: application/json" ^
        -d "{\"feature_id\":\"Feature_X_v2_subflow6_prod\",\"optimization_targets\":[{\"metric_name\":\"latency_p50_ms\",\"unit\":\"ms\",\"direction\":\"decrease\",\"target_value\":40000,\"measurement_source\":\"loki:{app=\\\"x\\\"}\",\"priority\":1}],\"guardrails\":[{\"metric_name\":\"quality_score\",\"max_allowed_change_pct\":2,\"hard\":true}],\"thresholds\":{\"keep_improvement_pct\":25,\"revert_improvement_pct\":10},\"max_risk_tier\":\"prompt\",\"scope_in\":[\"subflow6\"],\"scope_out\":[\"model selection\"],\"business_context\":\"...\",\"business_rule_card\":\"optimization_data/registry/cards/Feature_X_v2.md\",\"business_rule_card_confirmed\":true,\"data_gaps\":[]}"
   ```

5. **④ Cách lấy số đo** — app quét folder rồi gợi ý (đổi được trước khi chạy):
   - có `runs.json|jsonl|csv` → *Dùng số đo có sẵn* (không chạy gì thêm);
   - có script `.py` → dropdown `python <script>`;
   - không có gì → tự gõ lệnh, ví dụ `{python} main.py --n 100` (`{python}` = phiên bản Python đang chạy).
   - Lệnh chỉ được trỏ vào **trong** folder đã chọn (thoát ra ngoài → 422); mỗi lần lặp ghi 1 run vào `optimization_data/raw_runs/<feature>/<period>.json`, dòng `STEP <tên> <ms>` được gộp thành từng bước.
   - Các ô: *Số lần lặp* (repeats), *Kỳ*, *Timeout (giây)/lần* (mặc định 120 — lần chạy đầu load model nặng nên đặt 300); script giống web server sẽ hiện ⚠ ngay khi nạp nguồn.
   - **Preflight** (mặc định `min(120, timeout_s)`, ô riêng, 0 = bỏ qua): chạy **thử 1 lần** trước khi đo đủ N lần — script exit≠0 / timeout / không in `STEP <tên> <ms>` → **dừng ngay** kèm lý do (không tốn N×timeout; smoke thật: web server fail mất 15s thay vì ~10 phút). Kết quả preflight hiện trong `benchmark.preflight` và dòng "Preflight: OK/fail" ở UI.
   - **Script đo dùng chung** `templates/bench_driver.py`: copy vào folder nguồn có `services/` + `core/`, sửa khối `STEP_SPECS` (tên module/hàm/argument) rồi chạy `{python} bench_driver.py --repeat 30` + tick "Script tự lặp" — import thẳng hàm (không web server → không treo), in `STEP`/`RUN` đúng contract; `--discover` liệt kê hàm đo được. Prepare tự nhắc khi folder có `services/` hoặc `core/`.
   - **Script tự lặp** (tick vào ô riêng): script tự lặp N vòng trong **1 process**, mỗi vòng in `STEP <tên> <ms>` rồi kết thúc bằng `RUN <ms>` (wall của vòng) → runner tách mỗi `RUN` thành 1 run. 30 mẫu chỉ tốn **1 lần khởi tạo** (~25s) thay vì 30 lần → `bench_chat.py --repeat 30`. Lệch `repeats` bị bỏ qua ở chế độ này.

6. **⑤ Chạy** — nút *Chạy Lane A* / *Chạy Lane B* (theo lane đã chọn ở ②; API: `POST /api/v1/optimize/run`):
   ```bash
   curl -X POST http://localhost:8000/api/v1/optimize/run -H "Content-Type: application/json" ^
        -d "{\"lane\":\"A\",\"source_id\":\"SRC-0001\",\"brief_id\":\"BR-2026-0001\",\"run_benchmark\":true,\"repeats\":30,\"timeout_s\":300,\"period\":\"2026-W41\"}"
   ```
   - **Lane A** → yêu cầu `brief_id` **đã qua Cổng 1**: thiếu → 409 kèm `reasons` (không chạy benchmark), không tồn tại → 404, brief chưa `validated` → 409; sau đó `baseline` (Cổng 2, mang `brief_id`) + bảng `bottlenecks` (share/long_tail) + `hypotheses` (chưa xác minh → **không** nằm trong `solutions`).
   - **Lane B** → kiểm tra điều kiện B0; thiếu policy/registry/card → **409** kèm `reasons`, hiện thẳng trên UI, không tự duyệt.
   - Chưa có số đo → 409 “Chưa có số đo”; hệ thống **không bịa** baseline.
   - **Số đo mỗi run**: `latency_ms` = wall clock (gồm khởi tạo process), `workload_ms` = tổng dòng `STEP` (chỉ phần workload). Baseline lấy `workload_ms` khi mọi run đều có (trộn kiểu đo → dùng wall clock và ghi `data_gaps`), nên nạp model ~25s không làm phình p50. Ở chế độ tự lặp, `latency_ms` = wall của từng vòng (do script đo), `workload_ms` = tổng STEP trong vòng.
   - **Run lỗi**: exit code/timeout được gộp thành `run r1,r2: exit code 1: <phần cuối stderr>` và hiện đỏ trong kết quả (409 cũng kèm `errors`). `timeout_s` chỉnh per-run (mặc định 120s; lần đầu cold-start nên để 300).
   - Script đo phải **chạy batch rồi thoát** (web server `app.run(` → báo ⚠ khi nạp nguồn) và in `STEP <tên> <ms>`; ví dụ có sẵn: `bench_chat.py` trong folder nguồn (mode `rag` local, mode `chat` cần Neo4j + Gemini).
   - Tham số API thêm: `self_loop: true` (script tự lặp) cùng `timeout_s`, `repeats`.
   - **Hypothesis**: ID dạng `HYP-xxxx` (tăng dần, lưu hồ sơ tại `optimization_data/hypotheses/<id>.json`), KHÔNG nằm trong `solutions/` — mỗi thẻ trong UI có ID riêng dù chạy lại nhiều lần (A3-V6).
   - **Chốt biến → Solution chính**: domain owner nhập tên 1 biến cấu hình thật (ô dưới thẻ hypothesis, hoặc `POST /api/v1/optimize/hypotheses/{id}/confirm` với `{"variable": "top_k", "reviewer": "mai"}`) → hệ thống kiểm lại Cổng 3, cấp ID `SOL-xxxx`, lưu `solutions/`. Chạy lại Lane A (dùng số đo đã có): solution hiện ở mục "Solution chính thức"; bước đã chốt không sinh hypothesis trùng.
   - **Số đo theo từng nguồn**: `raw_runs` lọc theo `config.source` — file của nguồn khác không bị dùng ngầm (có ghi chú rõ nếu file mới nhất thuộc nguồn khác). 0 run thành công → 409 kèm lý do (không im lặng). Lệnh gợi ý bỏ qua script web server (app.run/uvicorn...) và ưu tiên script có tên `bench*/measure*/perf*`.

7. **⑥ §2 — Triển khai & Xác minh solution** (hiện sau khi Lane A/B có solution): vòng lặp **Rerank → Plan → Implement (tay) → Test → Đo lại → Quyết định → Báo cáo → Rollout**.
   - **State machine §7**: `proposed → ranked → planned → implementing → testing → measuring → decided → kept/reverted → reported → rolling_out → done`. Chuyển sai trạng thái → **422** kèm danh sách trạng thái được phép. Lịch sử chuyển lưu trong `status_history`.
   - **Step 01 — Rerank** (`POST /api/v1/section-2/rerank`): xếp hạng lại theo impact rủi ro; loại over-ceiling / hypothesis chưa xác minh / conflict (S01-R1..R4). Solution được xếp → tự chuyển `ranked`.
   - **Step 02 — Plan** (`POST /api/v1/section-2/plan`): 1 solution → plan 1 phase; nhiều solution → multi-phase (config→prompt→code, `depends_on` chain). Mỗi phase có `done_criteria` (keep ≥25%, revert <10%), tests + guardrail, remeasure window/min_runs, rollback. Lưu `plans/<id>-plan.json`.
   - **Step 05+06+07 — Verify & Report** (`POST /api/v1/section-2/report`): nhập số đo trước/sau + V-1..V-6 → engine tính improvement %, quyết định KEEP/PARTIAL/REVERT/INVALID; KEEP → auto chuyển `kept`, REVERT → `reverted`. Báo cáo Markdown 3 phần (Xong thật / Đơn giản hóa / Còn thiếu) lưu `reports/R-*.md`.
   - **Chuyển trạng thái thủ công** (`POST /api/v1/section-2/solutions/{id}/status`): implement/test do người thực hiện, đánh dấu tiến độ qua API.
   - **Danh sách**: `GET /solutions`, `GET /plans`, `GET /plans/{id}`.
   - UI ⑥ hiển thị solution cards + status badge, form rerank/plan/transition/report, danh sách plans.

> Cơ chế khai báo `optimization_data/benchmarks/benchmark.json` đã bị xoá (xem `tasks.md` — `RM-BM`); mọi bài test giờ là một **nguồn (source)** tạo lúc chạy.
