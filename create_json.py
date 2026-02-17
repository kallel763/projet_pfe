import json
import os
import re

INPUT_FILE = "law_structured.txt"
OUTPUT_FILE = "output19.json"

# ── Constants ──────────────────────────────────────────────────────────────

CHAPTER_ORDINALS = (
    "الأول", "الثاني", "الثالث", "الرابع", "الخامس",
    "السادس", "السابع", "الثامن", "التاسع", "العاشر",
)

def strip_tatweel(text):
    """Remove Arabic tatweel (kashida) ـ from text."""
    return text.replace("ـ", "")

def is_section_heading(text):
    """
    Returns True if the line is a الفصل or الباب heading.
    Handles tatweel, and requires an ordinal word to be present.
    """
    clean = strip_tatweel(text).strip()
    for keyword in ("الفصل", "الباب"):
        if clean.startswith(keyword):
            if any(ordinal in clean for ordinal in CHAPTER_ORDINALS):
                return True
    return False

def is_toc_line(raw_line):
    """
    TOC lines start with a leading space or uf0da bullet, followed by a
    section keyword OR 'مواد الاصدار'.
    """
    stripped = raw_line.rstrip()
    if re.match(r"^[\uf0da]\s*", stripped):
        return True
    if stripped.startswith(" "):
        inner = stripped.strip()
        if is_section_heading(inner):
            return True
        if re.match(r"^مواد\s", inner):   # e.g. مواد الاصدار
            return True
    return False

# Article heading: handles all these real-world formats:
#   المادة 1                 (digit)
#   المادة ١٢               (Arabic-Indic digit)
#   المادة - 1              (dash before digit, law18 style)
#   المادة 1 - إصدار        (digit then label)
#   المادة الحادية والعشرون  (word-form ordinal)
ARTICLE_PATTERN = re.compile(
    r"^المادة\s*"
    r"(-\s*[\d٠-٩]+|[\d٠-٩]+|ال\S+(\s+\S+){0,3})"
)

def is_article_line(text):
    return bool(ARTICLE_PATTERN.match(text.strip()))

PREAMBLE_START        = re.compile(r"^نحن\s")
PREAMBLE_END_EXPLICIT = re.compile(r"قررنا المصادقة على القانون")


# ── Helpers ────────────────────────────────────────────────────────────────

def _flush_article(law, current_chapter, current_article):
    """Append current_article to the right bucket."""
    if current_article is None:
        return
    if current_chapter is not None:
        current_chapter["مواد"].append(current_article)
    else:
        law["مواد"].append(current_article)


# ── Main parser ────────────────────────────────────────────────────────────

def text_to_json():
    if not os.path.exists(INPUT_FILE):
        print(f"الملف غير موجود: {INPUT_FILE}")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    law = {
        "بطاقة_التشریع": {},
        "فھرس":  [],
        "دیباجة": [],
        "فصول":  [],
        "مواد":  [],   # top-level articles when there are no sections
    }

    current_chapter = None
    current_article = None
    section = "metadata"

    for line in lines:
        text    = line.rstrip("\n")
        stripped = text.strip()

        if not stripped or re.match(r"^[•\s]+$", stripped):
            continue

        clean = re.sub(r"^[•\s]+", "", stripped).strip()
        clean = re.sub(r"[•]+$",   "", clean).strip()
        if not clean:
            continue

        is_sec = is_section_heading(clean)
        is_art = is_article_line(clean)

        # ── TOC ────────────────────────────────────────────────────────────
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
                # fall through to body handling
            elif section == "metadata":
                if "قانون رقم" in clean:
                    continue
                parse_metadata_line(clean, law)
                continue
            else:
                continue

        # ── Preamble ───────────────────────────────────────────────────────
        if section == "preamble":
            # Skip repeated page-header title lines
            if "قانون رقم" in clean \
                    and "نحن" not in clean and "وعلى" not in clean:
                continue

            if PREAMBLE_END_EXPLICIT.search(clean):
                law["دیباجة"].append(clean)
                section = "body"
                continue

            # Fallback: section heading ends the preamble even if
            # قررنا المصادقة was cut off by a page break
            if is_sec:
                section = "body"
                # fall through — don't skip this line
            else:
                law["دیباجة"].append(clean)
                continue

        # ── Body ───────────────────────────────────────────────────────────
        if section == "body":
            # Skip repeated page-header title lines
            if "قانون رقم" in clean and not is_art and not is_sec:
                continue

            if is_sec:
                # New section (الفصل / الباب)
                _flush_article(law, current_chapter, current_article)
                current_article = None
                if current_chapter:
                    law["فصول"].append(current_chapter)
                current_chapter = {"عنوان_الفصل": clean, "مواد": []}

            elif is_art:
                # New article heading
                _flush_article(law, current_chapter, current_article)
                current_article = {"عنوان_المادة": clean, "نص": []}

            elif current_article is not None:
                # Body text of the current article
                current_article["نص"].append(clean)

            elif current_chapter is not None and current_article is None:
                # Subtitle / label line immediately after a section heading
                # Append only if it looks like a short title (≤ 60 chars)
                # to avoid swallowing long prose into the section name
                if len(clean) <= 60:
                    current_chapter["عنوان_الفصل"] += " - " + clean

    # Flush the very last article and chapter
    _flush_article(law, current_chapter, current_article)
    if current_chapter:
        law["فصول"].append(current_chapter)

    # Remove empty top-level مواد key if not used
    if not law["مواد"]:
        del law["مواد"]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(law, f, ensure_ascii=False, indent=4)

    total_chapters = len(law.get("فصول", []))
    total_arts_in  = sum(len(ch["مواد"]) for ch in law.get("فصول", []))
    total_arts_top = len(law.get("مواد", []))
    total_articles = total_arts_in + total_arts_top

    print(f"تم التحويل بنجاح: {INPUT_FILE} -> {OUTPUT_FILE}")
    if total_chapters:
        print(f"عدد الأبواب/الفصول: {total_chapters}")
    else:
        print("لا توجد أبواب/فصول — المواد مباشرة في المستوى الأول")
    print(f"عدد المواد: {total_articles}")
    return law


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


text_to_json()