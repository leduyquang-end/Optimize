import os
import numpy as np
from neo4j import GraphDatabase
from config import llm, vector_db, svm_pipeline, embed_model, CONFIDENCE_THR, CHITCHAT_LABEL, GROQ_MODEL

# ==================== KẾT NỐI NEO4J ====================
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "12345678")

_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD),encrypted=False)

# ==================== LOAD GRAPH VÀO RAM (1 LẦN KHI KHỞI ĐỘNG) ====================
# Đọc toàn bộ node + edge vào dict để tra cứu O(1), không query Neo4j mỗi lần chat
_nodes: dict[str, dict] = {}   # name → {type, description, ...}
_edges: list[dict]       = []   # [{source, target, description, weight}]

with _driver.session() as _s:
    for rec in _s.run("MATCH (n:KGNode) RETURN properties(n) AS p"):
        p = rec["p"]
        _nodes[p["name"]] = p

    for rec in _s.run("""
        MATCH (a:KGNode)-[r:RELATES_TO]->(b:KGNode)
        RETURN a.name AS source, b.name AS target,
               r.description AS description, r.weight AS weight
    """):
        _edges.append(dict(rec))

print(f"Đã load graph: {len(_nodes)} nodes, {len(_edges)} edges")

# Pre-embed toàn bộ node (name + description) để dùng cho semantic retrieval
# ==================== CACHE NODE EMBEDDINGS ====================
CACHE_DIR  = "cache"
CACHE_FILE = os.path.join(CACHE_DIR, "node_vecs.npy")

os.makedirs(CACHE_DIR, exist_ok=True)

# Pre-embed toàn bộ node (name + description)
_node_names = list(_nodes.keys())

_node_texts = [
    f"{n} {_nodes[n].get('description', '')}"
    for n in _node_names
]

# Nếu đã có cache thì load luôn
if os.path.exists(CACHE_FILE):
    print("Đang load node embeddings từ cache...")
    _node_vecs = np.load(CACHE_FILE)

# Nếu chưa có thì embed rồi lưu cache
else:
    print("Đang embedding nodes lần đầu...")
    _node_vecs = np.array(
        embed_model.embed_documents(_node_texts)
    )

    np.save(CACHE_FILE, _node_vecs)
    print(f"Đã lưu cache embeddings vào: {CACHE_FILE}")

print(f"Đã sẵn sàng {len(_node_names)} node embeddings")

# Lookup cạnh nhanh: source → [(target, edge_data)], target → [(source, edge_data)]
_out_edges: dict[str, list] = {n: [] for n in _node_names}
_in_edges:  dict[str, list] = {n: [] for n in _node_names}
for e in _edges:
    if e["source"] in _out_edges:
        _out_edges[e["source"]].append((e["target"], e))
    if e["target"] in _in_edges:
        _in_edges[e["target"]].append((e["source"], e))

# ==================== KG RETRIEVAL — HYBRID ====================
# α ∈ [0,1]: trọng số cho semantic score; (1-α) cho keyword score
# α = 0.7 → ưu tiên ngữ nghĩa, vẫn giữ tín hiệu từ khóa
ALPHA = 0.7

