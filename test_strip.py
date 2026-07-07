import json
import re

p = r"c:\Users\jgi\Downloads\university-updated (1)\university\templates\about_jain.html"
content = open(p, "rb").read()
# Strip trailing null bytes
cleaned_content = content.rstrip(b"\x00")
print("Original size:", len(content))
print("Cleaned size:", len(cleaned_content))

text = cleaned_content.decode("utf-8", errors="ignore")

def check_script_tag(text, tag_type):
    m = re.search(rf'<script type="{tag_type}">(.*?)</script>', text, re.DOTALL)
    if not m:
        print(f"No {tag_type} found!")
        return
    tag_text = m.group(1).strip()
    try:
        json.loads(tag_text)
        print(f"{tag_type} is valid JSON!")
    except Exception as e:
        print(f"Error in {tag_type}:", e)
        pos = getattr(e, 'pos', None)
        if pos is not None:
            print(f"Error at position {pos}")
            start_pos = max(0, pos - 50)
            end_pos = min(len(tag_text), pos + 50)
            print("Context around error:")
            print("..." + tag_text[start_pos:pos] + " -->" + tag_text[pos] + "<-- " + tag_text[pos+1:end_pos] + "...")

check_script_tag(text, "__bundler/manifest")
check_script_tag(text, "__bundler/template")
