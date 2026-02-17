import pdfplumber

text = ""

with pdfplumber.open("law19.pdf") as pdf:
    for page in pdf.pages:
        text += page.extract_text() + "\n"

with open("law.txt", "w", encoding="utf-8") as f:
    f.write(text)

print("✅ Texte extrait avec succès")