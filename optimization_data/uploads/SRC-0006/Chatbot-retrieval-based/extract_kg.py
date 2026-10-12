import os
import json
import time
from config import llm, GROQ_MODEL
from ingest_kg import load_docx, chunk_by_article
from parse_kg import process_kg

TUPLE_DELIMITER = "<|>"
RECORD_DELIMITER = "##"
COMPLETION_DELIMITER = "<|COMPLETE|>"

ENTITY_TYPES = [
    "LOAI_HOC_BONG",
    "DIEU_KIEN",
    "GPA_RANGE",
    "RL_CONDITION",
    "CREDIT_CONDITION", 
    "MUC_HOC_BONG",
    "DOI_TUONG",
    "DON_VI",
    "QUY_TRINH",
]

GRAPH_EXTRACTION_PROMPT = """
-Mục tiêu-
Cho một đoạn văn bản về quy định học bổng tại Trường Đại học Thủy lợi (TLU),
hãy xác định tất cả các thực thể thuộc các loại được chỉ định và tất cả các
mối quan hệ giữa chúng.

-Các nguyên tắc chung-
+ Không suy diễn hoặc tự thêm thông tin ngoài văn bản.
+ Chỉ sử dụng thông tin có trong văn bản đầu vào.
+ Không bỏ sót bất kỳ điều kiện, giá trị hoặc thông tin quan trọng nào.
+ Ưu tiên trích xuất thông tin có cấu trúc (đặc biệt là số liệu).
+ BẮT BUỘC phát hiện và trích xuất đầy đủ các điều kiện liên quan đến tín chỉ, kể cả các trường hợp ngoại lệ, điều kiện rẽ nhánh.

-Các bước-
1. Xác định tất cả các thực thể. Với mỗi thực thể được xác định, trích xuất
các thông tin sau:
- entity_name: 
    + Tên của thực thể, viết hoa, dùng tiếng Việt.
    + Ngắn gọn, rõ ràng.
    + Nếu là điều kiện thì phải chứa số liệu (nếu có trong văn bản).
- entity_type: Một trong các loại sau: [{entity_types}]
- entity_description: 
    + Mô tả toàn diện về thuộc tính của thực thể trong ngữ cảnh quy định học bổng TLU.
    + Phải giữ nguyên số liệu, không làm mất thông tin quan trọng.
    + Nếu là điều kiện phức tạp (nhiều vế, ngoại lệ), phải mô tả đầy đủ logic.
Định dạng mỗi thực thể như sau:
("entity"{tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>{tuple_delimiter}<entity_description>)

QUY TẮC BẮT BUỘC ĐỐI VỚI CÁC ĐIỀU KIỆN:

- Nếu là điều kiện về GPA:
  + PHẢI biểu diễn dưới dạng số cụ thể
  + Ví dụ đúng: "GPA 3.20 - 3.59"

- Nếu là điều kiện về điểm rèn luyện:
  + PHẢI ghi rõ ngưỡng số
  + Ví dụ đúng: "RÈN LUYỆN ≥ 80"

**Quy tắc đặc biệt đối với số tín chỉ:**
- Trích xuất thành entity riêng.
- Ghi rõ số tín chỉ:
  + Ví dụ chuẩn: "TÍN CHỈ ≥ 15"
  + Nếu số tín chỉ tối đa ngành < 15 → ghi riêng, mô tả logic
  + Nếu học vượt hoặc tín chỉ tích lũy đủ → ghi rõ trong description
  + Nếu học kỳ cuối → ghi rõ tín chỉ tính theo học phần tốt nghiệp
- Phải tách các trường hợp: điều kiện chuẩn, điều kiện thay thế, ngoại lệ, học vượt, học kỳ cuối thành các entity riêng nếu có thể.

1b. Xử lý số tín chỉ sinh viên:
- Tạo entity cho số tín chỉ sinh viên đăng ký, ví dụ: 
  ("entity"{tuple_delimiter}SỐ TÍN CHỈ ĐĂNG KÝ{tuple_delimiter}DIEU_KIEN{tuple_delimiter}Sinh viên đăng ký 13 tín chỉ trong kỳ)
- Logic đánh giá: 
  + Nếu student_credits >= min_credits HOẶC student_credits >= max_credits_for_major → điều kiện tín chỉ đạt
  + Nếu student_credits < min_credits và student_credits < max_credits_for_major → chưa đủ điều kiện
- Ghi rõ trong relationship giữa học bổng và entity tín chỉ.

- PHẢI trích xuất đầy đủ tất cả các điều kiện xuất hiện trong văn bản:
  + GPA
  + Điểm rèn luyện
  + Số tín chỉ (QUAN TRỌNG)
  + Điều kiện ngoại lệ / điều kiện bổ sung
  + Điều kiện loại trừ (ví dụ: bị kỷ luật)

- KHÔNG được bỏ sót các điều kiện dạng:
  + "hoặc"
  + "nếu"
  + "trường hợp"
  + "ngoại lệ"

2. Từ các thực thể đã xác định ở bước 1, xác định tất cả các cặp
(source_entity, target_entity) có liên quan rõ ràng với nhau.
Với mỗi cặp thực thể có liên quan, trích xuất các thông tin sau:
- source_entity: tên thực thể nguồn, như đã xác định ở bước 1
- target_entity: tên thực thể đích, như đã xác định ở bước 1
- relationship_description: giải thích lý do thực thể nguồn và thực thể đích
  có liên quan với nhau trong ngữ cảnh quy định học bổng
- relationship_strength: điểm số từ 1 đến 10 thể hiện độ mạnh của mối quan hệ
Định dạng mỗi mối quan hệ như sau:
("relationship"{tuple_delimiter}<source_entity>{tuple_delimiter}<target_entity>{tuple_delimiter}<relationship_description>{tuple_delimiter}<relationship_strength>)

3. Trả về kết quả dưới dạng một danh sách duy nhất gồm tất cả các thực thể
và mối quan hệ đã xác định ở bước 1 và 2.
Sử dụng **{record_delimiter}** làm ký tự phân cách danh sách.

4. Khi hoàn thành, xuất {completion_delimiter}

######################
-Ví dụ-
######################
Ví dụ 1:
Entity_types: LOAI_HOC_BONG,DIEU_KIEN,MUC_HOC_BONG
Text:
Học bổng loại Giỏi dành cho sinh viên có điểm trung bình học tập đạt loại
giỏi trở lên và điểm rèn luyện đạt loại tốt trở lên. Học bổng loại Giỏi có
giá trị bằng 110% mức học phí tín chỉ đại học nhân với số tín chỉ tính học
bổng của học kỳ.
######################
Output:
("entity"{tuple_delimiter}HỌC BỔNG LOẠI GIỎI{tuple_delimiter}LOAI_HOC_BONG{tuple_delimiter}Học bổng KKHT mức giỏi dành cho sinh viên đạt điểm học tập loại giỏi trở lên và điểm rèn luyện loại tốt trở lên)
{record_delimiter}
("entity"{tuple_delimiter}ĐIỂM TRUNG BÌNH HỌC TẬP LOẠI GIỎI{tuple_delimiter}DIEU_KIEN{tuple_delimiter}Điều kiện học lực: điểm trung bình học tập đạt loại giỏi trở lên trong kỳ xét học bổng)
{record_delimiter}
("entity"{tuple_delimiter}ĐIỂM RÈN LUYỆN LOẠI TỐT{tuple_delimiter}DIEU_KIEN{tuple_delimiter}Điều kiện rèn luyện: điểm rèn luyện đạt loại tốt trở lên trong kỳ xét học bổng)
{record_delimiter}
("entity"{tuple_delimiter}110% HỌC PHÍ TÍN CHỈ{tuple_delimiter}MUC_HOC_BONG{tuple_delimiter}Giá trị học bổng loại giỏi bằng 110% mức học phí tín chỉ nhân số tín chỉ học kỳ)
{record_delimiter}
("relationship"{tuple_delimiter}HỌC BỔNG LOẠI GIỎI{tuple_delimiter}ĐIỂM TRUNG BÌNH HỌC TẬP LOẠI GIỎI{tuple_delimiter}Học bổng loại giỏi yêu cầu điểm trung bình học tập đạt loại giỏi trở lên{tuple_delimiter}9)
{record_delimiter}
("relationship"{tuple_delimiter}HỌC BỔNG LOẠI GIỎI{tuple_delimiter}ĐIỂM RÈN LUYỆN LOẠI TỐT{tuple_delimiter}Học bổng loại giỏi yêu cầu điểm rèn luyện đạt loại tốt trở lên{tuple_delimiter}9)
{record_delimiter}
("relationship"{tuple_delimiter}HỌC BỔNG LOẠI GIỎI{tuple_delimiter}110% HỌC PHÍ TÍN CHỈ{tuple_delimiter}Học bổng loại giỏi có giá trị 110% mức học phí tín chỉ{tuple_delimiter}10)
<|COMPLETE|>

Ví dụ 2:
######################
Entity_types: LOAI_HOC_BONG,DIEU_KIEN,MUC_HOC_BONG
Text:
Học bổng loại Khá dành cho sinh viên có điểm trung bình học tập ≥ 3.2 và điểm rèn luyện ≥ 80. 
Số tín chỉ tối thiểu là 15. Nếu số tín chỉ tối đa ngành < 15 thì xét theo số tín chỉ tối đa. 
Sinh viên đăng ký 13 tín chỉ trong kỳ.

######################
Output:
("entity"{tuple_delimiter}HỌC BỔNG LOẠI KHÁ{tuple_delimiter}LOAI_HOC_BONG{tuple_delimiter}Học bổng dành cho sinh viên đạt GPA ≥ 3.2 và điểm rèn luyện ≥ 80)
{record_delimiter}
("entity"{tuple_delimiter}GPA ≥ 3.2{tuple_delimiter}DIEU_KIEN{tuple_delimiter}Điều kiện học tập: GPA ≥ 3.2)
{record_delimiter}
("entity"{tuple_delimiter}RÈN LUYỆN ≥ 80{tuple_delimiter}DIEU_KIEN{tuple_delimiter}Điều kiện rèn luyện: điểm rèn luyện ≥ 80)
{record_delimiter}
("entity"{tuple_delimiter}TÍN CHỈ ≥ 15{tuple_delimiter}DIEU_KIEN{tuple_delimiter}Điều kiện số tín chỉ chuẩn: ≥ 15)
{record_delimiter}
("entity"{tuple_delimiter}TÍN CHỈ TỐI ĐA NGÀNH 14{tuple_delimiter}DIEU_KIEN{tuple_delimiter}Nếu số tín chỉ tối đa ngành < 15 thì xét theo số tín chỉ tối đa = 14)
{record_delimiter}
("entity"{tuple_delimiter}SỐ TÍN CHỈ ĐĂNG KÝ 13{tuple_delimiter}DIEU_KIEN{tuple_delimiter}Sinh viên đăng ký 13 tín chỉ trong kỳ)
{record_delimiter}
("relationship"{tuple_delimiter}HỌC BỔNG LOẠI KHÁ{tuple_delimiter}GPA ≥ 3.2{tuple_delimiter}Học bổng yêu cầu GPA ≥ 3.2{tuple_delimiter}9)
{record_delimiter}
("relationship"{tuple_delimiter}HỌC BỔNG LOẠI KHÁ{tuple_delimiter}RÈN LUYỆN ≥ 80{tuple_delimiter}Học bổng yêu cầu điểm rèn luyện ≥ 80{tuple_delimiter}9)
{record_delimiter}
("relationship"{tuple_delimiter}HỌC BỔNG LOẠI KHÁ{tuple_delimiter}TÍN CHỈ ≥ 15{tuple_delimiter}Kiểm tra điều kiện số tín chỉ: student_credits phải ≥ 15 HOẶC ≥ max tín chỉ ngành{tuple_delimiter}10)
{record_delimiter}
("relationship"{tuple_delimiter}HỌC BỔNG LOẠI KHÁ{tuple_delimiter}TÍN CHỈ TỐI ĐA NGÀNH 14{tuple_delimiter}Kiểm tra điều kiện số tín chỉ theo ngành{tuple_delimiter}10)
{record_delimiter}
("relationship"{tuple_delimiter}HỌC BỔNG LOẠI KHÁ{tuple_delimiter}SỐ TÍN CHỈ ĐĂNG KÝ 13{tuple_delimiter}So sánh số tín chỉ sinh viên đăng ký với điều kiện để đánh giá đủ điều kiện xét học bổng{tuple_delimiter}10)
<|COMPLETE|>

######################
-Dữ liệu thực tế-
######################
Entity_types: {entity_types}
Text: {input_text}
######################
Output:"""


