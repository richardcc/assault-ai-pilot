import json
import re

with open('docs/audit_rulebook_extracted.json', encoding='utf-8') as f:
    rb_pages = json.load(f)

with open('docs/audit_rulebook_pages.txt', 'w', encoding='utf-8') as out:
    for p in rb_pages:
        num = p["page"]
        lines = [l.strip() for l in p["raw_text"].split("\n") if l.strip()]
        
        sec_matches = []
        for l in lines:
            # Match patterns like 9.10.2, 10.7, etc.
            m = re.findall(r'(?:^|\s)(\d+\.\d+(?:\.\d+)*\.?\s+[A-Za-z0-9\s\(\)\/\-\,\&]+)', l)
            for item in m:
                clean = item.strip()
                if len(clean) > 3 and clean not in sec_matches:
                    sec_matches.append(clean)
                    
        out.write(f"=== PAGE {num:02d} ===\n")
        out.write("  Top text: " + " // ".join(lines[:5]) + "\n")
        if sec_matches:
            out.write("  Detected sections: " + " | ".join(sec_matches[:8]) + "\n")
        out.write("\n")

print("Wrote docs/audit_rulebook_pages.txt")
