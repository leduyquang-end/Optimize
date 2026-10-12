# parse_kg.py
import re

TUPLE_DELIMITER       = "<|>"
RECORD_DELIMITER      = "##"
COMPLETION_DELIMITER  = "<|COMPLETE|>"


# ══════════════════════════════════════════════════════════════
# 1. PARSE RAW LLM OUTPUT
# ══════════════════════════════════════════════════════════════

def parse_output(raw_output: str) -> tuple[list[dict], list[dict]]:
    """Parse raw output từ LLM thành entities và relationships."""

    if COMPLETION_DELIMITER in raw_output:
        raw_output = raw_output[:raw_output.index(COMPLETION_DELIMITER)]

    entities      = []
    relationships = []

    for record in raw_output.split(RECORD_DELIMITER):
        record = record.strip()
        if not record:
            continue

        record = re.sub(r'^\(', '',  record)
        record = re.sub(r'\)$', '', record.rstrip())

        fields      = [f.strip() for f in record.split(TUPLE_DELIMITER)]
        record_type = fields[0].strip('"').strip("'").lower() if fields else ""

        if record_type == "entity" and len(fields) >= 4:
            entities.append({
                "name":        fields[1].upper(),
                "type":        fields[2].upper(),
                "description": fields[3],
            })

        elif record_type == "relationship" and len(fields) >= 5:
            try:
                strength = float(fields[4])
            except ValueError:
                strength = 5.0
            relationships.append({
                "source":      fields[1].upper(),
                "target":      fields[2].upper(),
                "description": fields[3],
                "strength":    strength,
            })

    return entities, relationships


def parse_all(results: list[dict]) -> tuple[list[dict], list[dict]]:
    """Parse toàn bộ kết quả extraction từ tất cả chunk."""
    all_entities      = []
    all_relationships = []
    for r in results:
        e, rel = parse_output(r["raw_output"])
        all_entities.extend(e)
        all_relationships.extend(rel)
    return all_entities, all_relationships


# ══════════════════════════════════════════════════════════════
# 2. DEDUPLICATION — BƯỚC 1: EXACT MATCH TÊN
# ══════════════════════════════════════════════════════════════

