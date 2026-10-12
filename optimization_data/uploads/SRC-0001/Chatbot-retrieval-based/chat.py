# -*- coding: utf-8 -*-
import sys
import io
import re
import numpy as np
from underthesea import word_tokenize
from config import llm, vector_db, svm_pipeline, CONFIDENCE_THR, CHITCHAT_LABEL

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stdin  = io.TextIOWrapper(sys.stdin.buffer,  encoding='utf-8', errors='replace')

# ==================== XỬ LÝ VĂN BẢN ====================
def preprocess_text(text: str) -> str:
    """Chuyển text về chữ thường và tách từ bằng underthesea."""
    if not isinstance(text, str):
        return ""
    return word_tokenize(text.lower(), format="text")

# ==================== PHÂN LOẠI Ý ĐỊNH (SVM) ====================
def classify_intent(query: str) -> tuple[str, float]:
    """Dùng SVM pipeline để phân loại topic và trả về độ tin cậy."""
    processed  = preprocess_text(query)
    proba      = svm_pipeline.predict_proba([processed])[0]
    confidence = np.max(proba)
    topic      = svm_pipeline.classes_[np.argmax(proba)]
    return topic, confidence

def classify_multi_intent(query: str, top_n: int = 2, sec_thr: float = 0.15) -> list[str]:
    """
    Phát hiện nhiều topic trong 1 câu hỏi — phiên bản giới hạn top_n.
    Lấy topic cao nhất + bất kỳ topic nào có proba >= sec_thr.
    Loại bỏ CHITCHAT khỏi danh sách multi-topic.

    Lưu ý: hàm này chỉ xét tối đa top_n=2 topic.
    Dùng classify_n_intent() nếu cần phát hiện nhiều hơn 2 topic.
    """
    processed = preprocess_text(query)
    proba     = svm_pipeline.predict_proba([processed])[0]
    classes   = svm_pipeline.classes_

    # Sắp xếp giảm dần theo proba
    sorted_idx = np.argsort(proba)[::-1]

    topics = []
    for idx in sorted_idx[:top_n]:
        label = classes[idx]
        score = proba[idx]
        if label == CHITCHAT_LABEL:
            continue
        if not topics:                  # topic đầu tiên luôn lấy nếu > CONFIDENCE_THR
            if score >= CONFIDENCE_THR:
                topics.append(label)
        else:                           # topic thứ 2+ chỉ lấy nếu đủ ngưỡng phụ
            if score >= sec_thr:
                topics.append(label)

    return topics  # [] nếu không topic nào đủ ngưỡng (→ chitchat hoặc MMR)

# ==================== PHÁT HIỆN N TOPIC (MỞ RỘNG) ====================
def classify_n_intent(query: str, max_topics: int = 3) -> list[str]:

    processed = preprocess_text(query)
    proba     = svm_pipeline.predict_proba([processed])[0]
    classes   = svm_pipeline.classes_

    # Sắp xếp giảm dần, lọc bỏ CHITCHAT (không cần retrieve tài liệu cho chitchat)
    sorted_idx = np.argsort(proba)[::-1]
    filtered   = [
        (classes[i], proba[i])
        for i in sorted_idx
        if classes[i] != CHITCHAT_LABEL
    ]

    if not filtered:
        return []

    # Topic đầu tiên phải đủ ngưỡng chính mới lấy
    if filtered[0][1] < CONFIDENCE_THR:
        return []

    topics = [filtered[0][0]]

    # Xét topic tiếp theo bằng gap động — không vượt max_topics
    for i in range(1, min(len(filtered), max_topics)):
        prev_score = filtered[i - 1][1]
        curr_score = filtered[i][1]
        gap        = prev_score - curr_score

        # Dừng nếu xác suất tuyệt đối quá thấp HOẶC gap đột ngột lớn hơn 0.15
        if curr_score < 0.10 or gap > 0.15:
            break

        topics.append(filtered[i][0])

    return topics

