import re
import unicodedata

# ==========================================
# 1️⃣ LOAD RAW TEXT
# ==========================================
with open("law_raw.txt", "r", encoding="utf-8") as f:
    text = f.read()

text = unicodedata.normalize("NFKC", text)

# ==========================================
# 2️⃣ CLEANING PATTERNS
# ==========================================

# --- A) Remove the almeezan URL + page number (e.g., "https://...ar 1/7") ---
text = re.sub(r'https?://www\.almeezan\.qa/\S+\s*\d+/\d+', '', text)

# --- B) Remove the repeated law title + date on each page ---
text = re.sub(
    r'.*(?:ﻗﺎﻧﻮﻧ|قانون)\s*(?:ﺭﻗﻡ|رقم)\s*\(13\)\s*(?:ﻟﺳﻧﺔ|لسنة)\s*2024\s*(?:ﺑﺷﺄﻥ|بشأن).*?(?:10[:/]02[:/]2026|10:41).*',
    '',
    text
)
text = re.sub(
    r'.*(?:ﻗﺎﻧﻮﻧ|قانون)\s*(?:ﺭﻗﻡ|رقم)\s*\(13\)\s*(?:ﻟﺳﻧﺔ|لسنة)\s*2024\s*(?:ﺑﺷﺄﻥ|بشأن).*(?:ﺍﻟﻌﺎﻣﺔ|العامة).*\n?',
    '',
    text
)

# --- C) Remove the date/time pattern standalone ---
text = re.sub(r'\d{2}/\d{2}/\d{4}\s*\d{1,2}:\d{2}', '', text)

# --- D) Remove footer (الرجاء عدم اعتبار... + copyright) ---
text = re.sub(r'.*الرجاء\s+عدم\s+اعتبار.*', '', text)
text = re.sub(r'.*ﺍﻟﺭﺟﺎﺀ\s+.*(?:ﺭﺳﻣﯾﺔ|رسمية).*', '', text)
text = re.sub(r'©.*$', '', text, flags=re.MULTILINE)

# --- E) Clean up extra whitespace ---
text = re.sub(r'\r\n', '\n', text)
text = re.sub(r'[ \t]+', ' ', text)
text = re.sub(r'\n{3,}', '\n\n', text)
text = text.strip()

# ==========================================
# 3️⃣ SAVE CLEANED TEXT
# ==========================================
with open("law_structured.txt", "w", encoding="utf-8") as f:
    f.write(text)

print("✅ Cleaned text saved to law_structured.txt")
print(f"📏 Length: {len(text)} characters")

print("\n--- First 500 chars ---")
print(text[:500])
print("\n--- Last 300 chars ---")
print(text[-300:])