CONTINUE_PROMPT = "NHIỀU thực thể và mối quan hệ đã bị bỏ sót trong lần trích xuất vừa rồi. Hãy nhớ CHỈ xuất các thực thể khớp với bất kỳ loại nào đã được trích xuất trước đó. Thêm chúng bên dưới theo cùng định dạng:\n"
LOOP_PROMPT = "Có vẻ như một số thực thể và mối quan hệ vẫn có thể bị bỏ sót. Hãy trả lời YES | NO nếu vẫn còn thực thể hoặc mối quan hệ cần được thêm vào.\n"


def call_llm(prompt: str) -> str:
    response = llm.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


def extract_chunk(chunk: str, max_loops: int = 1) -> str:
    prompt = GRAPH_EXTRACTION_PROMPT.format(
        entity_types=", ".join(ENTITY_TYPES),
        tuple_delimiter=TUPLE_DELIMITER,
        record_delimiter=RECORD_DELIMITER,
        completion_delimiter=COMPLETION_DELIMITER,
        input_text=chunk,
    )
    output = call_llm(prompt)
    time.sleep(3)

    for _ in range(max_loops):
        answer = call_llm(output + "\n\n" + LOOP_PROMPT).upper()
        time.sleep(3)
        if "YES" not in answer:
            break
        output += "\n" + call_llm(output + "\n\n" + CONTINUE_PROMPT)
        time.sleep(3)

    return output


