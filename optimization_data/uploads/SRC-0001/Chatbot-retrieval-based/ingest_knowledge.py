import os
import shutil
import pandas as pd
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document as LangchainDoc


# ==================== XỬ LÝ FILE EXCEL ====================
def excel_sheet_to_text(df: pd.DataFrame, sheet_name: str) -> str:
    """
    Chuyển một sheet DataFrame thành văn bản có cấu trúc để chunk RAG:
    - ffill() lấp ô trống do merged cell
    - Lọc dòng header category (chỉ có ≤1 cột có giá trị — I, II, ...)
    - Mỗi nhóm (cùng giá trị cột đầu) thành 1 đoạn văn bản
    - Cột cuối (nhiều dòng) được gộp thành danh sách
    """
    df = df.dropna(how="all")

    # Lưu tên cột gốc TRƯỚC khi xử lý (tránh lệch tên do encoding sau ffill)
    headers = [str(c).strip() for c in df.columns]

    # Forward fill TRƯỚC để lấp merged cell
    df = df.ffill(axis=0)
    df = df.map(lambda x: str(x).strip() if pd.notna(x) else "")

    # Gán lại tên cột đã lưu để đảm bảo khớp
    df.columns = headers

    # Lọc bỏ dòng header category (chỉ có ≤1 cột có giá trị — thường là I, II, ...)
    df = df[df.apply(
        lambda row: sum(1 for v in row if v not in ("", "nan", "None")) >= 2,
        axis=1
    )]

    if df.empty:
        return ""

    key_col   = headers[0]
    info_cols = headers[1:-1]
    last_col  = headers[-1] if len(headers) > 1 else None

    lines = []
    seen_keys = list(dict.fromkeys(df[key_col].tolist()))

    for key in seen_keys:
        group = df[df[key_col] == key]

        parts = [
            f"{h}: {group[h].iloc[0]}"
            for h in [key_col] + info_cols
            if group[h].iloc[0] not in ("", "nan", "None")
        ]
        block = " | ".join(parts)

        if last_col and len(headers) > 1:
            items = [v for v in group[last_col].tolist() if v not in ("", "nan", "None")]
            if items:
                block += f"\n{last_col}:\n" + "\n".join(items)

        if block.strip():
            lines.append(block)

    return f"[Sheet: {sheet_name}]\n" + "\n\n".join(lines)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_DIR   = os.path.join(BASE_DIR, "vector_db")

os.makedirs(DATA_DIR, exist_ok=True)

docx_files  = [f for f in os.listdir(DATA_DIR) if f.endswith(".docx")           and not f.startswith("~$")]
excel_files = [f for f in os.listdir(DATA_DIR) if f.endswith((".xlsx", ".xls")) and not f.startswith("~$")]
pdf_files   = [f for f in os.listdir(DATA_DIR) if f.endswith(".pdf")            and not f.startswith("~$")]

if not docx_files and not excel_files and not pdf_files:
    print(f"[LOI] Khong tim thay file .docx, .xlsx hoac .pdf trong: {DATA_DIR}")
    exit(1)

print(f"Tim thay {len(docx_files)} file docx: {docx_files}")
print(f"Tim thay {len(excel_files)} file excel: {excel_files}")
print(f"Tim thay {len(pdf_files)} file pdf: {pdf_files}")

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1500,
    chunk_overlap=200,
    separators=["\n\n\n", "\n\n", "\n", ". ", " ", ""]
)

all_chunks = []

# ==================== NẠP FILE DOCX ====================
for filename in docx_files:
    file_path = os.path.join(DATA_DIR, filename)
    label     = os.path.splitext(filename)[0].replace(" ", "_")

    loader = Docx2txtLoader(file_path)
    data   = loader.load()
    chunks = text_splitter.split_documents(data)

    for chunk in chunks:
        chunk.metadata["topic"]  = label
        chunk.metadata["source"] = filename

    print(f"[{label}]: {len(chunks)} chunks")
    all_chunks.extend(chunks)

# ==================== NẠP FILE EXCEL ====================
for filename in excel_files:
    file_path = os.path.join(DATA_DIR, filename)
    label     = os.path.splitext(filename)[0].replace(" ", "_")

    all_sheets = pd.read_excel(file_path, sheet_name=None, header=0)
    total_chunks = 0

    for sheet_name, df in all_sheets.items():
        text = excel_sheet_to_text(df, sheet_name)
        if not text.strip():
            continue

        raw_chunks = [c.strip() for c in text.split("\n\n") if c.strip() and not c.strip().startswith("[Sheet:")]
        for chunk_text in raw_chunks:
            all_chunks.append(LangchainDoc(
                page_content=chunk_text,
                metadata={"topic": label, "source": filename, "sheet": sheet_name}
            ))
        total_chunks += len(raw_chunks)

    print(f"[{label}]: {total_chunks} chunks từ {len(all_sheets)} sheet(s)")

# ==================== NẠP FILE PDF ====================
for filename in pdf_files:
    file_path = os.path.join(DATA_DIR, filename)
    label     = os.path.splitext(filename)[0].replace(" ", "_")

    loader = PyPDFLoader(file_path)
    data   = loader.load()

    if not data:
        print(f"[{label}]: Bo qua (khong co text, co the la PDF scan)")
        continue

    chunks = text_splitter.split_documents(data)

    for chunk in chunks:
        chunk.metadata["topic"]  = label
        chunk.metadata["source"] = filename

    print(f"[{label}]: {len(chunks)} chunks")
    all_chunks.extend(chunks)

# ==================== KIỂM TRA METADATA ====================
missing = [i for i, c in enumerate(all_chunks) if not c.metadata.get("topic")]
if missing:
    print(f"[CANH BAO] {len(missing)} chunks thieu topic, dang gan lai...")
    for i in missing:
        all_chunks[i].metadata["topic"] = "unknown"

print(f"\nTong: {len(all_chunks)} chunks, tat ca deu co topic metadata.")

# ==================== XÓA DB CŨ ====================
if os.path.exists(DB_DIR):
    shutil.rmtree(DB_DIR)
    print("Da xoa DB cu.")

# ==================== TẠO VECTOR DB ====================
embed_model = HuggingFaceEmbeddings(
    model_name="bkai-foundation-models/vietnamese-bi-encoder",
    encode_kwargs={"normalize_embeddings": True, "batch_size": 32}d
)

vector_db = Chroma.from_documents(
    documents=all_chunks,
    embedding=embed_model,
    persist_directory=DB_DIR,
    collection_metadata={"hnsw:space": "cosine"}
)

print(f"\nHoan tat! Da nap {len(all_chunks)} chunks vao DB.")
for filename in docx_files + excel_files + pdf_files:
    label = os.path.splitext(filename)[0].replace(" ", "_")
    count = sum(1 for c in all_chunks if c.metadata["topic"] == label)
    print(f"  [{label}]: {count} chunks")