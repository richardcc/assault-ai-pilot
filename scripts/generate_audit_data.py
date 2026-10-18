"""
generate_audit_data.py
Analyzes each page of Rulebook and Campaign Book, comparing against assault_model and scenarios.
"""
import json
import re

with open("docs/audit_rulebook_extracted.json", encoding="utf-8") as f:
    rb_pages = json.load(f)

with open("docs/audit_campaign_extracted.json", encoding="utf-8") as f:
    cb_pages = json.load(f)

# Analyze rulebook page by page
print(f"Loaded {len(rb_pages)} rulebook pages, {len(cb_pages)} campaign book pages.")

rulebook_toc = [
    # Based on rulebook p. 2 & 3
    # 1.0 Game Components (p. 4)
    # 2.0 Quick Start (p. 5)
    # 3.0 Concept of the Game (p. 6)
    # 4.0 Game Elements (p. 7)
    # 5.0 Game Preparation (p. 10)
    # 6.0 Sequence of Play (p. 12)
    # 7.0 Support Phase (p. 13)
    # 8.0 Action Phase (p. 14)
    # 9.0 Actions in Detail (p. 16)
    # 10.0 Combat in Detail (p. 24)
    # 11.0 Close Combat in Detail (p. 31)
    # 12.0 Tactical Air Support & Off-Board Artillery (p. 36)
    # 13.0 End Phase (p. 38)
    # 14.0 Scenarios (p. 40)
    # 15.0 Optional Rules (p. 41)
    # Index & Summary Tables (p. 44-52)
]

for p in rb_pages:
    num = p["page"]
    raw = p["raw_text"]
    # Look for section patterns like "6.1", "10.7.2", etc.
    secs = re.findall(r'(\b\d+\.\d+(?:\.\d+)*\b[^\n\.\d]{3,40})', raw)
    # Clean up
    secs = [s.strip().replace('\t', ' ') for s in secs[:3]]
    # print summary
    first_line = p["header"][0] if p["header"] else ""
    first_line = first_line.encode("ascii", "replace").decode("ascii")
