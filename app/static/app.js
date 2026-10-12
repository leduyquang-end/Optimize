const state = { prepare: null, brief: null, briefList: [], lane: null };

const $ = (id) => document.getElementById(id);

function esc(text) {
  return String(text == null ? "" : text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function errorText(data) {
  if (!data) return "Lỗi không rõ.";
  if (data.detail && typeof data.detail === "object") {
    if (data.detail.error) return data.detail.error;
    if (Array.isArray(data.detail)) {
      return data.detail.map((d) => `${d.loc ? d.loc.join(".") : ""}: ${d.msg}`).join("\n");
    }
    if (data.detail.reasons) return data.detail.reasons.join("\n");
    return JSON.stringify(data.detail, null, 2);
  }
  if (typeof data.detail === "string") return data.detail;
  return JSON.stringify(data, null, 2);
}

function setSourceError(text) {
  const box = $("sourceError");
  if (!text) { box.hidden = true; box.textContent = ""; return; }
  box.hidden = false;
  box.textContent = text;
}

// --------------------------------------------------------------- ① nguồn ---
async function loadFromPath() {
  const path = $("pathInput").value.trim();
  if (!path) { setSourceError("Hãy nhập đường dẫn folder."); return; }
  setSourceError("");
  $("btnPath").disabled = true;
  try {
    const name = $("nameInput").value.trim();
    const res = await fetch("/api/v1/optimize/sources/from-path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, name: name || null }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { setSourceError(errorText(data)); return; }
    applyPrepare(data);
  } finally {
    $("btnPath").disabled = false;
  }
}

async function loadFromFiles(fileList, keepStructure) {
  const files = Array.from(fileList || []);
  if (!files.length) { setSourceError("Chưa chọn file nào."); return; }
  setSourceError("");

  const fd = new FormData();
  if (keepStructure) {
    fd.append("paths", JSON.stringify(files.map((f) => f.webkitRelativePath || f.name)));
  }
  files.forEach((f) => fd.append("files", f, f.name));

  try {
    const res = await fetch("/api/v1/optimize/sources/upload", { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { setSourceError(errorText(data)); return; }
    applyPrepare(data);
  } catch (err) {
    setSourceError(String(err));
  }
}

function applyPrepare(prepare) {
  state.prepare = prepare;
  setSourceError("");

  const src = prepare.source;
  const scripts = prepare.scripts || [];
  const info = $("sourceInfo");
  info.hidden = false;
  info.innerHTML = `
    <div><strong>${esc(src.name)}</strong>
      <span class="badge blue">${esc(src.kind)}</span>
      <span class="badge ${prepare.mode === "recorded" ? "green" : "amber"}">mode: ${esc(prepare.mode)}</span>
    </div>
    <div class="note">Nguồn: ${esc(src.source_id)} — ${esc(src.folder)}</div>
    <div class="note">Số đo sẵn trong folder: ${prepare.runs_available} · Script thấy được: ${scripts.length}</div>
    ${scripts.length ? `<div class="note">Script: ${scripts.map((s) => esc(s.relative_path)).join(", ")}</div>` : ""}
  `;

  buildCommandSelect(prepare);
  if (!$("briefFeature").value) {
    $("briefFeature").value = prepare.suggested_feature || prepare.source.name;
  }
  const prepNotes = (prepare.notes || [])
    .map((n) => `<div class="note">⚠ ${esc(n)}</div>`)
    .join("");
  if (prepNotes) info.innerHTML += prepNotes;
  $("step-pick").hidden = false;
  $("result").hidden = true;
  refreshBriefList();
  applyLane();
}

// ---------------------------------------------------------------- ② lane ---
function pickLane(lane) {
  state.lane = lane;
  applyLane();
}

function applyLane() {
  const lane = state.lane;
  $("btnPickA").classList.toggle("primary", lane === "A");
  $("btnPickB").classList.toggle("primary", lane === "B");
  const status = $("pickStatus");
  if (lane) {
    status.hidden = false;
    status.innerHTML = `Đã chọn <span class="badge blue">Lane ${lane}</span> — đi tiếp các bước bên dưới.`;
  } else {
    status.hidden = true;
  }
  // Brief chỉ bắt đầu hiện ra khi chọn Lane A; Lane B thì bỏ qua khối này
  $("step-brief").hidden = lane !== "A";
  $("step-run").hidden = !lane;
  $("step-lane").hidden = !lane;
  if (lane) {
    $("btnRun").textContent = `Chạy Lane ${lane}`;
    $("runLaneBadge").innerHTML = `<span class="badge blue">Lane ${lane}</span>`;
    $("step-run").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

// ---------------------------------------------------------------- ② brief --
function addObjectiveRow(data) {
  const row = document.createElement("div");
  row.className = "row obj-row";
  row.innerHTML = `
    <input type="text" class="obj-metric" placeholder="Chỉ số muốn cải thiện — VD: latency_p50_ms" />
    <input type="text" class="obj-unit" placeholder="Đơn vị — VD: ms" />
    <select class="obj-direction">
      <option value="decrease">giảm (decrease)</option>
      <option value="increase">tăng (increase)</option>
    </select>
    <input type="number" class="obj-target" placeholder="Mức muốn tới — VD: 200" step="any" />
    <input type="text" class="obj-source" placeholder="Lấy số từ đâu — VD: bench_chat.py (STEP classify/retrieve)" />
    <input type="number" class="obj-priority" placeholder="Ưu tiên" title="1 = cao nhất; 2 mục tiêu trái chiều phải khác số" />
    <button type="button" class="small obj-del" title="Xóa mục tiêu này">×</button>`;
  row.querySelector(".obj-del").addEventListener("click", () => row.remove());
  row.addEventListener("input", updateBriefPreview);
  row.addEventListener("change", updateBriefPreview);
  if (data) {
    row.querySelector(".obj-metric").value = data.metric_name || "";
    row.querySelector(".obj-unit").value = data.unit || "";
    row.querySelector(".obj-direction").value = data.direction || "decrease";
    row.querySelector(".obj-target").value = data.target_value != null ? data.target_value : "";
    row.querySelector(".obj-source").value = data.measurement_source || "";
    row.querySelector(".obj-priority").value = data.priority != null ? data.priority : 1;
  } else {
    row.querySelector(".obj-priority").value = 1;
  }
  $("objList").appendChild(row);
}

function addGuardrailRow(data) {
  const row = document.createElement("div");
  row.className = "row gr-row";
  row.innerHTML = `
    <input type="text" class="gr-metric" placeholder="Chỉ số bị chặn — VD: quality_score" />
    <input type="number" class="gr-pct" placeholder="Giới hạn giảm tối đa % — VD: 2" step="any" />
    <label class="filebtn hard-check"><input type="checkbox" class="gr-hard" /> hard — ranh giới đỏ, vượt là dừng</label>
    <button type="button" class="small gr-del" title="Xóa ràng buộc này">×</button>`;
  row.querySelector(".gr-del").addEventListener("click", () => row.remove());
  row.addEventListener("input", updateBriefPreview);
  row.addEventListener("change", updateBriefPreview);
  if (data) {
    row.querySelector(".gr-metric").value = data.metric_name || "";
    row.querySelector(".gr-pct").value = data.max_allowed_change_pct != null ? data.max_allowed_change_pct : "";
    row.querySelector(".gr-hard").checked = !!data.hard;
  } else {
    row.querySelector(".gr-hard").checked = true;
  }
  $("grList").appendChild(row);
}

function lines(id) {
  return $(id).value
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

function buildBriefPayload() {
  const targets = Array.from(document.querySelectorAll("#objList .obj-row"))
    .map((row) => ({
      metric_name: row.querySelector(".obj-metric").value.trim(),
      unit: row.querySelector(".obj-unit").value.trim(),
      direction: row.querySelector(".obj-direction").value,
      target_value: parseFloat(row.querySelector(".obj-target").value),
      measurement_source: row.querySelector(".obj-source").value.trim(),
      priority: parseInt(row.querySelector(".obj-priority").value || "1", 10),
    }))
    .filter((t) => t.metric_name);

  const guardrails = Array.from(document.querySelectorAll("#grList .gr-row"))
    .map((row) => ({
      metric_name: row.querySelector(".gr-metric").value.trim(),
      max_allowed_change_pct: parseFloat(row.querySelector(".gr-pct").value || "0"),
      hard: row.querySelector(".gr-hard").checked,
    }))
    .filter((g) => g.metric_name);

  const card = $("bizCard").value.trim();
  return {
    feature_id: $("briefFeature").value.trim(),
    optimization_targets: targets,
    guardrails: guardrails,
    thresholds: {
      keep_improvement_pct: parseFloat($("thrKeep").value || "0"),
      revert_improvement_pct: parseFloat($("thrRevert").value || "0"),
    },
    max_risk_tier: $("briefRisk").value,
    scope_in: lines("scopeIn"),
    scope_out: lines("scopeOut"),
    business_context: $("bizContext").value.trim(),
    business_rule_card: card || null,
    business_rule_card_confirmed: $("bizConfirm").checked,
    data_gaps: lines("dataGaps"),
  };
}

function updateBriefPreview() {
  const pre = $("briefPreview");
  if (!pre) return;
  try {
    pre.textContent = JSON.stringify(buildBriefPayload(), null, 2);
  } catch (err) {
    pre.textContent = `(${err})`;
  }
}

function fillBriefExample() {
  $("briefFeature").value = "chatbot_rag_v2";
  $("objList").innerHTML = "";
  addObjectiveRow({
    metric_name: "latency_p50_ms",
    unit: "ms",
    direction: "decrease",
    target_value: 200,
    measurement_source: "bench_chat.py — dòng STEP classify + STEP retrieve (self-loop --repeat 30)",
    priority: 1,
  });
  $("grList").innerHTML = "";
  addGuardrailRow({ metric_name: "quality_score", max_allowed_change_pct: 2, hard: true });
  $("thrKeep").value = 25;
  $("thrRevert").value = 10;
  $("briefRisk").value = "config";
  $("scopeIn").value = "retrieve (mmr, k=5)\nclassify (svm)";
  $("scopeOut").value = "model selection\ninfra / hạ tầng";
  $("bizContext").value =
    "Sinh viên phản hồi chatbot trả lời chậm khi hỏi học phí giờ cao điểm; " +
    "cần p50 dưới 200ms mà chất lượng trả lời không được giảm quá 2%.";
  $("bizCard").value = "optimization_data/registry/cards/Feature_X_v2.md";
  $("bizConfirm").checked = false; // domain owner phải tự xác nhận sau khi đọc thẻ
  $("dataGaps").value = "chưa log độ trễ phía LLM";
  updateBriefPreview();
}

function clearBriefForm() {
  $("briefFeature").value = "";
  $("objList").innerHTML = "";
  addObjectiveRow();
  $("grList").innerHTML = "";
  addGuardrailRow();
  $("thrKeep").value = 25;
  $("thrRevert").value = 10;
  $("briefRisk").value = "config";
  $("scopeIn").value = "";
  $("scopeOut").value = "";
  $("bizContext").value = "";
  $("bizCard").value = "";
  $("bizConfirm").checked = false;
  $("dataGaps").value = "";
  updateBriefPreview();
}

const GATE1_GLOSS = {
  "A1-V1": "Mỗi Brief chỉ nói về đúng 1 feature — kiểm tra ô “Tên feature” ở mục 1.",
  "A1-V2": "Mục tiêu cần: con số mục tiêu > 0, đơn vị, hướng (giảm/tăng) và nơi lấy số đo — xem mục 2.",
  "A1-V3": "Cần ít nhất 1 ràng buộc mức hard (tick “ranh giới đỏ” ở mục 3).",
  "A1-V4": "Ngưỡng “giữ” phải lớn hơn ngưỡng “hoàn lại”, cả hai > 0 — xem mục 4.",
  "A1-V5": "Hai mục tiêu cùng chỉ số nhưng hướng trái chiều cần mức Ưu tiên khác nhau.",
  "A1-V6": "Thiếu bối cảnh, thiếu đường dẫn Business Rule Card, hoặc chưa tick xác nhận của domain owner — xem mục 5–6.",
};

function glossGate1(errorTextLine) {
  const match = String(errorTextLine).match(/A1-V\d/);
  const gloss = match ? GATE1_GLOSS[match[0]] : "";
  return gloss ? `<div class="field-hint">${esc(gloss)}</div>` : "";
}

function fillBriefForm(brief) {
  state.brief = brief.status === "validated" ? { brief_id: brief.brief_id } : null;
  $("briefFeature").value = brief.feature_id || "";
  $("objList").innerHTML = "";
  (brief.optimization_targets || []).forEach(addObjectiveRow);
  if (!(brief.optimization_targets || []).length) addObjectiveRow();
  $("grList").innerHTML = "";
  (brief.guardrails || []).forEach(addGuardrailRow);
  if (!(brief.guardrails || []).length) addGuardrailRow();
  $("thrKeep").value = (brief.thresholds || {}).keep_improvement_pct != null ? brief.thresholds.keep_improvement_pct : 25;
  $("thrRevert").value = (brief.thresholds || {}).revert_improvement_pct != null ? brief.thresholds.revert_improvement_pct : 10;
  $("briefRisk").value = brief.max_risk_tier || "config";
  $("scopeIn").value = (brief.scope_in || []).join("\n");
  $("scopeOut").value = (brief.scope_out || []).join("\n");
  $("bizContext").value = brief.business_context || "";
  $("bizCard").value = brief.business_rule_card || "";
  $("bizConfirm").checked = !!brief.business_rule_card_confirmed;
  $("dataGaps").value = (brief.data_gaps || []).join("\n");
  showBriefStatus(brief);
}

function showBriefStatus(brief) {
  const el = $("briefStatus");
  $("briefErrors").hidden = true;
  if (brief && brief.status === "validated") {
    el.innerHTML = `<span class="badge green">Brief ${esc(brief.brief_id)} đã qua Cổng 1</span>`;
    state.brief = { brief_id: brief.brief_id };
  } else {
    el.innerHTML = `<span class="badge amber">Brief chưa qua Cổng 1</span>`;
    if (!brief || !brief.brief_id) state.brief = null;
  }
}

async function saveBrief() {
  const payload = buildBriefPayload();
  $("btnBrief").disabled = true;
  try {
    const res = await fetch("/api/v1/lane-a/brief", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      state.brief = null;
      const errors = (data.detail && data.detail.errors) || [errorText(data)];
      const box = $("briefErrors");
      box.hidden = false;
      box.innerHTML = errors
        .map((e) => `<div>${esc(e)}${glossGate1(e)}</div>`)
        .join("");
      $("briefStatus").innerHTML = '<span class="badge red">Cổng 1 chưa qua</span>';
      return;
    }
    state.brief = { brief_id: data.brief_id };
    showBriefStatus({ brief_id: data.brief_id, status: "validated" });
    refreshBriefList(data.brief_id);
  } catch (err) {
    setSourceError(String(err));
  } finally {
    $("btnBrief").disabled = false;
  }
}

async function refreshBriefList(preselect) {
  try {
    const res = await fetch("/api/v1/lane-a/briefs");
    const data = await res.json().catch(() => ({ briefs: [] }));
    state.briefList = data.briefs || [];
    const select = $("briefSelect");
    const current = preselect || select.value;
    select.innerHTML = '<option value="">— chọn brief cũ —</option>';
    state.briefList.forEach((b) => {
      select.appendChild(new Option(`${b.brief_id} — ${b.feature_id}`, b.brief_id));
    });
    if (current) select.value = current;
  } catch (err) {
    /* danh sách brief lỗi không chặn thao tác khác */
  }
}

function buildCommandSelect(prepare) {
  const select = $("cmdSelect");
  select.innerHTML = "";
  const runs = prepare.runs_available || 0;
  const scripts = prepare.scripts || [];

  if (runs > 0) {
    select.appendChild(new Option(`Dùng ${runs} số đo có sẵn trong folder (không chạy gì)`, "recorded"));
  }
  scripts.forEach((s, i) => {
    select.appendChild(new Option(`Chạy: python ${s.relative_path}`, `script:${i}`));
  });
  select.appendChild(new Option("Tự gõ lệnh…", "custom"));

  if (runs > 0) select.value = "recorded";
  else if (scripts.length) select.value = "script:0";
  else select.value = "custom";

  if (prepare.suggested_command) {
    $("customCmd").value = prepare.suggested_command.join(" ");
  }
  onCommandChange();
}

function onCommandChange() {
  const value = $("cmdSelect").value;
  $("customRow").hidden = value !== "custom";
  const hint = $("modeHint");
  if (value === "recorded") {
    hint.textContent = "Sẽ dùng trực tiếp số đo đã có trong folder; không phát sinh số liệu mới.";
  } else if (value === "custom") {
    hint.textContent = "Lệnh chỉ được chạy trong folder đã chọn; đường dẫn thoát ra ngoài sẽ bị từ chối.";
  } else {
    hint.textContent =
      "Mỗi lần lặp ghi 1 run: wall clock + workload_ms (tổng dòng 'STEP <tên> <ms>'); " +
      "baseline lấy workload_ms nên thời gian khởi tạo model không làm phình số liệu. " +
      "Lần chạy đầu thường chậm (nạp model) — tăng Timeout nếu run đầu bị timeout.";
  }
}

function chosenCommand() {
  const value = $("cmdSelect").value;
  if (value === "recorded") return null;
  if (value === "custom") {
    const raw = $("customCmd").value.trim();
    if (!raw) throw new Error("Chưa nhập lệnh.");
    return raw.split(/\s+/);
  }
  const index = parseInt(value.split(":")[1], 10);
  const script = state.prepare.scripts[index];
  if (!script) throw new Error("Không tìm thấy script đã chọn.");
  return ["{python}", script.relative_path];
}

// ---------------------------------------------------------------- ④ lane ---
async function runLane() {
  if (!state.prepare) { setSourceError("Hãy nạp nguồn bài test trước."); return; }
  const lane = state.lane;
  if (!lane) { pickLaneHint(); return; }

  const body = { lane, source_id: state.prepare.source.source_id };
  if (lane === "A") {
    if (!state.brief) {
      renderError(
        "Lane A cần Optimization Brief đã qua Cổng 1 (A1). Hãy điền khối ③ Brief rồi bấm " +
          "'Kiểm tra & lưu Brief' trước khi chạy."
      );
      $("result").hidden = false;
      $("result").scrollIntoView({ behavior: "smooth" });
      return;
    }
    body.brief_id = state.brief.brief_id;
  }
  try {
    const command = chosenCommand();
    if (command) {
      body.run_benchmark = true;
      body.command = command;
      body.repeats = Math.max(1, parseInt($("repeatsInput").value || "5", 10) || 5);
      const timeout = parseFloat($("timeoutInput").value || "120");
      if (timeout > 0) body.timeout_s = Math.min(timeout, 1800);
      const preflight = parseFloat($("preflightInput").value || "120");
      if (Number.isFinite(preflight) && preflight >= 0) body.preflight_timeout_s = Math.min(preflight, 600);
      if ($("selfLoopInput").checked) body.self_loop = true;
    }
  } catch (err) {
    setSourceError(err.message);
    return;
  }
  const period = $("periodInput").value.trim();
  if (period) body.period = period;

  const buttons = [$("btnRun")];
  buttons.forEach((b) => (b.disabled = true));
  const result = $("result");
  const out = $("resultBody");
  result.hidden = false;
  out.innerHTML = "<p class='hint'>Đang chạy…</p>";
  result.scrollIntoView({ behavior: "smooth" });

  try {
    const res = await fetch("/api/v1/optimize/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 409) renderBlocked(data.detail);
    else if (!res.ok) renderError(errorText(data));
    else renderResult(data);
  } catch (err) {
    renderError(String(err));
  } finally {
    buttons.forEach((b) => (b.disabled = false));
  }
}

// --------------------------------------------------------------- render ----
function renderError(text) {
  $("resultBody").innerHTML = `<div class="error">${esc(text)}</div>`;
}

function renderBlocked(detail) {
  const reasons = (detail.reasons || []).map((r) => `<li>${esc(r)}</li>`).join("");
  const notes = (detail.notes || []).map((n) => `<p class="note">${esc(n)}</p>`).join("");
  const errors = (detail.errors || []).map((n) => `<p class="reason">${esc(n)}</p>`).join("");
  const fixes = (detail.blocked_fixes || []).map((f) => `
    <div class="preflight-diag">
      <p><strong>Chẩn đoán:</strong> ${esc(f.diagnosis)}</p>
      <p><strong>Cách fix:</strong> ${esc(f.fix)}</p>
    </div>`).join("");
  $("resultBody").innerHTML = `
    <p><span class="badge red">Bị chặn</span> Lane ${esc(detail.lane)} — feature
      <code>${esc(detail.feature_id)}</code></p>
    <div class="blocked"><ul>${reasons}</ul>${notes}${errors}</div>
    ${fixes}
    <p class="hint">Hệ thống không tự bỏ qua điều kiện; khắc phục lý do rồi chạy lại.</p>
  `;
}

function bottleneckRows(bottlenecks) {
  return bottlenecks
    .map((b) => {
      const pct = b.pct_of_total_time;
      return `<tr>
        <td>${esc(b.step_name)}</td>
        <td><div class="bar ${pct >= 25 ? "" : "warn"}"><span style="width:${Math.max(pct, 1)}%"></span></div>
            ${pct.toFixed(2)}%</td>
        <td>${esc(b.signals)}</td>
        <td>${b.p50_latency_ms}</td>
        <td>${b.p90_latency_ms}</td>
        <td>${b.p99_latency_ms}</td>
      </tr>`;
    })
    .join("");
}

function hypothesisCards(items) {
  return items
    .map((h) => {
      const gate = h.gate3 || { errors: [] };
      const evi = ((h.verified_root_cause || {}).evidence_log_lines || [])
        .map((line) => `<div class="evi">${esc(line)}</div>`)
        .join("");
      const errors = (gate.errors || []).map((e) => `<div class="reason">${esc(e)}</div>`).join("");
      const stepGuess = ((h.change || {}).variables || []).join(", ") || "?";
      const confirmBlock = h.confirmed_solution_id
        ? `<p class="note">Đã chốt biến <code>${esc(h.confirmed_variable || "")}</code> bởi
             ${esc(h.confirmed_by || "?")} → solution <strong>${esc(h.confirmed_solution_id)}</strong>.</p>`
        : `
          <div class="confirm-row">
            <input type="text" id="var-${esc(h.solution_id)}" style="min-width:180px"
              placeholder="Tên biến cấu hình (VD: TOP_K) — đoán theo bước: ${esc(stepGuess)}">
            <input type="text" id="rev-${esc(h.solution_id)}" style="min-width:120px"
              placeholder="Domain owner (tên người)">
            <button type="button" class="btn-confirm-hyp" data-id="${esc(h.solution_id)}">Xác nhận → Solution chính</button>
          </div>`;
      return `
        <div class="hypo">
          <h4>${esc(h.solution_id)}
            <span class="badge amber">chưa xác minh (hypothesis)</span>
            ${gate.passed ? '<span class="badge green">Cổng 3 qua</span>' : '<span class="badge red">Cổng 3 chưa qua</span>'}
          </h4>
          <div class="note">Tác động kỳ vọng: ${esc(h.expected_impact_range)} · Bước đang nghi: ${esc(stepGuess)}</div>
          <div>${esc((h.verified_root_cause || {}).statement || "")}</div>
          ${evi}${errors}${confirmBlock}
        </div>`;
    })
    .join("");
}

function wireConfirmButtons() {
  document.querySelectorAll(".btn-confirm-hyp").forEach((btn) => {
    btn.addEventListener("click", () => confirmHypothesis(btn.dataset.id));
  });
}

async function confirmHypothesis(hypId) {
  const variableInput = document.getElementById(`var-${hypId}`);
  const reviewerInput = document.getElementById(`rev-${hypId}`);
  const variable = ((variableInput && variableInput.value) || "").trim();
  if (!variable) {
    if (variableInput) {
      variableInput.style.borderColor = "#e11d48";
      variableInput.placeholder = "Bắt buộc: nhập đúng 1 tên biến cấu hình thật";
      variableInput.focus();
    }
    return;
  }
  const reviewer = ((reviewerInput && reviewerInput.value) || "").trim();
  const btn = document.querySelector(`.btn-confirm-hyp[data-id="${hypId}"]`);
  if (btn) { btn.disabled = true; btn.textContent = "Đang chốt…"; }
  try {
    const res = await fetch(`/api/v1/optimize/hypotheses/${encodeURIComponent(hypId)}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ variable, reviewer: reviewer || undefined }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      renderError(errorText(data));
      if (btn) { btn.disabled = false; btn.textContent = "Xác nhận → Solution chính"; }
      return;
    }
    if (btn) {
      const row = btn.closest(".confirm-row");
      const card = btn.closest(".hypo");
      if (card) {
        const badge = card.querySelector(".badge");
        if (badge) { badge.className = "badge green"; badge.textContent = `đã chốt → ${data.solution_id}`; }
      }
      if (row) {
        row.innerHTML = `<p class="note">Đã chốt biến <code>${esc(data.variable)}</code> bởi
          ${esc(data.reviewer)} → solution <strong>${esc(data.solution_id)}</strong>
          (Cổng 3: ${data.gate3.passed ? "qua" : "chưa qua"}).
          Chạy lại Lane A (dùng số đo đã có) để thấy trong mục "Solution chính thức".</p>`;
      }
    }
  } catch (err) {
    renderError(String(err));
    if (btn) { btn.disabled = false; btn.textContent = "Xác nhận → Solution chính"; }
  }
}

function renderResult(data) {
  const base = data.baseline || {};
  const bench = data.benchmark;
  const notes = (data.notes || []).map((n) => `<p class="note">${esc(n)}</p>`).join("");
  const errors = (data.errors || []).map((n) => `<p class="reason">${esc(n)}</p>`).join("");

  const gateChip = data.gate2_passed
    ? '<span class="badge green">Cổng 2 qua</span>'
    : data.gate2_passed === false
      ? '<span class="badge red">Cổng 2 chưa qua</span>'
      : "";

  const baselineHtml = base.total_p50_latency_ms
    ? `
      <table>
        <tr><th>Mẫu</th><th>p50 (ms)</th><th>p90 (ms)</th><th>p99 (ms)</th><th>Weak baseline</th></tr>
        <tr>
          <td>${base.sample_count}</td>
          <td>${base.total_p50_latency_ms}</td>
          <td>${base.total_p90_latency_ms}</td>
          <td>${base.total_p99_latency_ms}</td>
          <td>${base.is_weak_baseline ? '<span class="badge amber">có</span>' : "không"}</td>
        </tr>
      </table>`
    : "<p class='note'>Không có baseline.</p>";

  const bottleneckHtml = data.bottlenecks && data.bottlenecks.length
    ? `
      <table>
        <tr><th>Bước</th><th>Chiếm</th><th>Tín hiệu</th><th>p50</th><th>p90</th><th>p99</th></tr>
        ${bottleneckRows(data.bottlenecks)}
      </table>`
    : "<p class='note'>Không bước nào vượt tín hiệu bottleneck.</p>";

  const benchHtml = bench
    ? `<p class="note">Benchmark ${esc(bench.benchmark_id)}: ${bench.succeeded}/${bench.total} run thành công
        (fingerprint ${esc(bench.fingerprint)})${bench.steps_seen && bench.steps_seen.length ? `, bước đo được: ${esc(bench.steps_seen.join(", "))}` : ""}.</p>` +
      (bench.preflight
        ? `<p class="note">Preflight: ${bench.preflight.ok
            ? `<span class="badge green">OK</span> chạy thử ${(bench.preflight.duration_ms / 1000).toFixed(1)}s, bước: ${esc((bench.preflight.steps_seen || []).join(", ") || "?")}`
            : `<span class="badge red">fail</span> ${esc(bench.preflight.reason || "")}`}</p>` +
          (bench.preflight.diagnosis
            ? `<div class="preflight-diag"><p><strong>Chẩn đoán:</strong> ${esc(bench.preflight.diagnosis)}</p>` +
              (bench.preflight.fix ? `<p><strong>Cách fix:</strong> ${esc(bench.preflight.fix)}</p>` : "") +
              `</div>`
            : "")
        : "")
    : "";

  const solutionsHtml = data.solutions && data.solutions.length
    ? `<h3>Solution chính thức (${data.solutions.length})</h3><pre>${esc(JSON.stringify(data.solutions, null, 2))}</pre>`
    : "";

  const laneExtra = data.scan
    ? `<details><summary>Chi tiết scan (Lane B)</summary><pre>${esc(JSON.stringify(data.scan, null, 2))}</pre></details>`
    : "";
  const proposeExtra = data.propose
    ? `<details><summary>Chi tiết propose (Lane B)</summary><pre>${esc(JSON.stringify(data.propose, null, 2))}</pre></details>`
    : "";

  $("resultBody").innerHTML = `
    <p>
      <span class="badge blue">Lane ${esc(data.lane)}</span>
      ${gateChip}
      ${data.brief_id ? `<span class="badge green">Brief ${esc(data.brief_id)} qua Cổng 1</span>` : ""}
      feature <code>${esc(data.feature_id)}</code> · kỳ <code>${esc(data.period)}</code> ·
      ${data.runs_used} run · fingerprint <code>${esc(data.fingerprint || "-")}</code>
    </p>
    ${benchHtml}
    <h3>Baseline</h3>
    ${baselineHtml}
    <h3>Bottleneck</h3>
    ${bottleneckHtml}
    <h3>Hypothesis (chưa xác minh)</h3>
    ${(data.hypotheses && data.hypotheses.length) ? hypothesisCards(data.hypotheses) : "<p class='note'>Không có ứng viên nào.</p>"}
    ${solutionsHtml}
    ${laneExtra}${proposeExtra}
    ${errors}${notes}
  `;
  wireConfirmButtons();
  // hiện section §2 nếu có solution
  if ((data.solutions && data.solutions.length) || (data.hypotheses && data.hypotheses.length)) {
    loadSection2();
  }
}

// ---------------------------------------------------------------- wiring ---
function pickLaneHint() {
  const status = $("pickStatus");
  status.hidden = false;
  status.innerHTML = '<span class="badge amber">Hãy chọn Lane A hoặc Lane B ở bước ② trước.</span>';
  $("step-pick").scrollIntoView({ behavior: "smooth" });
}

// ------------------------------------------------------------- §2 helpers ---
const S2_STATUSES = ["proposed","ranked","planned","implementing","testing","measuring","decided","kept","reverted","reported","rolling_out","done"];

function statusBadge(s) {
  const colors = { proposed: "amber", ranked: "blue", planned: "blue", implementing: "amber", testing: "amber", measuring: "amber", decided: "blue", kept: "green", reverted: "red", reported: "green", rolling_out: "blue", done: "green" };
  return `<span class="badge ${colors[s] || "amber"}">${esc(s)}</span>`;
}

function renderSection2Solutions(solutions) {
  const el = $("section2Solutions");
  if (!solutions || !solutions.length) { el.innerHTML = "<p class='note'>Chưa có solution nào.</p>"; return; }
  el.innerHTML = "<h3>Solutions (" + solutions.length + ")</h3>" + solutions.map(s => `
    <div class="hypo" style="margin:8px 0;">
      <p><strong>${esc(s.solution_id)}</strong> ${statusBadge(s.status)} · lane ${esc(s.source_lane)} · risk ${esc(s.risk_tier)}</p>
      <p class="note">${esc(s.proposed_change || "")}</p>
      <p class="note">Impact: ${esc(s.expected_impact_range || "?")} · Effort: ${esc(s.effort_estimate || "?")} · Confidence: ${s.confidence_score}</p>
      ${s.status_history && s.status_history.length ? `<details><summary>Lịch sử</summary><pre>${esc(s.status_history.join("\n"))}</pre></details>` : ""}
    </div>`).join("");
  // fill datalist for status select
  const sel = $("statusTarget");
  sel.innerHTML = S2_STATUSES.map(s => `<option value="${s}">${s}</option>`).join("");
}

async function loadSection2() {
  try {
    const res = await fetch("/api/v1/section-2/solutions");
    if (res.ok) {
      const d = await res.json();
      renderSection2Solutions(d.solutions);
      $("step-section2").hidden = false;
    }
  } catch (_) {}
}

async function doRerank() {
  const out = $("rerankResult");
  out.textContent = "Đang rerank...";
  try {
    const res = await fetch("/api/v1/section-2/rerank", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
    const d = await res.json();
    if (!res.ok) { out.textContent = "Lỗi: " + JSON.stringify(d); return; }
    out.innerHTML = `<p>Ranked: ${(d.ranked || []).map(s => esc(s.solution_id)).join(", ") || "không có"}</p>` +
      `<p>Excluded: ${(d.excluded || []).map(e => esc(e.id) + " (" + esc(e.reason) + ")").join("; ") || "không có"}</p>`;
    loadSection2();
  } catch (e) { out.textContent = "Lỗi: " + e; }
}

async function doCreatePlan() {
  const out = $("planResult");
  const ids = $("planSolutionIds").value.split(",").map(s => s.trim()).filter(Boolean);
  if (!ids.length) { out.textContent = "Nhập ít nhất 1 solution ID."; return; }
  out.textContent = "Đang tạo plan...";
  try {
    const res = await fetch("/api/v1/section-2/plan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ solution_ids: ids, owner: $("planOwner").value || "AI Flow Engineer" }) });
    const d = await res.json();
    if (!res.ok) { out.textContent = "Lỗi: " + JSON.stringify(d); return; }
    out.innerHTML = `<p>Plan <code>${esc(d.solution_id)}</code> · ${d.phases.length} phase(s) · revision ${d.revision}</p>` +
      d.phases.map(p => `<p class="note">${esc(p.phase_id)}: ${esc(p.change_variable)} — ${esc(p.done_criteria)}</p>`).join("");
    loadSection2();
  } catch (e) { out.textContent = "Lỗi: " + e; }
}

async function doTransition() {
  const out = $("statusResult");
  const sid = $("statusSolutionId").value.trim();
  const target = $("statusTarget").value;
  if (!sid) { out.textContent = "Nhập Solution ID."; return; }
  out.textContent = "Đang chuyển...";
  try {
    const res = await fetch(`/api/v1/section-2/solutions/${encodeURIComponent(sid)}/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: target, actor: "ui" }) });
    const d = await res.json();
    if (!res.ok) { out.textContent = "Lỗi: " + JSON.stringify(d); return; }
    out.innerHTML = `<p>${esc(sid)} → ${statusBadge(d.status)}</p>`;
    loadSection2();
  } catch (e) { out.textContent = "Lỗi: " + e; }
}

async function doReport() {
  const out = $("reportResult");
  const sid = $("reportSolutionId").value.trim();
  if (!sid) { out.textContent = "Nhập Solution ID."; return; }
  out.textContent = "Đang verify & report...";
  const body = {
    solution_id: sid,
    snapshot_before: $("reportSnapBefore").value || "S-BASE",
    snapshot_after: $("reportSnapAfter").value || "S-RETEST",
    baseline_p50: parseFloat($("reportBaselineP50").value) || 100,
    retest_p50: parseFloat($("reportRetestP50").value) || 80,
    guardrail_breached: $("reportGuardrail").value === "true",
    validity: {
      v1_same_fingerprint: true, v2_same_business_complexity: true,
      v3_equivalent_conditions: true, v4_sufficient_sample_size: true,
      v5_single_variable_diff: true, v6_distribution_provided: true,
    },
  };
  try {
    const res = await fetch("/api/v1/section-2/report", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const d = await res.json();
    if (!res.ok) { out.textContent = "Lỗi: " + JSON.stringify(d); return; }
    const rr = d.retest_result || {};
    out.innerHTML = `<p>Quyết định: <strong>${esc(rr.decision)}</strong> · improvement ${rr.improvement_pct}%</p>` +
      `<p class="note">${esc(rr.reasoning || "")}</p>` +
      `<details><summary>Báo cáo Markdown</summary><pre>${esc(d.report_markdown || "")}</pre></details>`;
    loadSection2();
  } catch (e) { out.textContent = "Lỗi: " + e; }
}

async function doLoadPlans() {
  const out = $("plansList");
  out.textContent = "Đang tải...";
  try {
    const res = await fetch("/api/v1/section-2/plans");
    const d = await res.json();
    if (!res.ok) { out.textContent = "Lỗi: " + JSON.stringify(d); return; }
    const plans = d.plans || [];
    if (!plans.length) { out.innerHTML = "<p class='note'>Chưa có plan nào.</p>"; return; }
    out.innerHTML = plans.map(p => `
      <div class="hypo" style="margin:6px 0;">
        <p><strong>${esc(p.solution_id)}</strong> · ${p.phases.length} phase · rev ${p.revision}</p>
        ${p.phases.map(ph => `<p class="note">${esc(ph.phase_id)}: ${esc(ph.change_variable)} — keep ≥25%, revert &lt;10%</p>`).join("")}
      </div>`).join("");
  } catch (e) { out.textContent = "Lỗi: " + e; }
}

document.addEventListener("DOMContentLoaded", () => {
  $("btnPath").addEventListener("click", loadFromPath);
  $("pathInput").addEventListener("keydown", (e) => { if (e.key === "Enter") loadFromPath(); });
  $("folderInput").addEventListener("change", (e) => loadFromFiles(e.target.files, true));
  $("fileInput").addEventListener("change", (e) => loadFromFiles(e.target.files, false));
  $("btnPickA").addEventListener("click", () => pickLane("A"));
  $("btnPickB").addEventListener("click", () => pickLane("B"));
  $("btnAddObjective").addEventListener("click", () => addObjectiveRow());
  $("btnAddGuardrail").addEventListener("click", () => addGuardrailRow());
  $("btnBriefExample").addEventListener("click", fillBriefExample);
  $("btnBriefClear").addEventListener("click", clearBriefForm);
  $("step-brief").addEventListener("input", (e) => {
    if (e.target.closest(".obj-row, .gr-row")) return; // row đã tự cập nhật preview
    updateBriefPreview();
  });
  $("step-brief").addEventListener("change", (e) => {
    if (e.target.closest(".obj-row, .gr-row")) return;
    updateBriefPreview();
  });
  $("btnBrief").addEventListener("click", saveBrief);
  $("briefSelect").addEventListener("change", (e) => {
    const brief = state.briefList.find((b) => b.brief_id === e.target.value);
    if (brief) fillBriefForm(brief);
  });
  $("cmdSelect").addEventListener("change", onCommandChange);
  $("btnRun").addEventListener("click", () => runLane());

  // §2 wiring
  $("btnRerank").addEventListener("click", doRerank);
  $("btnCreatePlan").addEventListener("click", doCreatePlan);
  $("btnTransition").addEventListener("click", doTransition);
  $("btnReport").addEventListener("click", doReport);
  $("btnLoadPlans").addEventListener("click", doLoadPlans);
  loadSection2();

  addObjectiveRow();
  addGuardrailRow();
  refreshBriefList();
});