def extract_all(docx_path: str) -> list[dict]:
    text = load_docx(docx_path)
    chunks = chunk_by_article(text)

    results = []
    for chunk in chunks:
        print(f"Extracting chunk {chunk['chunk_id']}/{len(chunks)}...")
        results.append({
            "chunk_id":   chunk["chunk_id"],
            "content":    chunk["content"],
            "raw_output": extract_chunk(chunk["content"]),
        })
        time.sleep(3)

    return results


if __name__ == "__main__":
    # EXTRACT
    if os.path.exists("kg_raw.json"):
        with open("kg_raw.json", "r", encoding="utf-8") as f:
            results = json.load(f)
        print("Loaded kg_raw.json")
    else:
        results = extract_all("Hoc_Bong_Hoc_Tap.docx")
        with open("kg_raw.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print("Đã lưu kg_raw.json")

    # PARSE + DEDUP + NORMALIZE (toàn bộ pipeline)
    entities, relationships = process_kg(results)

    with open("kg_parsed.json", "w", encoding="utf-8") as f:
        json.dump({
            "entities":      entities,
            "relationships": relationships,
        }, f, ensure_ascii=False, indent=2)
    print("Đã lưu kg_parsed.json")

    print(f"\nTổng entities: {len(entities)}")
    for e in entities:
        print(f"  {e['name']} ({e['type']})")

    print(f"\nTổng relationships: {len(relationships)}")
    for r in relationships:
        print(f"  {r['source']} --> {r['target']} (w={r['strength']})")