import json

with open('docs/audit_campaign_extracted.json', encoding='utf-8') as f:
    cb_pages = json.load(f)

with open('docs/audit_campaign_pages.txt', 'w', encoding='utf-8') as out:
    for p in cb_pages:
        num = p["page"]
        text = p["full_text"]
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        
        # Check if page has scenario indications
        scenario_lines = [l for l in lines if "SCENARIO" in l.upper() or "11." in l or "BATTUTA" in l.upper() or "GELA" in l.upper()]
        
        out.write(f"=== PAGE {num:03d} ===\n")
        out.write("  Top: " + " // ".join(lines[:4]) + "\n")
        if scenario_lines:
            out.write("  Key lines: " + " | ".join(scenario_lines[:6]) + "\n")
        out.write("\n")

print("Wrote docs/audit_campaign_pages.txt")
