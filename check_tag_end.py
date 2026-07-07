import re

content = open('templates/about_jain.html', encoding='utf-8').read()
m = re.search(r'(<script type="__bundler/manifest">.*?</script>)', content, re.DOTALL)
if m:
    tag = m.group(1)
    print("Tag length:", len(tag))
    print("Last 100 chars of tag:", repr(tag[-100:]))
    # Count null bytes inside the tag
    print("Null bytes in tag:", tag.count('\x00'))
else:
    print("Tag not found")
