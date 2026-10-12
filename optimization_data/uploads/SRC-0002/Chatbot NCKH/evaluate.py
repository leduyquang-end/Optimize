# evaluate.py
"""
Script đánh giá Chatbot TLU theo 2 cấp độ:

3.2.1 — Retrieval (Hit Rate, MRR):
    Kiểm tra trong top-k kết quả retrieve có chứa chunk/node đúng không.

3.2.2 — End-to-end (Accuracy, Relevance):
    Dùng LLM (Groq) làm judge so sánh câu trả lời chatbot với đáp án mẫu.

Chuẩn bị:
    File eval_questions.xlsx với các cột:
        question        : câu hỏi
        ground_truth    : đáp án mẫu (văn bản)
        expected_chunk  : từ khóa đặc trưng của chunk/node đúng (dùng cho Hit Rate/MRR)
        topic           : topic của câu hỏi (ví dụ: Hoc_Bong_Hoc_Tap)
        use_kg          : TRUE nếu câu hỏi dùng KG, FALSE nếu dùng RAG

Chạy:
    python evaluate.py
    python evaluate.py --mode retrieval      # chỉ đánh giá retrieval
    python evaluate.py --mode endtoend       # chỉ đánh giá end-to-end
    python evaluate.py --input my_file.xlsx  # dùng file khác
"""

import argparse
import json
import os
import time
import pandas as pd
from tqdm import tqdm

# Import từ project
from config import llm, GROQ_MODEL
from chat import chatbot_response, retrieve_mmr, retrieve_all_by_topic
from chat_kg import get_kg_context

EVAL_FILE   = "eval_questions.xlsx"
RESULT_FILE = "eval_results.xlsx"
TOP_K       = 5      # Hit Rate@5
SLEEP_SEC   = 1.0    # tránh rate limit Groq


# ══════════════════════════════════════════════════════════════
# 1. ĐỌC FILE CÂU HỎI
# ══════════════════════════════════════════════════════════════

