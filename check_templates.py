import glob

for f in sorted(glob.glob('templates/*.html')):
    content = open(f, encoding='utf-8', errors='replace').read()
    name = f.split('\\')[-1]
    has_favicon = 'rel="icon"' in content
    has_new_logo = 'jainu.png' in content
    has_old_logo = 'L23.png' in content
    if has_old_logo or not has_favicon:
        print(f'{name}: favicon={has_favicon}, jainu={has_new_logo}, L23={has_old_logo}')

print("Scan complete.")
