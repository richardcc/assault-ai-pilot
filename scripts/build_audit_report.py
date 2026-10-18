"""
build_audit_report.py
Constructs the exhaustive page-by-page matrix for Rulebook (52 pages) and Campaign Book (104 pages / 38 scenarios).
"""
import json

with open("docs/audit_rulebook_extracted.json", encoding="utf-8") as f:
    rb_pages = json.load(f)

print(f"Loaded {len(rb_pages)} rulebook pages.")