# ==================== TRUY XUẤT TÀI LIỆU (RETRIEVAL) ====================
def retrieve_all_by_topic(topic: str) -> str:
    """Lấy TOÀN BỘ nội dung topic, dedup, ghép liền mạch."""
    try:
        col1  = vector_db.get(where={"topic": topic})
        docs1 = col1["documents"] if col1 and col1["documents"] else []
    except Exception:
        docs1 = []

    try:
        col2       = vector_db.get()
        topic_file = topic.lower().replace("_", "")
        docs2 = [
            doc for doc, meta in zip(col2["documents"], col2["metadatas"])
            if meta.get("topic") == topic
            or topic_file in meta.get("source", "").lower().replace("_", "").replace(" ", "")
        ]
    except Exception:
        docs2 = []

    all_docs = docs1 + [d for d in docs2 if d not in docs1]
    if not all_docs:
        return ""

    seen, unique = [], []
    for content in all_docs:
        content = content.strip()
        if content and not any(content in s or s in content for s in seen):
            seen.append(content)
            unique.append(content)

    return "\n\n".join(unique)

def retrieve_mmr(query: str, topic: str = None) -> str:
    """Dùng MMR khi không rõ topic."""
    search_kwargs = {"fetch_k": 20, "k": 5, "lambda_mult": 0.5}
    if topic:
        search_kwargs["filter"] = {"topic": topic}
    retriever = vector_db.as_retriever(search_type="mmr", search_kwargs=search_kwargs)
    return "\n\n".join([d.page_content.strip() for d in retriever.invoke(query)])

def retrieve_n_topics(topics: list[str], query: str) -> str:
    parts = []
    for topic in topics:
        ctx = retrieve_all_by_topic(topic) or retrieve_mmr(query, topic)
        if ctx:
            parts.append(f"[Chủ đề: {topic}]\n{ctx}")

    return f"\n\n{'='*40}\n\n".join(parts)

