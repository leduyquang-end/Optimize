# build_kg.py
"""
Lưu entities và relationships vào Neo4j.

Schema:
  Node  nhãn KGNode  — thuộc tính: name, type, description,
                        GPA_MIN, GPA_MAX, RL_MIN, CREDIT_MIN (nếu có)
  Edge  nhãn RELATES_TO — thuộc tính: description, weight (1-10)

Chiến lược ghi:
  Dùng MERGE (name, type) để tránh trùng lặp khi chạy lại.
  Xóa toàn bộ graph cũ trước khi nạp để đồng bộ với file nguồn.
"""

import json
import os
from neo4j import GraphDatabase

# ==================== KẾT NỐI ====================
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "12345678")


def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ==================== XÓA GRAPH CŨ ====================

def clear_graph(driver):
    """Xóa toàn bộ node KGNode và edge RELATES_TO để đồng bộ với dữ liệu mới."""
    with driver.session() as session:
        session.run("MATCH (n:KGNode) DETACH DELETE n")
    print("  Đã xóa graph cũ.")


# ==================== TẠO INDEX ====================

def create_index(driver):
    """Tạo index trên (name, type) để MERGE nhanh hơn."""
    with driver.session() as session:
        session.run("""
            CREATE INDEX kg_node_name_type IF NOT EXISTS
            FOR (n:KGNode) ON (n.name, n.type)
        """)
    print("  Index KGNode(name, type) sẵn sàng.")


# ==================== NẠP ENTITY ====================

def _build_set_clause(e: dict) -> tuple[str, dict]:
    """
    Xây SET clause động cho các thuộc tính số tuỳ chọn:
    GPA_MIN, GPA_MAX, RL_MIN, CREDIT_MIN, CREDIT_SPECIAL.
    Trả về (cypher_fragment, params_dict).
    """
    optional_fields = {
        "GPA_MIN":        e.get("gpa_min"),
        "GPA_MAX":        e.get("gpa_max"),
        "RL_MIN":         e.get("rl_min"),
        "CREDIT_MIN":     e.get("credit_min"),
        "CREDIT_SPECIAL": e.get("credit_special"),
    }
    parts  = []
    params = {}
    for key, val in optional_fields.items():
        if val is not None:
            param_key = key.lower()
            parts.append(f"n.{key} = ${param_key}")
            params[param_key] = val

    clause = (", " + ", ".join(parts)) if parts else ""
    return clause, params


def upsert_entities(driver, entities: list[dict]):
    """
    MERGE node KGNode theo (name, type).
    Cập nhật description và các thuộc tính số nếu đã tồn tại.
    """
    with driver.session() as session:
        for e in entities:
            optional_clause, optional_params = _build_set_clause(e)

            cypher = f"""
                MERGE (n:KGNode {{name: $name, type: $type}})
                SET n.description = $description
                    {optional_clause}
            """
            params = {
                "name":        e["name"],
                "type":        e["type"],
                "description": e.get("description", ""),
                **optional_params,
            }
            session.run(cypher, params)

    print(f"  Đã upsert {len(entities)} nodes.")


# ==================== NẠP RELATIONSHIP ====================

def upsert_relationships(driver, relationships: list[dict]):
    """
    MERGE edge RELATES_TO theo (source.name, source.type, target.name, target.type).
    Nếu node chưa tồn tại thì MERGE tạo node placeholder trước.
    """
    cypher = """
        MERGE (a:KGNode {name: $source})
        MERGE (b:KGNode {name: $target})
        MERGE (a)-[r:RELATES_TO]->(b)
        SET r.description = $description,
            r.weight      = $weight
    """
    with driver.session() as session:
        for r in relationships:
            session.run(cypher, {
                "source":      r["source"],
                "target":      r["target"],
                "description": r.get("description", ""),
                "weight":      r.get("strength", 5.0),
            })

    print(f"  Đã upsert {len(relationships)} edges.")


# ==================== LOAD GRAPH (ĐỌC LẠI TỪ NEO4J) ====================

def load_graph(driver) -> tuple[list[dict], list[dict]]:
    """
    Đọc lại toàn bộ graph từ Neo4j.
    Trả về (entities, relationships) — tiện dùng trong chat_kg.py thay vì
    load từ file JSON.
    """
    with driver.session() as session:
        node_result = session.run("MATCH (n:KGNode) RETURN properties(n) AS props")
        entities = [record["props"] for record in node_result]

        edge_result = session.run("""
            MATCH (a:KGNode)-[r:RELATES_TO]->(b:KGNode)
            RETURN a.name AS source, b.name AS target,
                   r.description AS description, r.weight AS weight
        """)
        relationships = [dict(record) for record in edge_result]

    return entities, relationships


# ==================== BUILD PIPELINE ====================

def build_kg(parsed_path: str):
    """
    Đọc kg_parsed.json → xóa graph cũ → tạo index → upsert nodes → upsert edges.
    """
    with open(parsed_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entities      = data["entities"]
    relationships = data["relationships"]

    print(f"Đọc: {len(entities)} entities, {len(relationships)} relationships")

    driver = get_driver()
    try:
        print("Xóa graph cũ...")
        clear_graph(driver)

        print("Tạo index...")
        create_index(driver)

        print("Nạp nodes...")
        upsert_entities(driver, entities)

        print("Nạp edges...")
        upsert_relationships(driver, relationships)

        print("\nHoàn tất! Thống kê:")
        with driver.session() as session:
            n_nodes = session.run("MATCH (n:KGNode) RETURN count(n) AS c").single()["c"]
            n_edges = session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS c").single()["c"]
        print(f"  Nodes: {n_nodes}")
        print(f"  Edges: {n_edges}")

    finally:
        driver.close()


# ==================== MAIN ====================

if __name__ == "__main__":
    build_kg("kg_parsed.json")