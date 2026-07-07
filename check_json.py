import json
import re

content = open('templates/about_jain.html', encoding='utf-8').read()

def check_script_tag(tag_type):
    m = re.search(rf'<script type="{tag_type}">(.*?)</script>', content, re.DOTALL)
    if not m:
        print(f"No {tag_type} found!")
        return
    text = m.group(1).strip()
    try:
        json.loads(text)
        print(f"{tag_type} is valid JSON!")
    except Exception as e:
        print(f"Error in {tag_type}:", e)
        pos = getattr(e, 'pos', None)
        if pos is not None:
            print(f"Error at position {pos}")
            start_pos = max(0, pos - 50)
            end_pos = min(len(text), pos + 50)
            print("Context around error:")
            print("..." + text[start_pos:pos] + " -->" + text[pos] + "<-- " + text[pos+1:end_pos] + "...")

print("Checking Manifest:")
check_script_tag("__bundler/manifest")

print("\nChecking Template:")
check_script_tag("__bundler/template")
