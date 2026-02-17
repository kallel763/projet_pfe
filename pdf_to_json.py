import pdfplumber
from bidi.algorithm import get_display
import arabic_reshaper
import unicodedata
import re
import json
import os

# ══════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════
PDF_INPUT = "law19.pdf"
OUTPUT_JSON = "output19.json"

# ══════════════════════════════════════════
# STEP 1: EXTRACT TEXT FROM PDF
# ══════════════════════════════════════════
def extract_text(pdf_path):
    print("📄 Step 1: Extracting text from PDF...")
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    print("✅ Text extracted successfully")
    return text

# ══════════════════════════════════════════
# STEP 2: FIX ARABIC BIDI + RESHAPING
# ══════════════════════════════════════════
def fix_arabic(text):
    print("🔤 Step 2: Fixing Arabic text (reshape + bidi)...")
    reshaped_text = arabic_reshaper.reshape(text)
    fixed_text = get_display(reshaped_text)
    print("✅ Arabic text corrected")
    return fixed_text

# ══════════════════════════════════════════
# STEP 3: NORMALIZE UNICODE + DIGITS
# ══════════════════════════════════════════
def normalize_text(text):
    print("🔧 Step 3: Normalizing Unicode...")
    text = unicodedata.normalize("NFKC", text)

    arabic_digits = {
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
        "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9"
    }
    for k, v in arabic_digits.items():
        text = text.replace(k, v)

    print("✅ Unicode normalization done")
    return text

# ══════════════════════════════════════════
# STEP 4: CLEAN TEXT
# ══════════════════════════════════════════
def clean_text(text):
    print("🧹 Step 4: Cleaning text...")
    text = unicodedata.normalize("NFKC", text)

    # Remove almeezan URL + page number
    text = re.sub(r'https?://www\.almeezan\.qa/\S+\s*\d+/\d+', '', text)

    # Remove repeated law title + date on each page
    text = re.sub(
        r'.*(?:ﻗﺎﻧﻮﻧ|قانون)\s*(?:ﺭﻗﻡ|رقم)\s*\(13\)\s*(?:ﻟﺳﻧﺔ|لسنة)\s*2024\s*(?:ﺑﺷﺄﻥ|بشأن).*?(?:10[:/]02[:/]2026|10:41).*',
        '', text
    )
    text = re.sub(
        r'.*(?:ﻗﺎﻧﻮﻧ|قانون)\s*(?:ﺭﻗﻡ|رقم)\s*\(13\)\s*(?:ﻟﺳﻧﺔ|لسنة)\s*2024\s*(?:ﺑﺷﺄﻥ|بشأن).*(?:ﺍﻟﻌﺎﻣﺔ|العامة).*\n?',
        '', text
    )

    # Remove standalone date/time
    text = re.sub(r'\d{2}/\d{2}/\d{4}\s*\d{1,2}:\d{2}', '', text)

    # Remove footer
    text = re.sub(r'.*الرجاء\s+عدم\s+اعتبار.*', '', text)
    text = re.sub(r'.*ﺍﻟﺭﺟﺎﺀ\s+.*(?:ﺭﺳﻣﯾﺔ|رسمية).*', '', text)
    text = re.sub(r'©.*$', '', text, flags=re.MULTILINE)

    # Clean up whitespace
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    print(f"✅ Cleaned text: {len(text)} characters")
    return text

# ══════════════════════════════════════════
# STEP 5: CREATE JSON
# ══════════════════════════════════════════

CHAPTER_ORDINALS = (
    "الأول", "الثاني", "الثالث", "الرابع", "الخامس",
    "السادس", "السابع", "الثامن", "التاسع", "العاشر",
)

def strip_tatweel(text):
    return text.replace("ـ", "")

def is_section_heading(text):
    clean = strip_tatweel(text).strip()
    for keyword in ("الفصل", "الباب"):
        if clean.startswith(keyword):
            if any(ordinal in clean for ordinal in CHAPTER_ORDINALS):
                return True
    return False

def is_toc_line(raw_line):
    stripped = raw_line.rstrip()
    if re.match(r"^[\uf0da]\s*", stripped):
        return True
    if stripped.startswith(" "):
        inner = stripped.strip()
        if is_section_heading(inner):
            return True
        if re.match(r"^مواد\s", inner):
            return True
    return False

ARTICLE_PATTERN = re.compile(
    r"^المادة\s*"
    r"(-\s*[\d٠-٩]+|[\d٠-٩]+|ال\S+(\s+\S+){0,3})"
)

def is_article_line(text):
    return bool(ARTICLE_PATTERN.match(text.strip()))

PREAMBLE_START        = re.compile(r"^نحن\s")
PREAMBLE_END_EXPLICIT = re.compile(r"قررنا المصادقة على القانون")

