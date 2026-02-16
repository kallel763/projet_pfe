import unicodedata

def normalize(text):
    text = unicodedata.normalize("NFKC", text)

    arabic_digits = {
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
        "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9"
    }

    for k, v in arabic_digits.items():
        text = text.replace(k, v)

    return text

with open("law_fixed.txt", "r", encoding="utf-8") as f:
    raw = f.read()

normalized = normalize(raw)

with open("law_normalized.txt", "w", encoding="utf-8") as f:
    f.write(normalized)

print("✅ Normalisation Unicode terminée")