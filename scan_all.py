import os

paths = [
    r"c:\Users\jgi\Downloads\jain-portal-fixed\jain\templates\about_jain.html",
    r"c:\Users\jgi\Downloads\jain-portal-v3\jain-portal-v3\templates\about_jain.html",
    r"c:\Users\jgi\Downloads\jain-portal-v3-perf\jain-portal-v3\templates\about_jain.html",
    r"c:\Users\jgi\Downloads\university-updated\university\templates\about_jain.html",
    r"c:\Users\jgi\Downloads\university-updated (1)\university\templates\about_jain.html",
    r"c:\Users\jgi\Downloads\university-updated (2)\university\templates\about_jain.html"
]

for p in paths:
    if os.path.exists(p):
        size = os.path.getsize(p)
        content = open(p, "rb").read()
        null_count = content.count(b"\x00")
        print(f"Path: {p}")
        print(f"  Size: {size} bytes")
        print(f"  Null bytes count: {null_count}")
    else:
        print(f"Path: {p} does not exist")
