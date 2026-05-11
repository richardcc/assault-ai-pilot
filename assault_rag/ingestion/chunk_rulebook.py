import re
from pathlib import Path
from typing import List, Dict

INPUT_PATH = Path(
    "assault_rag/data/rulebook/chunks/rulebook_raw_text.txt"
)

OUTPUT_PATH = Path(
    "assault_rag/data/rulebook/chunks/rulebook_chunks.json"
)

# Regex para detectar encabezados de reglas (ej: 10, 10.7, 10.9.3)
RULE_HEADER_REGEX = re.compile(r"^\s*(\d+(?:\.\d+)*)(?:\s+|$)")

def chunk_rulebook(text: str) -> List[Dict]:
    chunks = []
    current_rule = None
    current_text = []

    for line in text.splitlines():
        match = RULE_HEADER_REGEX.match(line)
        if match:
            # Guardar chunk anterior
            if current_rule and current_text:
                chunks.append({
                    "rule_id": current_rule,
                    "text": "\n".join(current_text).strip(),
                    "source": "rulebook"
                })

            # Empezar nuevo chunk
            current_rule = match.group(1)
            current_text = [line.strip()]
        else:
            if current_rule:
                current_text.append(line)

    # Guardar el último chunk
    if current_rule and current_text:
        chunks.append({
            "rule_id": current_rule,
            "text": "\n".join(current_text).strip(),
            "source": "rulebook"
        })

    return chunks

def main():
    print("▶ Loading rulebook raw text...")
    text = INPUT_PATH.read_text(encoding="utf-8")

    print("▶ Chunking rulebook...")
    chunks = chunk_rulebook(text)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json_dump(chunks),
        encoding="utf-8"
    )

    print(f"✅ Created {len(chunks)} rule chunks")
    print(f"✅ Saved to: {OUTPUT_PATH}")

def json_dump(obj):
    import json
    return json.dumps(obj, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()