import json

with open('docs/audit_rulebook_extracted.json', encoding='utf-8') as f:
    rb_pages = json.load(f)

for p in rb_pages:
    txt = p['raw_text']
    lines = [l.strip() for l in txt.split('\n') if l.strip()]
    first_few = ' '.join(lines[:4])[:120]
    first_few = first_few.encode('ascii', 'replace').decode('ascii')
    print("Page %02d: %s" % (p["page"], first_few))