# ==================== LÀM SẠCH VĂN BẢN ====================
def clean_text(text: str) -> str:
    """Nối dòng bị cắt sai do docx loader, xóa dòng trắng thừa."""
    text = re.sub(r'\n\.', '.', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# ==================== LỊCH SỬ HỘI THOẠI ====================
chat_history = []
MAX_HISTORY  = 10

def update_history(query: str, response: str) -> None:
    """Lưu lượt hội thoại vào history, giữ tối đa MAX_HISTORY lượt."""
    chat_history.append({"role": "user",      "content": query})
    chat_history.append({"role": "assistant", "content": response})
    if len(chat_history) > MAX_HISTORY * 2:
        del chat_history[:2]


# ==================== PROMPT DÙNG CHUNG ====================
CHITCHAT_SYSTEM = (
    "Bạn là trợ lý tư vấn sinh viên thân thiện của Đại học Thủy Lợi (TLU). "
    "Trả lời ngắn gọn, tự nhiên bằng tiếng Việt có dấu đầy đủ."
)

RAG_SYSTEM = (
    "Bạn là trợ lý tư vấn sinh viên Đại học Thủy Lợi (TLU).\n"
    "NGUYÊN TẮC:\n"
    "1. Chỉ dùng thông tin CÓ TRONG tài liệu được cung cấp, không thêm bất kỳ thông tin nào ngoài tài liệu.\n"
    "2. Trả lời ĐÚNG VÀO CÂU HỎI — không lan man sang nội dung khác.\n"
    "3. Nếu câu hỏi hỏi định nghĩa → chỉ trả lời phần định nghĩa đó.\n"
    "4. Nếu câu hỏi hỏi liệt kê / có mấy loại → ĐỌC TOÀN BỘ tài liệu từ đầu đến cuối, "
       "đếm TẤT CẢ các mục, rồi liệt kê ĐẦY ĐỦ theo đúng thứ tự xuất hiện trong tài liệu. "
       "TUYỆT ĐỐI không được bỏ sót bất kỳ mục nào, không gộp nhóm, không tóm tắt.\n"
    "5. Nếu tài liệu có nhiều chủ đề (nhiều nhãn [Chủ đề: ...]) → trả lời lần lượt từng chủ đề, "
       "có tiêu đề **Chủ đề: ...** rõ ràng, không trộn lẫn nội dung.\n"
    "6. Có thể dùng lịch sử hội thoại để hiểu câu hỏi ngắn hoặc chỉ số thứ tự.\n"
    "7. Trả lời bằng tiếng Việt có dấu, thân thiện, rõ ràng."
)

NO_CONTEXT_REPLY = (
    "Xin lỗi, mình chưa tìm thấy thông tin này trong tài liệu của trường.\n"
    "Bạn vui lòng liên hệ Phòng Đào tạo để được hỗ trợ chính xác nhất nhé!"
)

def build_rag_prompt(query: str, context: str) -> str:
    return (
        f"TÀI LIỆU:\n"
        f"{'='*60}\n"
        f"{context}\n"
        f"{'='*60}\n\n"
        f"CÂU HỎI: {query}\n\n"
        f"HƯỚNG DẪN TRẢ LỜI:\n"
        f"- Đọc TOÀN BỘ tài liệu từ đầu đến cuối trước khi trả lời.\n"
        f"- Xác định câu hỏi đang hỏi GÌ: định nghĩa, liệt kê, hay chi tiết một mục.\n"
        f"- Nếu hỏi 'có mấy loại' hoặc liệt kê → tìm và đếm TẤT CẢ các mục trong tài liệu, "
        f"liệt kê ĐẦY ĐỦ theo thứ tự, đánh số 1, 2, 3... KHÔNG được dừng giữa chừng, "
        f"KHÔNG gộp nhóm, KHÔNG bỏ sót dù chỉ 1 mục.\n"
        f"- Nếu tài liệu có nhiều nhãn [Chủ đề: ...] → trả lời lần lượt từng chủ đề, "
        f"có tiêu đề **Chủ đề: ...** rõ ràng.\n"
        f"- Nếu câu hỏi liên quan đến lượt trước (thứ 2, loại đó, cái đó...) → dùng lịch sử để hiểu đúng ý.\n"
        f"- Chỉ trả lời ĐÚNG phần được hỏi, không thêm thông tin thừa."
    )


# ==================== GỌI LLM (STREAMING) ====================
def call_groq_stream(system: str, prompt: str, history: list = []) -> str:
    """Gọi Groq với streaming — in từng chữ ngay khi nhận được."""
    try:
        messages = [{"role": "system", "content": system}]
        messages += history
        messages.append({"role": "user", "content": prompt})

        stream = llm.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.0,
            max_tokens=2048,
            stream=True
        )

        full_response = ""
        print("\nChatbot: ", end="", flush=True)
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                print(delta, end="", flush=True)
                full_response += delta
        print()
        return full_response

    except Exception as e:
        error_msg = f"Lỗi kết nối Groq: {str(e)}"
        print(f"\nChatbot: {error_msg}")
        return error_msg


# ==================== GỌI LLM (NO STREAM) ====================
def call_llm_no_stream(system: str, prompt: str, history: list = []) -> str:
    """Gọi LLM không streaming — dùng cho web API."""
    try:
        messages = [{"role": "system", "content": system}]
        messages += history
        messages.append({"role": "user", "content": prompt})

        completion = llm.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.0,
            max_tokens=2048
        )
        return completion.choices[0].message.content

    except Exception as e:
        return f"Lỗi LLM: {str(e)}"


# ==================== GENERATE ====================
def generate_chitchat(query: str) -> None:
    """Xử lý câu hỏi giao tiếp thông thường, có nhớ lịch sử."""
    response = call_groq_stream(CHITCHAT_SYSTEM, query, chat_history)
    update_history(query, response)


def generate_rag(query: str, context: str) -> None:
    """Trả lời từ tài liệu (streaming), có nhớ lịch sử hội thoại."""
    if not context:
        print(f"\nChatbot: {NO_CONTEXT_REPLY}")
        return
    context  = clean_text(context)
    prompt   = build_rag_prompt(query, context)
    response = call_groq_stream(RAG_SYSTEM, prompt, chat_history)
    update_history(query, response)


