import json
import os
import re

INPUT_FILE = "law_structured.txt"
OUTPUT_FILE = "output.json"

TOC_PATTERN = re.compile(r"^\uf0da")
CHAPTER_PATTERN = re.compile(r"^الفصل\s+(الأول|الثاني|الثالث|الرابع|الخامس|السادس|السابع|الثامن|التاسع|العاشر)")
ARTICLE_PATTERN = re.compile(r"^المادة\s+[\d٠-٩]+")
PREAMBLE_START = re.compile(r"^نحن\s")
PREAMBLE_END = re.compile(r"قررنا المصادقة على القانون الآتي")


def text_to_json():
    if not os.path.exists(INPUT_FILE):
        print(f"الملف غير موجود: {INPUT_FILE}")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    law = {
        "بطاقة_التشریع": {},
        "فھرس": [],
        "دیباجة": [],
        "فصول": []
    }

    current_chapter = None
    current_article = None
    section = "metadata"

    for line in lines:
        text = line.strip()
        if not text or re.match(r"^[•\s]+$", text):
            continue

        clean = re.sub(r"^[•\s]+", "", text).strip()
        clean = re.sub(r"[•]+$", "", clean).strip()
        if not clean:
            continue

        if TOC_PATTERN.match(text):
            toc_text = re.sub(r"^\uf0da\s*", "", text).strip()
            law["فھرس"].append(toc_text)
            section = "toc"
            continue

        if section == "metadata" or section == "toc":
            if PREAMBLE_START.match(clean):
                section = "preamble"
                law["دیباجة"].append(clean)
                continue
            elif CHAPTER_PATTERN.match(clean):
                section = "body"
            elif section == "metadata":
                parse_metadata_line(clean, law)
                continue
            else:
                continue

        if section == "preamble":
            law["دیباجة"].append(clean)
            if PREAMBLE_END.search(clean):
                section = "body"
            continue

        if section == "body":
            if CHAPTER_PATTERN.match(clean):
                if current_article and current_chapter:
                    current_chapter["مواد"].append(current_article)
                    current_article = None
                if current_chapter:
                    law["فصول"].append(current_chapter)

                current_chapter = {
                    "عنوان_الفصل": clean,
                    "مواد": []
                }
                current_article = None

            elif ARTICLE_PATTERN.match(clean):
                if current_article and current_chapter:
                    current_chapter["مواد"].append(current_article)

                current_article = {
                    "عنوان_المادة": clean,
                    "نص": []
                }

            elif current_article:
                current_article["نص"].append(clean)

            elif current_chapter and not current_article:
                current_chapter["عنوان_الفصل"] += " - " + clean

    if current_article and current_chapter:
        current_chapter["مواد"].append(current_article)
    if current_chapter:
        law["فصول"].append(current_chapter)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(law, f, ensure_ascii=False, indent=4)

    total_chapters = len(law["فصول"])
    total_articles = sum(len(ch["مواد"]) for ch in law["فصول"])
    print(f"تم التحويل بنجاح: {INPUT_FILE} -> {OUTPUT_FILE}")
    print(f"عدد الفصول: {total_chapters}")
    print(f"عدد المواد: {total_articles}")


def parse_metadata_line(text, law):
    if "بطاقة التشریع" in text:
        text = text.replace("بطاقة التشریع", "").strip()

    pairs = re.findall(r"([\u0600-\u06FF\s]+?):\s*([^:]+?)(?=\s+[\u0600-\u06FF]+:|$)", text)
    if pairs:
        for key, value in pairs:
            law["بطاقة_التشریع"][key.strip()] = value.strip()
    elif ":" in text:
        key, value = text.split(":", 1)
        law["بطاقة_التشریع"][key.strip()] = value.strip()


text_to_json()