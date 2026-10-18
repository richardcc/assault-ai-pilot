import json
import re

with open('docs/audit_campaign_extracted.json', encoding='utf-8') as f:
    cb_pages = json.load(f)

scenarios = []

for p in cb_pages:
    num = p["page"]
    text = p["full_text"]
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    
    # Check for Scenario pattern: e.g. "SCENARIO 1.0", "SCENARIO 2.1", "11.1 Addestramento Fanteria", etc.
    for i, l in enumerate(lines[:10]):
        m = re.search(r'(?:SCENARIO\s+(\d+\.\d+)|11\.(\d+))\s*[:\-\–]?\s*(.*)', l, re.IGNORECASE)
        if m:
            sc_id = m.group(1) if m.group(1) else f"11.{m.group(2)}"
            title = m.group(3) if m.group(3) else (lines[i+1] if i+1 < len(lines) else "")
            scenarios.append({
                "page": num,
                "id": sc_id,
                "title": title[:50].strip(),
                "line": l[:60]
            })
            break

print(f"Total scenario pages identified: {len(scenarios)}")
for sc in scenarios:
    print(f"Page {sc['page']:03d} | ID {sc['id']:6s} | Title: {sc['title']}")
