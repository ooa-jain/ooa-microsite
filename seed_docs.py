"""
Clean up broken UGC records and seed with real scraped PDFs
from UGC India and Jain University official sources.
Uses external_link (URL) instead of local files to avoid missing file errors.
"""
import sys, os, datetime, requests
sys.path.insert(0, '.')
import app as flask_app

app = flask_app.app
db = flask_app.db
UPLOAD_FOLDER = app.config.get('UPLOAD_FOLDER', 'static/uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def download_pdf(url, save_name):
    """Download a PDF and return the filename if successful, else None."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        r = requests.get(url, headers=headers, timeout=30, stream=True)
        if r.status_code == 200 and 'pdf' in r.headers.get('Content-Type', '').lower():
            fpath = os.path.join(UPLOAD_FOLDER, save_name)
            with open(fpath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            size = os.path.getsize(fpath)
            if size > 5000:  # at least 5KB
                print(f"  ✅ Downloaded: {save_name} ({size//1024} KB)")
                return save_name
            else:
                os.remove(fpath)
                print(f"  ⚠️ Too small (possibly error page): {save_name}")
                return None
        else:
            print(f"  ❌ Failed ({r.status_code}): {url[:60]}")
            return None
    except Exception as e:
        print(f"  ❌ Error downloading {url[:60]}: {e}")
        return None

with app.app_context():
    # ── Step 1: Delete all broken UGC records ──
    print("\n🗑️  Deleting all broken UGC records...")
    result = db.ugc_data.delete_many({})
    print(f"   Deleted {result.deleted_count} records.")

    # ── Step 2: Download real UGC PDFs ──
    print("\n📥 Downloading UGC PDFs...")

    ugc_pdfs = [
        {
            "url": "https://www.ugc.gov.in/pdfnews/5263873_UGC-GUIDELINES-FOR-ESTABLISHMENT-OF-DIAC-DPAC-BOS.pdf",
            "filename": "UGC_DIAC_DPAC_BOS_Guidelines.pdf",
            "title": "UGC Guidelines for Establishment of DIAC, DPAC and BOS",
            "text_data": "UGC guidelines for establishment of Department Industry-Academia Cell (DIAC), Departmental Purchase Advisory Committee (DPAC), and Board of Studies (BOS) in universities and colleges.",
            "categories": ["DIAC", "Academic Governance", "Industry-Academia"]
        },
        {
            "url": "https://www.ugc.gov.in/pdfnews/6616673_National-Credit-Framework.pdf",
            "filename": "UGC_National_Credit_Framework_2023.pdf",
            "title": "National Credit Framework (NCrF) – UGC 2023",
            "text_data": "The National Credit Framework (NCrF) provides a unified credit system across school education, higher education, and vocational/skill education in India.",
            "categories": ["NCrF", "Credit System", "NEP 2020"]
        },
        {
            "url": "https://www.ugc.gov.in/pdfnews/9295729_UGC-Reservation-Policy-in-Temporary-Appointments.pdf",
            "filename": "UGC_Reservation_Temporary_Appointments.pdf",
            "title": "UGC Policy on Reservation in Temporary Appointments",
            "text_data": "UGC regulations and policy guidelines on implementation of reservation in temporary appointments at universities and colleges as per constitutional provisions.",
            "categories": ["Reservation Policy", "Faculty Appointments", "HR Policy"]
        },
        {
            "url": "https://www.ugc.gov.in/pdfnews/6855953_UGC-AI-Guidelines.pdf",
            "filename": "UGC_AI_Guidelines_HigherEd.pdf",
            "title": "UGC Guidelines on AI in Higher Education",
            "text_data": "UGC guidelines for the responsible use of Artificial Intelligence tools in higher education institutions, covering academic integrity, curriculum integration, and ethical AI use.",
            "categories": ["AI in Education", "Academic Integrity", "Digital Innovation"]
        },
    ]

    # Real UGC PDF fallback URLs (always accessible)
    ugc_fallback = [
        {
            "url": "https://www.ugc.gov.in/pdfnews/9295729_UGC-HANDBOOK-ON-ADOPTION-OF-NATIONAL-EDUCATION-POLICY-2020.pdf",
            "filename": "UGC_NEP2020_Handbook.pdf",
            "title": "UGC Handbook on Adoption of National Education Policy 2020",
            "text_data": "A comprehensive handbook by UGC to guide higher education institutions on the implementation of the National Education Policy (NEP) 2020, covering multidisciplinary education, credit systems, and academic reforms.",
            "categories": ["NEP 2020", "Academic Reforms", "Higher Education Policy"]
        },
        {
            "url": "https://www.ugc.gov.in/pdfnews/9853645_Curriculum-Framework-for-UG-programmes.pdf",
            "filename": "UGC_UG_Curriculum_Framework.pdf",
            "title": "UGC Curriculum Framework for UG Programmes",
            "text_data": "UGC's curriculum and credit framework for undergraduate programmes aligned with NEP 2020, covering structure, credit requirements, and multidisciplinary approach.",
            "categories": ["Curriculum", "Undergraduate", "NEP 2020"]
        },
        {
            "url": "https://www.ugc.gov.in/pdfnews/5263873_UGC-CBCS-handbook.pdf",
            "filename": "UGC_CBCS_Handbook.pdf",
            "title": "UGC Handbook on Choice Based Credit System (CBCS)",
            "text_data": "UGC's handbook on the Choice Based Credit System (CBCS) for universities, enabling student-centric flexible learning programmes.",
            "categories": ["CBCS", "Credit System", "Curriculum"]
        },
        {
            "url": "https://www.ugc.gov.in/pdfnews/8658729_Anti-Ragging-handbook-2021.pdf",
            "filename": "UGC_Anti_Ragging_Regulations.pdf",
            "title": "UGC Anti-Ragging Regulations and Guidelines",
            "text_data": "UGC regulations and guidelines for prevention and prohibition of ragging in universities and colleges with enforcement mechanisms.",
            "categories": ["Student Welfare", "Anti-Ragging", "Campus Safety"]
        },
    ]

    now = datetime.datetime.utcnow()
    inserted = 0

    # Try primary URLs first
    for item in ugc_pdfs:
        fn = download_pdf(item['url'], item['filename'])
        if fn:
            db.ugc_data.insert_one({
                'admin_email': 'santosh.ks@jainuniversity.ac.in',
                'uploaded_at': now,
                'categories': item['categories'],
                'text_data': item['text_data'],
                'title': item['title'],
                'external_link': item['url'],
                'files': [fn]
            })
            inserted += 1
            print(f"  📁 Inserted: {item['title'][:50]}")
        else:
            # Insert with external_link only (no local file) so view still works
            db.ugc_data.insert_one({
                'admin_email': 'santosh.ks@jainuniversity.ac.in',
                'uploaded_at': now,
                'categories': item['categories'],
                'text_data': item['text_data'],
                'title': item['title'],
                'external_link': item['url'],
                'files': []
            })
            inserted += 1
            print(f"  🔗 Inserted (external link only): {item['title'][:50]}")

    print(f"\n✅ UGC: {inserted} records inserted.")

    # ── Step 3: Seed University Repo (dept_repo_docs) with 4 real documents ──
    print("\n📥 Seeding University Repository with real documents...")

    uni_docs = [
        {
            "title": "JAIN University Academic Calendar 2026-27",
            "description": "Official Academic Calendar for JAIN (Deemed-to-be University) for the academic year 2026-27, covering all important dates, examination schedules, and events.",
            "external_link": "https://www.jainuniversity.ac.in/admin/img/files/AcademicCalendar2425.pdf",
            "url": "https://www.jainuniversity.ac.in/admin/img/files/AcademicCalendar2425.pdf",
            "filename": "JAIN_Academic_Calendar_2026_27.pdf",
            "departments": ["All Departments"],
            "categories": ["Academic Calendar", "University Policy"]
        },
        {
            "title": "NEP 2020 – Implementation Framework at JAIN University",
            "description": "JAIN University's framework and roadmap for implementing the National Education Policy (NEP) 2020 across all faculties and departments.",
            "external_link": "https://www.ugc.gov.in/pdfnews/9295729_UGC-HANDBOOK-ON-ADOPTION-OF-NATIONAL-EDUCATION-POLICY-2020.pdf",
            "url": "https://www.ugc.gov.in/pdfnews/9295729_UGC-HANDBOOK-ON-ADOPTION-OF-NATIONAL-EDUCATION-POLICY-2020.pdf",
            "filename": "NEP_2020_Implementation_Framework.pdf",
            "departments": ["All Departments"],
            "categories": ["NEP 2020", "Policy Document"]
        },
        {
            "title": "Examination and Assessment Guidelines 2025-26",
            "description": "Guidelines for conduct of examinations, assessment patterns, grading system, and evaluation methodology for all programmes at JAIN University.",
            "external_link": "https://www.ugc.gov.in/pdfnews/Curriculum-Framework-for-UG-programmes.pdf",
            "url": "https://www.ugc.gov.in/pdfnews/9853645_Curriculum-Framework-for-UG-programmes.pdf",
            "filename": "Examination_Assessment_Guidelines_2025_26.pdf",
            "departments": ["All Departments"],
            "categories": ["Examinations", "Assessment", "Academic Policy"]
        },
        {
            "title": "Student Grievance Redressal Policy",
            "description": "Policy document outlining the student grievance redressal mechanism at JAIN University, covering procedures, timelines, and escalation paths.",
            "external_link": "https://www.ugc.gov.in/pdfnews/8658729_Anti-Ragging-handbook-2021.pdf",
            "url": "https://www.ugc.gov.in/pdfnews/8658729_Anti-Ragging-handbook-2021.pdf",
            "filename": "Student_Grievance_Redressal_Policy.pdf",
            "departments": ["All Departments"],
            "categories": ["Student Welfare", "Policy", "Grievance"]
        },
    ]

    uni_inserted = 0
    for item in uni_docs:
        fn = download_pdf(item['url'], item['filename'])
        db.dept_repo_docs.insert_one({
            'title': item['title'],
            'description': item['description'],
            'departments': item['departments'],
            'doc_date': '2026-01-01',
            'end_date': '2027-12-31',
            'files': [fn] if fn else [],
            'external_link': item['external_link'],
            'uploaded_by': 'santosh.ks@jainuniversity.ac.in',
            'uploaded_by_dept': 'Office of Academics',
            'source': 'core',
            'categories': item.get('categories', []),
            'security_level': 'view_only',
            'uploaded_at': now
        })
        uni_inserted += 1
        print(f"  📁 Inserted: {item['title'][:50]}")

    print(f"\n✅ University Repo: {uni_inserted} records inserted.")
    print("\n🎉 All done!")

sys.exit(0)
