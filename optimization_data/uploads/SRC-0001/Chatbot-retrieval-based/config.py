import warnings
import logging
import os
import joblib
from groq import Groq
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

warnings.filterwarnings("ignore")
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("chromadb").setLevel(logging.ERROR)
logging.getLogger("langchain").setLevel(logging.ERROR)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# ==================== CẤU HÌNH ====================
# Dùng đường dẫn tuyệt đối dựa theo vị trí file config.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GROQ_API_KEY   = os.getenv("GROQ_API_KEY")

DB_DIR         = os.path.join(BASE_DIR, "vector_db")
SVM_PATH       = os.path.join(BASE_DIR, "intent_model_svm.pkl")
CONFIDENCE_THR = 0.75
CHITCHAT_LABEL = "Giao_Tiep_Co_Ban"
if not GROQ_API_KEY:
    raise ValueError(
        "Chưa cấu hình GROQ_API_KEY trong biến môi trường."
    )
# ==================== KIỂM TRA FILE ====================
if not os.path.exists(SVM_PATH):
    raise FileNotFoundError(
        f"\n[LỖI] Không tìm thấy file model: {SVM_PATH}\n"
        f"Hãy chạy 'tfidf_retrieval.py' trước để tạo file 'intent_model_svm.pkl'."
    )

if not os.path.exists(DB_DIR):
    raise FileNotFoundError(
        f"\n[LỖI] Không tìm thấy vector DB: {DB_DIR}\n"
        f"Hãy chạy 'ingest_knowledge.py' trước để tạo vector database."
    )

# ==================== KHỞI TẠO ====================
llm = Groq(api_key=GROQ_API_KEY)

embed_model = HuggingFaceEmbeddings(
    model_name="bkai-foundation-models/vietnamese-bi-encoder",
    encode_kwargs={"normalize_embeddings": True, "batch_size": 32}
)

vector_db = Chroma(
    persist_directory=DB_DIR,
    embedding_function=embed_model,
    collection_metadata={"hnsw:space": "cosine"}
)

svm_pipeline = joblib.load(SVM_PATH)