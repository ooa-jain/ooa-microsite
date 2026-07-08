"""
Audit UGC and University Repo documents:
- Show what's in DB
- Check if files exist on disk
- Report missing files
"""
import sys, os
sys.path.insert(0, '.')
import app as flask_app

app = flask_app.app
db = flask_app.db
UPLOAD_FOLDER = app.config.get('UPLOAD_FOLDER', 'static/uploads')

with app.app_context():
    print("=" * 60)
    print("UNIVERSITY REPO DOCUMENTS")
    print("=" * 60)
    uni_docs = list(db.university_repo.find({}))
    print(f"Total records: {len(uni_docs)}")
    for d in uni_docs:
        files = d.get('files', [])
        for f in files:
            path = os.path.join(UPLOAD_FOLDER, f)
            exists = os.path.exists(path)
            print(f"  [{('OK' if exists else 'MISSING')}] {f[:60]}")

    print()
    print("=" * 60)
    print("UGC RECORDS")
    print("=" * 60)
    ugc_docs = list(db.ugc_records.find({}))
    print(f"Total records: {len(ugc_docs)}")
    for d in ugc_docs:
        files = d.get('files', [])
        for f in files:
            path = os.path.join(UPLOAD_FOLDER, f)
            exists = os.path.exists(path)
            print(f"  [{('OK' if exists else 'MISSING')}] {f[:60]}")

    print()
    print("=" * 60)
    print("DEPT REPO DOCS")
    print("=" * 60)
    dept_docs = list(db.dept_repo_docs.find({}))
    print(f"Total records: {len(dept_docs)}")
    for d in dept_docs:
        files = d.get('files', [])
        for f in files:
            path = os.path.join(UPLOAD_FOLDER, f)
            exists = os.path.exists(path)
            print(f"  [{('OK' if exists else 'MISSING')}] {f[:60]}")

print("Done.")
sys.exit(0)