def load_questions(filepath: str) -> pd.DataFrame:
    df = pd.read_excel(filepath)
    required = ["question", "ground_truth", "expected_chunk"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Thiếu cột '{col}' trong file Excel.")
    df["topic"]  = df.get("topic",  pd.Series([""] * len(df)))
    df["use_kg"] = df.get("use_kg", pd.Series([False] * len(df)))
    df = df.fillna("")
    print(f"Đã load {len(df)} câu hỏi từ {filepath}")
    return df


# ══════════════════════════════════════════════════════════════
# 2. RETRIEVAL EVALUATION — Hit Rate & MRR
# ══════════════════════════════════════════════════════════════

def retrieve_for_eval(question: str, topic: str, use_kg: bool) -> list[str]:
    """
    Trả về list các đoạn text retrieve được (top-k).
    KG → list node descriptions + relationships.
    RAG → list chunk page_content.
    """
    if use_kg:
        kg_context = get_kg_context(question, top_k=TOP_K)
        # Mỗi dòng là 1 "kết quả"
        return [line.strip() for line in kg_context.split("\n") if line.strip()]
    else:
        # Ưu tiên topic nếu có
        if topic:
            from langchain_chroma import Chroma
            from config import vector_db
            search_kwargs = {"k": TOP_K, "fetch_k": 20, "lambda_mult": 0.5,
                             "filter": {"topic": topic}}
            retriever = vector_db.as_retriever(
                search_type="mmr", search_kwargs=search_kwargs
            )
            docs = retriever.invoke(question)
        else:
            from config import vector_db
            search_kwargs = {"k": TOP_K, "fetch_k": 20, "lambda_mult": 0.5}
            retriever = vector_db.as_retriever(
                search_type="mmr", search_kwargs=search_kwargs
            )
            docs = retriever.invoke(question)
        return [d.page_content.strip() for d in docs]


def check_hit(retrieved: list[str], expected_chunk: str) -> tuple[bool, int]:
    """
    Kiểm tra expected_chunk có xuất hiện trong kết quả retrieve không.
    expected_chunk là chuỗi từ khóa đặc trưng (không cần khớp 100%).
    Trả về (hit: bool, rank: int) — rank=0 nếu không tìm thấy.
    """
    keyword = expected_chunk.strip().lower()
    for rank, text in enumerate(retrieved, start=1):
        if keyword in text.lower():
            return True, rank
    return False, 0


def evaluate_retrieval(df: pd.DataFrame) -> dict:
    print("\n" + "="*50)
    print("ĐÁNH GIÁ RETRIEVAL (Hit Rate & MRR)")
    print("="*50)

    hits      = []
    rr_scores = []   # reciprocal rank
    details   = []

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Retrieval"):
        question       = str(row["question"])
        expected_chunk = str(row["expected_chunk"])
        topic          = str(row.get("topic", ""))
        use_kg         = str(row.get("use_kg", "")).upper() == "TRUE"

        retrieved = retrieve_for_eval(question, topic, use_kg)
        hit, rank = check_hit(retrieved, expected_chunk)

        hits.append(1 if hit else 0)
        rr_scores.append(1 / rank if rank > 0 else 0)

        details.append({
            "question":       question,
            "expected_chunk": expected_chunk,
            "hit":            hit,
            "rank":           rank if rank > 0 else "-",
            "top1_retrieved": retrieved[0][:100] if retrieved else "",
        })

        time.sleep(0.1)

    hit_rate = sum(hits) / len(hits)
    mrr      = sum(rr_scores) / len(rr_scores)

    print(f"\nHit Rate@{TOP_K} : {hit_rate:.2f}  ({sum(hits)}/{len(hits)})")
    print(f"MRR             : {mrr:.2f}")

    return {
        "hit_rate": round(hit_rate, 4),
        "mrr":      round(mrr, 4),
        "details":  details,
    }


# ══════════════════════════════════════════════════════════════
# 3. END-TO-END EVALUATION — Accuracy & Relevance (LLM Judge)
# ══════════════════════════════════════════════════════════════

JUDGE_SYSTEM = """Bạn là chuyên gia đánh giá chất lượng chatbot.
Nhiệm vụ: Chấm điểm câu trả lời của chatbot theo 2 tiêu chí.
Trả về JSON hợp lệ, KHÔNG có text thừa."""

def llm_judge(question: str, ground_truth: str, chatbot_answer: str) -> dict:
    """
    Dùng LLM chấm điểm câu trả lời chatbot.
    Trả về {"accuracy": 0/1, "relevance": 0/1, "reason": "..."}
    """
    prompt = f"""Câu hỏi: {question}

Đáp án mẫu: {ground_truth}

Câu trả lời chatbot: {chatbot_answer}

Chấm điểm theo 2 tiêu chí:
1. Accuracy (0 hoặc 1): Thông tin trong câu trả lời có ĐÚNG và ĐẦY ĐỦ so với đáp án mẫu không?
   - 1: đúng và đầy đủ các ý chính
   - 0: sai thông tin, thiếu nhiều ý quan trọng, hoặc không trả lời được

2. Relevance (0 hoặc 1): Câu trả lời có LIÊN QUAN đến câu hỏi không?
   - 1: trả lời đúng trọng tâm câu hỏi
   - 0: lạc đề, trả lời chủ đề khác

Trả về JSON (không có text thừa):
{{"accuracy": 0_hoặc_1, "relevance": 0_hoặc_1, "reason": "giải thích ngắn gọn"}}"""

    try:
        response = llm.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.0,
            max_tokens=256,
        )
        text = response.choices[0].message.content.strip()
        # Bóc JSON khỏi markdown nếu có
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        result = json.loads(text)
        return {
            "accuracy":  int(result.get("accuracy",  0)),
            "relevance": int(result.get("relevance", 0)),
            "reason":    result.get("reason", ""),
        }
    except Exception as e:
        print(f"  [WARN] LLM judge lỗi: {e}")
        return {"accuracy": -1, "relevance": -1, "reason": f"ERROR: {e}"}


def evaluate_endtoend(df: pd.DataFrame) -> dict:
    print("\n" + "="*50)
    print("ĐÁNH GIÁ END-TO-END (Accuracy & Relevance)")
    print("="*50)

    accuracy_scores  = []
    relevance_scores = []
    details          = []

    for _, row in tqdm(df.iterrows(), total=len(df), desc="End-to-end"):
        question     = str(row["question"])
        ground_truth = str(row["ground_truth"])

        # Lấy câu trả lời từ chatbot
        try:
            chatbot_answer = chatbot_response(question)
        except Exception as e:
            chatbot_answer = f"ERROR: {e}"

        time.sleep(SLEEP_SEC)

        # LLM judge
        scores = llm_judge(question, ground_truth, chatbot_answer)

        if scores["accuracy"] >= 0:   # bỏ qua lỗi
            accuracy_scores.append(scores["accuracy"])
            relevance_scores.append(scores["relevance"])

        details.append({
            "question":       question,
            "ground_truth":   ground_truth,
            "chatbot_answer": chatbot_answer,
            "accuracy":       scores["accuracy"],
            "relevance":      scores["relevance"],
            "reason":         scores["reason"],
        })

        time.sleep(SLEEP_SEC)

    accuracy  = sum(accuracy_scores)  / len(accuracy_scores)  if accuracy_scores  else 0
    relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0

    print(f"\nAccuracy  : {accuracy:.2f}  ({sum(accuracy_scores)}/{len(accuracy_scores)})")
    print(f"Relevance : {relevance:.2f}  ({sum(relevance_scores)}/{len(relevance_scores)})")

    return {
        "accuracy":  round(accuracy,  4),
        "relevance": round(relevance, 4),
        "details":   details,
    }


