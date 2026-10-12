from langchain_community.document_loaders import Docx2txtLoader
import re


def load_docx(path: str) -> str:
    loader = Docx2txtLoader(path)
    docs = loader.load()
    return docs[0].page_content


def chunk_by_article(text: str) -> list[dict]:
    """
    Mỗi Điều là một chunk. Trả về list dict gồm chunk_id và content.
    """
    parts = re.split(r'(?=\n\n[\t\s]*Điều\s+\d+\.\s+)', text)

    chunks = []
    chunk_id = 1

    for part in parts:
        part = part.strip()
        if re.match(r'Điều\s+\d+\.', part) and len(part) > 10:
            chunks.append({"chunk_id": chunk_id, "content": part})
            chunk_id += 1

    return chunks


if __name__ == "__main__":
    import os

    # Tự động trỏ đúng vào file Hoc_Bong_Hoc_Tap.docx nằm cùng thư mục với ingest_kg.py
    current_dir = os.path.dirname(os.path.abspath(__file__))
    docx_path = os.path.join(current_dir, "Hoc_Bong_Hoc_Tap.docx")

    text = load_docx(docx_path)
    chunks = chunk_by_article(text)


    print(f"Tổng số chunks: {len(chunks)}\n")
    for chunk in chunks:
        print(f"--- Chunk {chunk['chunk_id']} ({len(chunk['content'])} ký tự) ---")
        print(chunk["content"])
        print()