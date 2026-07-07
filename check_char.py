import re

content = open('templates/about_jain.html', encoding='utf-8').read()
m = re.search(r'<script type="__bundler/manifest">(.*?)</script>', content, re.DOTALL)
if m:
    text = m.group(1).strip()
    pos = 383829
    segment = text[max(0, pos-10):min(len(text), pos+10)]
    print("Segment:", repr(segment))
    print("Char at pos:", repr(text[pos]))
    print("Char code:", ord(text[pos]))
    print("Surrounding char codes:", [ord(c) for c in text[max(0, pos-5):min(len(text), pos+5)]])
else:
    print("Manifest not found")