# ══════════════════════════════════════════════════════════════
# 4. LƯU KẾT QUẢ
# ══════════════════════════════════════════════════════════════

def save_results(retrieval_result: dict, endtoend_result: dict, output_path: str):
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:

        # Sheet 1: Tổng kết
        summary = {
            "Chỉ số":  ["Hit Rate", "MRR", "Accuracy", "Relevance"],
            "Giá trị": [
                retrieval_result.get("hit_rate", "-"),
                retrieval_result.get("mrr",      "-"),
                endtoend_result.get("accuracy",  "-"),
                endtoend_result.get("relevance", "-"),
            ],
        }
        pd.DataFrame(summary).to_excel(writer, sheet_name="Tổng kết", index=False)

        # Sheet 2: Chi tiết Retrieval
        if retrieval_result.get("details"):
            pd.DataFrame(retrieval_result["details"]).to_excel(
                writer, sheet_name="Retrieval", index=False
            )

        # Sheet 3: Chi tiết End-to-end
        if endtoend_result.get("details"):
            pd.DataFrame(endtoend_result["details"]).to_excel(
                writer, sheet_name="End-to-end", index=False
            )

    print(f"\nĐã lưu kết quả vào: {output_path}")


# ══════════════════════════════════════════════════════════════
# 5. TẠO FILE TEMPLATE NẾU CHƯA CÓ
# ══════════════════════════════════════════════════════════════

def create_template(filepath: str):
    """Tạo file Excel mẫu để điền câu hỏi đánh giá."""
    sample = {
        "question": [
            "Điều kiện để được học bổng KKHT loại giỏi là gì?",
            "Sinh viên cần đăng ký bao nhiêu tín chỉ để được xét học bổng?",
            "Học bổng khuyến khích học tập có mấy loại?",
        ],
        "ground_truth": [
            "GPA từ 3.60 đến 3.94, điểm rèn luyện ≥ 80, đăng ký ≥ 15 tín chỉ",
            "Tối thiểu 15 tín chỉ, hoặc bằng số tín chỉ tối đa ngành nếu nhỏ hơn 15",
            "3 loại: Xuất sắc, Giỏi, Khá",
        ],
        "expected_chunk": [
            "3.60",           # từ khóa đặc trưng có trong chunk/node đúng
            "15 tín chỉ",
            "học bổng loại",
        ],
        "topic": [
            "Hoc_Bong_Hoc_Tap",
            "Hoc_Bong_Hoc_Tap",
            "Hoc_Bong_Hoc_Tap",
        ],
        "use_kg": [
            "TRUE",
            "TRUE",
            "TRUE",
        ],
    }
    pd.DataFrame(sample).to_excel(filepath, index=False)
    print(f"Đã tạo file template: {filepath}")
    print("Hãy điền đầy đủ câu hỏi rồi chạy lại script.")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Đánh giá Chatbot TLU")
    parser.add_argument("--mode",  choices=["all", "retrieval", "endtoend"],
                        default="all", help="Chế độ đánh giá")
    parser.add_argument("--input", default=EVAL_FILE,
                        help="File Excel câu hỏi đánh giá")
    parser.add_argument("--output", default=RESULT_FILE,
                        help="File Excel lưu kết quả")
    args = parser.parse_args()

    # Tạo template nếu chưa có file câu hỏi
    if not os.path.exists(args.input):
        print(f"Không tìm thấy {args.input}")
        create_template(args.input)
        return

    df = load_questions(args.input)

    retrieval_result = {}
    endtoend_result  = {}

    if args.mode in ("all", "retrieval"):
        retrieval_result = evaluate_retrieval(df)

    if args.mode in ("all", "endtoend"):
        endtoend_result = evaluate_endtoend(df)

    # In tổng kết
    print("\n" + "="*50)
    print("KẾT QUẢ TỔNG KẾT")
    print("="*50)
    if retrieval_result:
        print(f"Hit Rate@{TOP_K} : {retrieval_result.get('hit_rate', '-')}")
        print(f"MRR             : {retrieval_result.get('mrr', '-')}")
    if endtoend_result:
        print(f"Accuracy        : {endtoend_result.get('accuracy', '-')}")
        print(f"Relevance       : {endtoend_result.get('relevance', '-')}")

    save_results(retrieval_result, endtoend_result, args.output)


if __name__ == "__main__":
    main()