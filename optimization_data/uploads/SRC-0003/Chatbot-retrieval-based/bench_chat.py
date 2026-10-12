# -*- coding: utf-8 -*-
"""Benchmark batch cho chatbot — chạy lặp được, in ra STEP <ten> <ms>.

  python bench_chat.py                     # 1 vong: classify + retrieve (local)
  python bench_chat.py --repeat 30         # 30 vong trong 1 process (tick "Script tu lap")
  python bench_chat.py --mode chat --repeat 30   # toan pipeline (can Neo4j, goi Gemini)

Mo vong in cac dong STEP <ten> <ms> cho tung buoc, roi ket thuc bang RUN <ms>
(wall cua vong do script tu do). Khi tick "Script tu lap", runner tach moi RUN
thanh 1 run riet -> 30 mau chi tao 1 lan khoi tao process (~25s) thay vi 30 lan.
"""
import argparse
import time

import numpy as np
from underthesea import word_tokenize

from config import vector_db, svm_pipeline, CONFIDENCE_THR, CHITCHAT_LABEL

QUERIES = [
    "học phí một học kỳ là bao nhiêu?",
    "điều kiện nhận học bổng là gì?",
    "hồ sơ xét tuyển gồm những giấy tờ nào?",
    "lịch thi giữa kỳ của trường?",
    "thủ tục đổi ngành học như thế nào?",
]


def preprocess(text: str) -> str:
    return word_tokenize(text.lower(), format="text")


def classify(query: str) -> str:
    proba = svm_pipeline.predict_proba([preprocess(query)])[0]
    classes = list(svm_pipeline.classes_)
    order = np.argsort(proba)[::-1]
    for idx in order:
        if classes[idx] != CHITCHAT_LABEL:
            return classes[idx] if proba[idx] >= CONFIDENCE_THR else ""
    return ""


def retrieve(query: str, topic: str) -> str:
    search_kwargs = {"fetch_k": 10, "k": 5, "lambda_mult": 0.5}
    if topic:
        search_kwargs["filter"] = {"topic": topic}
    retriever = vector_db.as_retriever(search_type="mmr", search_kwargs=search_kwargs)
    return "\n\n".join(d.page_content for d in retriever.invoke(query))


def run_rag_cycle() -> None:
    for query in QUERIES:
        started = time.perf_counter()
        topic = classify(query)
        print("STEP classify %.1f" % ((time.perf_counter() - started) * 1000.0))

        started = time.perf_counter()
        retrieve(query, topic)
        print("STEP retrieve %.1f" % ((time.perf_counter() - started) * 1000.0))


def run_chat_cycle() -> None:
    from chat import chatbot_response

    for query in QUERIES:
        started = time.perf_counter()
        for _token in chatbot_response(query):
            pass
        print("STEP chat %.1f" % ((time.perf_counter() - started) * 1000.0))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("rag", "chat"), default="rag")
    parser.add_argument("--repeat", type=int, default=1, help="số vòng lặp trong 1 process")
    args = parser.parse_args()

    cycle = run_chat_cycle if args.mode == "chat" else run_rag_cycle
    for _ in range(max(1, args.repeat)):
        started = time.perf_counter()
        cycle()
        print("RUN %.1f" % ((time.perf_counter() - started) * 1000.0))
    print("done")


if __name__ == "__main__":
    main()
