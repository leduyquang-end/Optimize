import os
import pandas as pd
import numpy as np
import joblib
from underthesea import word_tokenize
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import SVC
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report

# ==================== CẤU HÌNH ====================
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
FILE_PATH  = os.path.join(BASE_DIR, "question.xlsx")
MODEL_PATH = os.path.join(BASE_DIR, "intent_model_svm.pkl")

if not os.path.exists(FILE_PATH):
    raise FileNotFoundError(
        f"\n[LỖI] Không tìm thấy file: {FILE_PATH}\n"
        f"Hãy đặt 'question.xlsx' cùng thư mục với script này."
    )

# ==================== TIỀN XỬ LÝ ====================
def preprocess_text(text):
    if not isinstance(text, str):
        return ""
    return word_tokenize(text.lower(), format="text")

# ==================== LOAD DATA ====================
df = pd.read_excel(FILE_PATH)

print(f"Columns : {list(df.columns)}")
print(f"Tổng số mẫu: {len(df)}")
print(f"\nPhân bố Intent:")
print(df["Intent"].value_counts().to_string())

df["text_processed"] = df["Text"].apply(preprocess_text)

# ==================== TRAIN / TEST SPLIT ====================
X_train, X_test, y_train, y_test = train_test_split(
    df["text_processed"],
    df["Intent"],
    test_size=0.2,
    random_state=42,
    stratify=df["Intent"]
)

print(f"\nTrain: {len(X_train)} mẫu | Test: {len(X_test)} mẫu")

# ==================== PIPELINE ====================
model_pipeline = Pipeline([
    ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=5000)),
    ("svm",   SVC(kernel="linear", C=1.0, probability=True))
])

print("\nĐang train model...")
model_pipeline.fit(X_train, y_train)

# ==================== ĐÁNH GIÁ ====================
y_pred = model_pipeline.predict(X_test)
print("\nClassification Report:")
print(classification_report(y_test, y_pred))

# ==================== LƯU MODEL ====================
joblib.dump(model_pipeline, MODEL_PATH)
print(f"\n✅ Đã lưu model vào: {MODEL_PATH}")
print(f"Các topic đã học: {list(model_pipeline.classes_)}")