def _exact_dedup(entities: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """
    Chuẩn hóa tên chữ hoa, gộp entity trùng tên, giữ description dài hơn.
    Trả về (danh sách đã gộp, bảng ánh xạ name → canonical_name).
    """
    seen:     dict[str, dict] = {}
    name_map: dict[str, str]  = {}

    for e in entities:
        name = e["name"]
        if name not in seen:
            seen[name] = dict(e)
        else:
            if len(e["description"]) > len(seen[name]["description"]):
                seen[name]["description"] = e["description"]
        name_map[name] = name   # self-mapping ban đầu

    return list(seen.values()), name_map


# ══════════════════════════════════════════════════════════════
# 3. DEDUPLICATION — BƯỚC 2: SEMANTIC MATCH
# ══════════════════════════════════════════════════════════════

def deduplicate_entities(
    entities: list[dict],
    similarity_threshold: float = 0.92,
) -> tuple[list[dict], dict[str, str]]:
    """
    Gộp entity trùng nghĩa qua 2 bước:

    Bước 1 – Khớp tên chính xác:
        Chuẩn hóa tên chữ hoa, gộp entity trùng tên, giữ description dài hơn.

    Bước 2 – Gộp theo ngữ nghĩa (vietnamese-bi-encoder):
        Mã hóa thực thể thành vector embedding.
        Với mỗi cặp cùng type, tính cosine similarity.
        Nếu similarity > threshold=0.92 → cùng ngữ nghĩa → gộp lại.
        Chọn entity có description dài hơn làm canonical.
        Chuyển toàn bộ quan hệ từ entity bị gộp sang canonical.
        Loại bỏ self-loop sau khi gộp.

    Trả về:
        (danh sách entity đã dedup, dict ánh xạ name → canonical_name)
    """
    # ── Bước 1: Exact ───────────────────────────────────────────────
    deduped, name_map = _exact_dedup(entities)

    if len(deduped) <= 1:
        return deduped, name_map

    # ── Bước 2: Semantic ────────────────────────────────────────────
    try:
        import numpy as np
        from langchain_huggingface import HuggingFaceEmbeddings

        _embed = HuggingFaceEmbeddings(
            model_name="bkai-foundation-models/vietnamese-bi-encoder",
            encode_kwargs={"normalize_embeddings": True, "batch_size": 32},
        )

        # Embed name + description để bắt cả tên và ngữ nghĩa
        texts = [f"{e['name']} {e['description']}" for e in deduped]
        vecs  = np.array(_embed.embed_documents(texts))   # (N, D) normalized

        sim_matrix = vecs @ vecs.T                         # cosine similarity (N, N)

        merged = [False] * len(deduped)
        result = []

        for i in range(len(deduped)):
            if merged[i]:
                continue

            canonical = dict(deduped[i])

            for j in range(i + 1, len(deduped)):
                if merged[j]:
                    continue
                # Chỉ so sánh cùng type để tránh gộp nhầm giữa loại khác nhau
                if deduped[i]["type"] != deduped[j]["type"]:
                    continue
                if sim_matrix[i, j] >= similarity_threshold:
                    # Chọn description dài hơn làm canonical
                    if len(deduped[j]["description"]) > len(canonical["description"]):
                        canonical["description"] = deduped[j]["description"]
                    # Ghi lại ánh xạ để remap relationship
                    name_map[deduped[j]["name"]] = canonical["name"]
                    merged[j] = True

            result.append(canonical)

        print(f"  Semantic dedup: {len(deduped)} → {len(result)} entities")
        return result, name_map

    except Exception as ex:
        print(f"  [WARN] Semantic dedup skipped: {ex}")
        return deduped, name_map


# ══════════════════════════════════════════════════════════════
# 4. REMAP + DEDUP RELATIONSHIPS
# ══════════════════════════════════════════════════════════════

def deduplicate_relationships(
    relationships: list[dict],
    name_map: dict[str, str],
    min_strength: float = 3.0,
) -> list[dict]:
    """
    Sau khi gộp entity:
    1. Remap source/target theo name_map (chuyển quan hệ từ entity bị gộp → canonical).
    2. Loại bỏ self-loop (source == target sau remap).
    3. Gộp cặp (source, target) trùng → giữ relationship có strength cao hơn.
    4. Lọc bỏ relationship yếu (strength < min_strength).
    """
    seen: dict[tuple, dict] = {}

    for r in relationships:
        src = name_map.get(r["source"], r["source"])
        tgt = name_map.get(r["target"], r["target"])

        if src == tgt:          # bỏ self-loop
            continue
        if r["strength"] < min_strength:
            continue

        key   = (src, tgt)
        entry = {
            "source":      src,
            "target":      tgt,
            "description": r["description"],
            "strength":    r["strength"],
        }

        if key not in seen or r["strength"] > seen[key]["strength"]:
            seen[key] = entry

    return list(seen.values())


# ══════════════════════════════════════════════════════════════
# 5. NORMALIZE — TRÍCH XUẤT THUỘC TÍNH SỐ
# ══════════════════════════════════════════════════════════════

def normalize_entities(entities: list[dict]) -> list[dict]:
    """
    Trích xuất thuộc tính số từ name + description để lưu vào node Neo4j:
    - GPA   → gpa_min, gpa_max   (field: GPA_MIN, GPA_MAX)
    - Rèn luyện → rl_min         (field: RL_MIN)
    - Tín chỉ   → credit_min     (field: CREDIT_MIN)
    """
    normalized = []

    for e in entities:
        new_e = dict(e)
        etype = e.get("type", "")
        text  = e.get("name", "") + " " + e.get("description", "")

        # ── GPA ─────────────────────────────────────────────────────
        is_gpa = etype == "GPA_RANGE" or (
            etype in ("DIEU_KIEN",) and re.search(r"\bgpa\b|điểm trung bình", text, re.I)
        )
        if is_gpa:
            m = re.search(r"(\d\.\d+)\s*[-–]\s*(\d\.\d+)", text)
            if m:
                new_e["gpa_min"] = float(m.group(1))
                new_e["gpa_max"] = float(m.group(2))
            else:
                m = re.search(r"[≥>]=?\s*(\d\.\d+)", text)
                if m:
                    new_e["gpa_min"] = float(m.group(1))
                    new_e["gpa_max"] = 4.0

        # ── RÈN LUYỆN ───────────────────────────────────────────────
        is_rl = etype == "RL_CONDITION" or (
            etype in ("DIEU_KIEN",) and re.search(r"rèn luyện", text, re.I)
        )
        if is_rl:
            m = re.search(r"[≥>]=?\s*(\d+)", text)
            if m:
                new_e["rl_min"] = int(m.group(1))

        # ── TÍN CHỈ ─────────────────────────────────────────────────
        is_credit = etype == "CREDIT_CONDITION" or (
            etype in ("DIEU_KIEN",) and re.search(r"tín chỉ", text, re.I)
        )
        if is_credit:
            m = re.search(r"[≥>]=?\s*(\d+)", text)
            if m:
                new_e["credit_min"] = int(m.group(1))
            if re.search(r"<\s*15|dưới\s+15|tối đa ngành", text, re.I):
                new_e["credit_special"] = e.get("description", "")

        normalized.append(new_e)

    return normalized


# ══════════════════════════════════════════════════════════════
# 6. PIPELINE TỔNG HỢP
# ══════════════════════════════════════════════════════════════

def process_kg(
    results: list[dict],
    similarity_threshold: float = 0.92,
    min_rel_strength: float = 3.0,
) -> tuple[list[dict], list[dict]]:
    """
    Chạy toàn bộ pipeline xử lý sau trích xuất LLM:
      parse_all → exact_dedup → semantic_dedup
      → remap_relationships → dedup_relationships → normalize

    Trả về (entities, relationships) sẵn sàng để nạp vào Neo4j (build_kg.py).
    """
    print("[1/5] Parse raw LLM output...")
    entities, relationships = parse_all(results)
    print(f"  Raw: {len(entities)} entities, {len(relationships)} relationships")

    print("[2/5] Exact dedup tên...")
    print("[3/5] Semantic dedup (vietnamese-bi-encoder, threshold=0.92)...")
    entities, name_map = deduplicate_entities(entities, similarity_threshold)
    print(f"  Sau dedup: {len(entities)} entities")

    print("[4/5] Remap + dedup + lọc relationships...")
    relationships = deduplicate_relationships(relationships, name_map, min_rel_strength)
    print(f"  Sau remap: {len(relationships)} relationships")

    print("[5/5] Normalize thuộc tính số (GPA, RL, tín chỉ)...")
    entities = normalize_entities(entities)

    return entities, relationships


# ══════════════════════════════════════════════════════════════
# SELF-TEST
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    sample = """
("entity"<|>HỌC BỔNG LOẠI GIỎI<|>LOAI_HOC_BONG<|>Học bổng KKHT mức giỏi dành cho SV đạt GPA loại giỏi trở lên)
##
("entity"<|>GPA ≥ 3.60<|>DIEU_KIEN<|>Điều kiện GPA: điểm trung bình học tập ≥ 3.60)
##
("entity"<|>RÈN LUYỆN ≥ 80<|>DIEU_KIEN<|>Điều kiện rèn luyện: điểm rèn luyện ≥ 80 điểm)
##
("entity"<|>TÍN CHỈ ≥ 15<|>DIEU_KIEN<|>Điều kiện số tín chỉ: đăng ký ≥ 15 tín chỉ trong kỳ)
##
("entity"<|>HỌC BỔNG GIỎI<|>LOAI_HOC_BONG<|>Học bổng mức giỏi tại TLU — cùng ngữ nghĩa với Học bổng loại giỏi)
##
("relationship"<|>HỌC BỔNG LOẠI GIỎI<|>GPA ≥ 3.60<|>Yêu cầu GPA ≥ 3.60<|>9)
##
("relationship"<|>HỌC BỔNG LOẠI GIỎI<|>RÈN LUYỆN ≥ 80<|>Yêu cầu rèn luyện ≥ 80<|>9)
##
("relationship"<|>HỌC BỔNG LOẠI GIỎI<|>TÍN CHỈ ≥ 15<|>Yêu cầu đăng ký ≥ 15 tín chỉ<|>10)
##
("relationship"<|>HỌC BỔNG GIỎI<|>GPA ≥ 3.60<|>Học bổng giỏi yêu cầu GPA<|>8)
<|COMPLETE|>
"""
    results_test = [{"chunk_id": 1, "content": "test", "raw_output": sample}]
    entities, relationships = process_kg(results_test)

    print("\n=== ENTITIES ===")
    for e in entities:
        extras = {k: v for k, v in e.items() if k not in ("name", "type", "description")}
        print(f"  [{e['type']}] {e['name']}")
        if extras:
            print(f"    → {extras}")

    print("\n=== RELATIONSHIPS ===")
    for r in relationships:
        print(f"  {r['source']} --({r['strength']})→ {r['target']}")