def get_kg_context(question: str, top_k: int = 5) -> str:
    """
    Hybrid retrieval từ Knowledge Graph:

    1. Keyword-based score:
       score_keyword(n) = Σ freq(k, n)   với k là từ trong câu hỏi (len > 2)
       Đếm số lần từ khóa xuất hiện trong (name + description) của node.

    2. Vector-based Semantic score:
       score_semantic(n) = cos(q, n)
       Embed câu hỏi, tính cosine với vector đã pre-embed của mỗi node.

    3. Kết hợp có trọng số:
       score(n) = α × score_semantic(n) + (1-α) × score_keyword_normalized(n)
       α = 0.7 theo thiết lập trong báo cáo.

    4. Neighborhood Expansion:
       Với mỗi node được chọn, lấy thêm toàn bộ cạnh ra và vào kèm mô tả.
    """
    if not _node_names:
        return ""

    question_lower = question.lower()
    words = [w for w in question_lower.split() if len(w) > 2]

    # ── 1. Keyword score ────────────────────────────────────────────
    keyword_scores = np.zeros(len(_node_names))
    for i, name in enumerate(_node_names):
        node_text = (name + " " + _nodes[name].get("description", "")).lower()
        keyword_scores[i] = sum(node_text.count(w) for w in words)

    # Normalize về [0, 1]
    kw_max = keyword_scores.max()
    if kw_max > 0:
        keyword_scores = keyword_scores / kw_max

    # ── 2. Semantic score ────────────────────────────────────────────
    q_vec = np.array(embed_model.embed_query(question))   # (D,) normalized
    semantic_scores = _node_vecs @ q_vec                   # cosine similarity (N,)

    # ── 3. Kết hợp có trọng số ──────────────────────────────────────
    combined = ALPHA * semantic_scores + (1 - ALPHA) * keyword_scores

    # Lấy top_k node có score cao nhất, ngưỡng tối thiểu > 0
    top_indices = np.argsort(combined)[::-1][:top_k]
    top_nodes   = [_node_names[i] for i in top_indices if combined[i] > 0]

    if not top_nodes:
        return ""

    # ── 4. Neighborhood Expansion ────────────────────────────────────
    context_parts = []
    for node in top_nodes:
        data = _nodes[node]
        context_parts.append(
            f"- {node} ({data.get('type', '')}): {data.get('description', '')}"
        )
        # Cạnh ra
        for target, edge in _out_edges.get(node, []):
            context_parts.append(f"  → {target}: {edge['description']}")
            # Lấy thêm description của neighbor
            neighbor_desc = _nodes.get(target, {}).get("description", "")
            if neighbor_desc:
                context_parts.append(f"    ({neighbor_desc})")
        # Cạnh vào
        for source, edge in _in_edges.get(node, []):
            context_parts.append(f"  ← {source}: {edge['description']}")

    return "\n".join(context_parts)


# ==================== DETECT FOLLOW-UP ====================
FOLLOWUP_KEYWORDS = ["đó", "này", "vậy", "thế", "còn", "thêm", "nữa", "sao", "thì"]

def is_followup(query: str, history: list) -> bool:
    if not history:
        return False
    if len(query.strip().split()) <= 4:
        return True
    if any(kw in query.lower() for kw in FOLLOWUP_KEYWORDS):
        return True
    return False


# ==================== GENERATE ====================
def call_llm(prompt: str, temperature: float = 0) -> str:
    response = llm.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()

def generate_kg(query: str, kg_context: str, history: list = []) -> str:
    history_text = ""
    if history:
        history_text = "Lịch sử hội thoại gần đây:\n"
        history_text += "\n".join([
            f"{'Sinh viên' if h['role'] == 'user' else 'Chatbot'}: {h['content']}"
            for h in history[-6:]
        ])
        history_text += "\n\n"

    prompt = f"""Bạn là trợ lý tư vấn thông tin học bổng của Trường Đại học Thủy lợi.
Dựa vào thông tin bên dưới để trả lời câu hỏi của sinh viên.

{history_text}QUY TẮC:
    1. ƯU TIÊN sử dụng thông tin từ knowledge graph.
    2. KHÔNG được suy diễn các thông tin (ví dụ: không được nói "thường là 3.0").
    3. Có thể diễn đạt lại thông tin cho dễ hiểu, nhưng phải giữ nguyên ý nghĩa.
    4. Nếu câu hỏi đưa ra điều kiện về số tín chỉ đăng kí mà chưa rõ đó là số 
    tín chỉ tối đa đăng kí của ngành hay số tín chỉ họ chỉ đăng kí trong kì này 
    thì phải hỏi lại để xác định rõ thông tin, không được đưa ra kết luận ngay.
    5.Đọc TOÀN BỘ tài liệu từ đầu đến cuối trước khi trả lời.
CÁCH TRẢ LỜI:
- Xác định thông tin liên quan
- Nếu có số liệu → giữ nguyên
- Kết luận rõ ràng, thân thiện và gần gũi với người dùng

Thông tin từ knowledge graph:
{kg_context}

Câu hỏi: {query}"""

    return call_llm(prompt)





