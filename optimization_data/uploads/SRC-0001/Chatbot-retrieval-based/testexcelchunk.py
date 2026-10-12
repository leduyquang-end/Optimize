# -*- coding: utf-8 -*-
"""
chunk_excel.py — Đọc và chunk toàn bộ file xlsx trong thư mục data/
Chạy: python chunk_excel.py
"""

import os
import pandas as pd

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, "data")
excel_files = [f for f in os.listdir(DATA_DIR) if f.endswith((".xlsx", ".xls")) and not f.startswith("~$")]

if not excel_files:
    print(f"[LOI] Khong tim thay file .xlsx trong: {DATA_DIR}")
    exit(1)

print(f"Tim thay {len(excel_files)} file excel: {excel_files}\n")


def excel_sheet_to_text(df: pd.DataFrame, sheet_name: str) -> str:
    df = df.dropna(how="all")
    df = df.ffill(axis=0)
    df = df.map(lambda x: str(x).strip() if pd.notna(x) else "")
    df = df[df.apply(
        lambda row: sum(1 for v in row if v not in ("", "nan", "None")) >= 2,
        axis=1
    )]
    if df.empty:
        return ""
    headers   = [str(c).strip() for c in df.columns]
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


for filename in excel_files:
    file_path  = os.path.join(DATA_DIR, filename)
    all_sheets = pd.read_excel(file_path, sheet_name=None, header=0)

    print(f"{'='*60}")
    print(f"FILE: {filename}")
    print(f"{'='*60}")

    for sheet_name, df in all_sheets.items():
        text = excel_sheet_to_text(df, sheet_name)
        if not text.strip():
            continue

        chunks = [c.strip() for c in text.split("\n\n") if c.strip() and not c.strip().startswith("[Sheet:")]

        print(f"\nSheet: {sheet_name} → {len(chunks)} chunks\n")
        for i, chunk in enumerate(chunks, 1):
            print(f"── Chunk {i} ──")
            print(chunk)
            print()