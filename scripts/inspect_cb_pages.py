import json

with open('docs/audit_campaign_extracted.json', encoding='utf-8') as f:
    cb_pages = json.load(f)

for p in cb_pages[13:100]:
    num = p["page"]
    lines = [l.strip() for l in p["full_text"].split("\n") if l.strip()]
    first_few = " /// ".join(lines[:6])
    first_few = first_few.encode("ascii", "replace").decode("ascii")
    print(f"P{num:03d}: {first_few[:120]}")
