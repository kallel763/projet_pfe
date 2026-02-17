from bidi.algorithm import get_display
import arabic_reshaper

with open("law.txt", "r", encoding="utf-8") as f:
    text = f.read()

reshaped_text = arabic_reshaper.reshape(text)
fixed_text = get_display(reshaped_text)

with open("law_fixed.txt", "w", encoding="utf-8") as f:
    f.write(fixed_text)

print("Texte arabe corrigé et prêt")