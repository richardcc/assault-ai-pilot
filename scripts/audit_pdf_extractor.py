"""
audit_pdf_extractor.py
Extracts full text and structure from Rulebook and Campaign Book without character truncations.
"""
from pathlib import Path
import json
import pypdf

def extract_rulebook():
    path = Path("docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf")
    reader = pypdf.PdfReader(path)
    pages_data = []
    
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        pages_data.append({
            "page": i + 1,
            "line_count": len(lines),
            "header": lines[:5] if lines else [],
            "full_text": text
        })
    
    with open("docs/audit_rulebook_extracted.json", "w", encoding="utf-8") as f:
        json.dump(pages_data, f, indent=2, ensure_ascii=False)
    print(f"Rulebook extracted: {len(pages_data)} pages (full text)")

def extract_campaign():
    path = Path("docs/pdfs/ITA_Assault_Libro_Campagna_v1.0.pdf")
    reader = pypdf.PdfReader(path)
    pages_data = []
    
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        pages_data.append({
            "page": i + 1,
            "line_count": len(lines),
            "header": lines[:6] if lines else [],
            "full_text": text
        })
        
    with open("docs/audit_campaign_extracted.json", "w", encoding="utf-8") as f:
        json.dump(pages_data, f, indent=2, ensure_ascii=False)
    print(f"Campaign book extracted: {len(pages_data)} pages (full text)")

if __name__ == "__main__":
    extract_rulebook()
    extract_campaign()