def _flush_article(law, current_chapter, current_article):
    if current_article is None:
        return
    if current_chapter is not None:
        current_chapter["مواد"].append(current_article)
    else:
        law["مواد"].append(current_article)

def parse_metadata_line(text, law):
    text = re.sub(r"بطاقة التشر[یي]ع", "", text).strip()
    pairs = re.findall(
        r"([\u0600-\u06FF\s]+?):\s*([^:]+?)(?=\s+[\u0600-\u06FF]+:|$)", text
    )
    if pairs:
        for key, value in pairs:
            law["بطاقة_التشریع"][key.strip()] = value.strip()
    elif ":" in text:
        key, value = text.split(":", 1)
        law["بطاقة_التشریع"][key.strip()] = value.strip()

def create_json(structured_text, output_path):
    print("📦 Step 5: Creating JSON...")

    lines = structured_text.split("\n")

    law = {
        "بطاقة_التشریع": {},
        "فھرس":  [],
        "دیباجة": [],
        "فصول":  [],
        "مواد":  [],
    }

    current_chapter = None
    current_article = None
    section = "metadata"

    for raw_line in lines:
        text    = raw_line.rstrip("\n")
        stripped = text.strip()

        if not stripped or re.match(r"^[•\s]+$", stripped):
            continue

        clean = re.sub(r"^[•\s]+", "", stripped).strip()
        clean = re.sub(r"[•]+$",   "", clean).strip()
        if not clean:
            continue

        is_sec = is_section_heading(clean)
        is_art = is_article_line(clean)

        # ── TOC
        if section in ("metadata", "toc"):
            if is_toc_line(text):
                toc_text = re.sub(r"^[\uf0da\s]+", "", text).strip()
                law["فھرس"].append(toc_text)
                section = "toc"
                continue

        if section in ("metadata", "toc"):
            if PREAMBLE_START.match(clean):
                section = "preamble"
                law["دیباجة"].append(clean)
                continue
            elif is_sec or is_art:
                section = "body"
            elif section == "metadata":
                if "قانون رقم" in clean:
                    continue
                parse_metadata_line(clean, law)
                continue
            else:
                continue

        # ── Preamble
        if section == "preamble":
            if "قانون رقم" in clean \
                    and "نحن" not in clean and "وعلى" not in clean:
                continue

            if PREAMBLE_END_EXPLICIT.search(clean):
                law["دیباجة"].append(clean)
                section = "body"
                continue

            if is_sec:
                section = "body"
            else:
                law["دیباجة"].append(clean)
                continue

        # ── Body
        if section == "body":
            if "قانون رقم" in clean and not is_art and not is_sec:
                continue

            if is_sec:
                _flush_article(law, current_chapter, current_article)
                current_article = None
                if current_chapter:
                    law["فصول"].append(current_chapter)
                current_chapter = {"عنوان_الفصل": clean, "مواد": []}

            elif is_art:
                _flush_article(law, current_chapter, current_article)
                current_article = {"عنوان_المادة": clean, "نص": []}

            elif current_article is not None:
                current_article["نص"].append(clean)

            elif current_chapter is not None and current_article is None:
                if len(clean) <= 60:
                    current_chapter["عنوان_الفصل"] += " - " + clean

    # Flush last article and chapter
    _flush_article(law, current_chapter, current_article)
    if current_chapter:
        law["فصول"].append(current_chapter)

    if not law["مواد"]:
        del law["مواد"]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(law, f, ensure_ascii=False, indent=4)

    total_chapters = len(law.get("فصول", []))
    total_arts_in  = sum(len(ch["مواد"]) for ch in law.get("فصول", []))
    total_arts_top = len(law.get("مواد", []))
    total_articles = total_arts_in + total_arts_top

    print(f"✅ JSON created: {output_path}")
    if total_chapters:
        print(f"   Chapters: {total_chapters}")
    else:
        print("   No chapters — articles at top level")
    print(f"   Articles: {total_articles}")

    return law

# ══════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════
def main():
    print("=" * 50)
    print("  LAW PDF → JSON PIPELINE")
    print("=" * 50)
    PDF_INPUT = "law19.pdf"
    if not os.path.exists(PDF_INPUT):
        print(f"❌ PDF not found: {PDF_INPUT}")
        return

    # Step 1: Extract
    raw_text = extract_text(PDF_INPUT)

    # Step 2: Fix Arabic
    fixed = fix_arabic(raw_text)

    # Step 3: Normalize
    normalized = normalize_text(fixed)

    # Step 4: Clean
    cleaned = clean_text(normalized)

    # Step 5: Create JSON
    law = create_json(cleaned, OUTPUT_JSON)

    print("\n" + "=" * 50)
    print("  ✅ PIPELINE COMPLETE")
    print("=" * 50)

if __name__ == "__main__":
    main()