# ==================== VÒNG LẶP CHAT ====================
def chat():
    """Vòng lặp chính của chatbot."""
    print("=" * 55)
    print("   Chatbot Tư Vấn Sinh Viên - TLU")
    print("   Gõ 'exit' để thoát | Gõ 'debug' để bật/tắt debug")
    print("=" * 55)

    debug_mode = False

    while True:
        try:
            query = input("\nBạn: ").strip()
        except (UnicodeDecodeError, EOFError):
            continue

        if not query:
            continue
        if query.lower() == "exit":
            print("Tạm biệt!")
            break
        if query.lower() == "debug":
            debug_mode = not debug_mode
            print(f"[Debug: {'BẬT' if debug_mode else 'TẮT'}]")
            continue

        # Bước 1: Phân loại ý định chính
        topic, confidence = classify_intent(query)
        if debug_mode:
            print(f"\n[DEBUG] Topic chính: {topic} | Confidence: {confidence:.2f}")

        # Bước 2: Chitchat → không cần tài liệu
        if topic == CHITCHAT_LABEL and confidence >= CONFIDENCE_THR:
            if debug_mode:
                print("[DEBUG] → Chitchat")
            generate_chitchat(query)
            continue

        # Bước 3: Phát hiện N topic (dùng gap động, tối đa 3)
        n_topics = classify_n_intent(query)
        if debug_mode:
            print(f"[DEBUG] N-topics phát hiện: {n_topics}")

        # Bước 4: Lấy context theo số topic phát hiện được
        if n_topics:
            # Có 1 hoặc nhiều topic rõ ràng → gộp context tất cả
            context = retrieve_n_topics(n_topics, query)
            if debug_mode:
                print(f"[DEBUG] → {len(n_topics)} topic(s): {n_topics}")
        elif confidence < CONFIDENCE_THR:
            # Không topic nào đủ ngưỡng → tìm kiếm ngữ nghĩa toàn bộ DB
            context = retrieve_mmr(query)
            if debug_mode:
                print("[DEBUG] → Confidence thấp, dùng MMR toàn bộ DB")
        else:
            # Fallback: dùng topic chính từ classify_intent
            context = retrieve_all_by_topic(topic) or retrieve_mmr(query, topic)
            if debug_mode:
                print(f"[DEBUG] → Fallback topic chính: {topic}")

        if debug_mode:
            print(f"\n{'='*60}\nNỘI DUNG TÀI LIỆU:\n{'='*60}\n{context}\n{'='*60}\n")

        # Bước 5: Sinh câu trả lời
        generate_rag(query, context)


# ==================== API WEB ====================
def chatbot_response(query: str) -> str:
    """Hàm dùng cho web Flask."""
    # Bước 1: Phân loại ý định chính
    topic, confidence = classify_intent(query)

    # Bước 2: Chitchat → trả lời trực tiếp không cần tài liệu
    if topic == CHITCHAT_LABEL and confidence >= CONFIDENCE_THR:
        response = call_llm_no_stream(CHITCHAT_SYSTEM, query, chat_history)
        update_history(query, response)
        return response

    # Bước 3: Phát hiện N topic (dùng gap động, tối đa 3)
    n_topics = classify_n_intent(query)

    # Bước 4: Lấy context theo số topic phát hiện được
    if n_topics:
        # Có 1 hoặc nhiều topic → gộp context tất cả
        context = retrieve_n_topics(n_topics, query)
    elif confidence < CONFIDENCE_THR:
        # Không topic nào đủ ngưỡng → MMR toàn bộ DB
        context = retrieve_mmr(query)
    else:
        # Fallback: dùng topic chính
        context = retrieve_all_by_topic(topic) or retrieve_mmr(query, topic)

    if not context:
        return NO_CONTEXT_REPLY

    context  = clean_text(context)
    prompt   = build_rag_prompt(query, context)
    response = call_llm_no_stream(RAG_SYSTEM, prompt, chat_history)
    update_history(query, response)
    return response


if __name__ == "__main__":
    chat()