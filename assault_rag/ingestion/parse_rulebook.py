from pathlib import Path
from pypdf import PdfReader

RULEBOOK_PATH = Path(
    "assault_rag/data/rulebook/raw/2024_09_18_Rulebook_rev6_web.pdf"
)

OUTPUT_PATH = Path(
    "assault_rag/data/rulebook/chunks/rulebook_raw_text.txt"
)

def extract_rulebook_text():
    reader = PdfReader(RULEBOOK_PATH)
    pages_text = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text:
            continue

        cleaned = text.strip()
        if cleaned:
            pages_text.append(f"\n--- PAGE {i+1} ---\n{cleaned}")

    return "\n".join(pages_text)

def main():
    print("▶ Reading rulebook PDF...")
    text = extract_rulebook_text()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"✅ Rulebook extracted to: {OUTPUT_PATH}")
    print(f"✅ Total characters: {len(text)}")

if __name__ == "__main__":
    main()