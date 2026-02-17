import json
import os
import re

INPUT_FILE = "law_structured.txt"
OUTPUT_FILE = "output.json"

def strip_tatweel(text):
    """Remove Arabic tatweel (kashida) character from text."""
    return text.replace("ـ", "")

CHAPTER_ORDINALS = (
    "الأول", "الثاني", "الثالث", "الرابع", "الخامس",
    "السادس", "السابع", "الثامن", "التاسع", "العاشر"
)

def is_chapter_line(text):
    """Check if line is a chapter heading, ignoring tatweel."""
    clean = strip_tatweel(text)
    if not clean.startswith("الفصل"):
        return False
    return any(ordinal in clean for ordinal in CHAPTER_ORDINALS)

def is_toc_line(raw_line):
    """TOC lines: start with space + chapter keyword, or uf0da bullet."""
    stripped = raw_line.rstrip()
    return bool(re.match(r"^[\uf0da]\s*", stripped)) or \
           (stripped.startswith(" ") and is_chapter_line(stripped.strip()))

ARTICLE_PATTERN = re.compile(r"^المادة\s+[\d٠-٩]+")
PREAMBLE_START  = re.compile(r"^نحن\s")
PREAMBLE_END    = re.compile(r"قررنا المصادقة على القانون الآتي")


def _flush_article(law, current_chapter, current_article):
    """Save current_article into the right bucket (chapter or top-level)."""
    if current_article is None:
        return
    if current_chapter is not None:
        current_chapter["مواد"].append(current_article)
    else:
        # No chapter exists → store at top level
        law["مواد"].append(current_article)


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
        "فصول": [],
        "مواد": []   # top-level articles used only when there are no chapters
    }

    current_chapter = None
    current_article = None
    section = "metadata"

    for line in lines:
        text = line.rstrip("\n")
        stripped = text.strip()

        if not stripped or re.match(r"^[•\s]+$", stripped):
            continue

        clean = re.sub(r"^[•\s]+", "", stripped).strip()
        clean = re.sub(r"[•]+$", "", clean).strip()
        if not clean:
            continue

        # ── TOC detection (uses raw line to detect leading space) ──────────
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
            elif is_chapter_line(clean):
                section = "body"
                # fall through to body handling below
            elif ARTICLE_PATTERN.match(clean):
                # Law with no preamble/TOC — jump straight into body
                section = "body"
                # fall through to body handling below
            elif section == "metadata":
                if "قانون رقم" in clean and "بتنظیم" in clean:
                    continue
                parse_metadata_line(clean, law)
                continue
            else:
                continue

        if section == "preamble":
            if "قانون رقم" in clean \
                    and "نحن" not in clean and "وعلى" not in clean:
                continue
            law["دیباجة"].append(clean)
            if PREAMBLE_END.search(clean):
                section = "body"
            continue

        if section == "body":
            # Skip repeated page-header title lines
            if "قانون رقم" in clean and not ARTICLE_PATTERN.match(clean) \
                    and not is_chapter_line(clean):
                continue

            # ── Chapter heading ────────────────────────────────────────────
            if is_chapter_line(clean):
                _flush_article(law, current_chapter, current_article)
                current_article = None
                if current_chapter:
                    law["فصول"].append(current_chapter)
                current_chapter = {"عنوان_الفصل": clean, "مواد": []}

            # ── Article heading ────────────────────────────────────────────
            elif ARTICLE_PATTERN.match(clean):
                _flush_article(law, current_chapter, current_article)
                current_article = {"عنوان_المادة": clean, "نص": []}

            # ── Article body text ──────────────────────────────────────────
            elif current_article is not None:
                current_article["نص"].append(clean)

            # ── Extra chapter title continuation (no article yet) ──────────
            elif current_chapter and current_article is None:
                current_chapter["عنوان_الفصل"] += " - " + clean

    # ── Flush the very last article and chapter ────────────────────────────
    _flush_article(law, current_chapter, current_article)
    if current_chapter:
        law["فصول"].append(current_chapter)

    # ── Remove empty top-level مواد key if not used ────────────────────────
    if not law["مواد"]:
        del law["مواد"]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(law, f, ensure_ascii=False, indent=4)

    total_chapters = len(law.get("فصول", []))
    total_articles_in_chapters = sum(len(ch["مواد"]) for ch in law.get("فصول", []))
    total_articles_top = len(law.get("مواد", []))
    total_articles = total_articles_in_chapters + total_articles_top

    print(f"تم التحويل بنجاح: {INPUT_FILE} -> {OUTPUT_FILE}")
    if total_chapters:
        print(f"عدد الفصول: {total_chapters}")
    else:
        print("لا توجد فصول — المواد مباشرة في المستوى الأول")
    print(f"عدد المواد: {total_articles}")
    return law


def parse_metadata_line(text, law):
    if "بطاقة التشریع" in text:
        text = text.replace("بطاقة التشریع", "").strip()

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