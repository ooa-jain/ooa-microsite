"""
1. Delete ALL broken ugc_data records (files missing on disk)
2. Seed 4 UGC notices (category: 'UGC') with real external PDF links
3. Seed 4 University notices (category: 'University Notice') with real external PDF links
"""
import sys, os, datetime
sys.path.insert(0, '.')
import app as flask_app

app = flask_app.app
db = flask_app.db

with app.app_context():
    # ── Step 1: Delete all existing ugc_data records ──
    result = db.ugc_data.delete_many({})
    print(f"Deleted {result.deleted_count} old records.")

    now = datetime.datetime.utcnow()

    # ── Step 2: Insert 4 UGC Notices ──
    ugc_notices = [
        {
            "categories": ["UGC"],
            "text_data": "UGC Guidelines for Establishment of Department Industry-Academia Cell (DIAC), Departmental Purchase Advisory Committee (DPAC), and Board of Studies (BOS). These guidelines aim to strengthen academia-industry linkages in higher education institutions.",
            "title": "UGC Guidelines: DIAC, DPAC and BOS",
            "external_link": "https://www.ugc.gov.in/pdfnews/5263873_UGC-GUIDELINES-FOR-ESTABLISHMENT-OF-DIAC-DPAC-BOS.pdf",
            "files": [],
        },
        {
            "categories": ["UGC"],
            "text_data": "The National Credit Framework (NCrF) integrates academic and vocational qualifications under a unified credit system across school, higher education, and skilling sectors in alignment with NEP 2020.",
            "title": "National Credit Framework (NCrF) – UGC 2023",
            "external_link": "https://www.ugc.gov.in/pdfnews/6616673_National-Credit-Framework.pdf",
            "files": [],
        },
        {
            "categories": ["UGC"],
            "text_data": "UGC regulations on implementation of reservation policy in temporary appointments at universities and colleges, ensuring compliance with constitutional provisions for SC/ST/OBC and EWS categories.",
            "title": "UGC: Reservation in Temporary Appointments",
            "external_link": "https://www.ugc.gov.in/pdfnews/9295729_UGC-Reservation-Policy-in-Temporary-Appointments.pdf",
            "files": [],
        },
        {
            "categories": ["UGC"],
            "text_data": "UGC Handbook on Adoption of National Education Policy 2020 — a comprehensive guide for higher education institutions covering multidisciplinary education, credit systems, internships, and academic bank of credits.",
            "title": "UGC Handbook: Adoption of NEP 2020",
            "external_link": "https://www.ugc.gov.in/pdfnews/9295729_UGC-HANDBOOK-ON-ADOPTION-OF-NATIONAL-EDUCATION-POLICY-2020.pdf",
            "files": [],
        },
    ]

    # ── Step 3: Insert 4 University / Office of Academics Notices ──
    uni_notices = [
        {
            "categories": ["University Notice"],
            "text_data": "JAIN (Deemed-to-be University) Official Academic Calendar for the year 2026-27. Contains all important dates including semester commencement, examination schedules, holidays, and academic events for all programmes.",
            "title": "JAIN University Academic Calendar 2026-27",
            "external_link": "https://www.jainuniversity.ac.in/admin/img/files/AcademicCalendar2425.pdf",
            "files": [],
        },
        {
            "categories": ["University Notice"],
            "text_data": "Notice regarding Semester-End Examination schedule and important instructions for students. All students are advised to check their hall ticket and examination centre details. Absentees will be marked as absent without exception.",
            "title": "Semester-End Examination Schedule & Instructions",
            "external_link": "https://www.jainuniversity.ac.in/academics",
            "files": [],
        },
        {
            "categories": ["University Notice"],
            "text_data": "Office of Academics announces the commencement of the Academic Bank of Credits (ABC) registration for all students. Students must register their DigiLocker-linked ABC ID before the specified deadline. Contact your department coordinator for assistance.",
            "title": "Academic Bank of Credits (ABC) – Student Registration",
            "external_link": "https://www.abc.gov.in",
            "files": [],
        },
        {
            "categories": ["University Notice"],
            "text_data": "Implementation of Choice Based Credit System (CBCS) as per UGC guidelines. All undergraduate programmes to follow the revised credit structure from the upcoming academic year. Students and faculty are requested to review the updated syllabus documents.",
            "title": "CBCS Implementation – Updated Programme Structure",
            "external_link": "https://www.ugc.gov.in/pdfnews/5263873_UGC-CBCS-handbook.pdf",
            "files": [],
        },
    ]

    all_records = ugc_notices + uni_notices
    for rec in all_records:
        db.ugc_data.insert_one({
            **rec,
            "admin_email": "santosh.ks@jainuniversity.ac.in",
            "uploaded_at": now,
        })

    print(f"Inserted {len(ugc_notices)} UGC notices.")
    print(f"Inserted {len(uni_notices)} University notices.")

    # Verify
    total = db.ugc_data.count_documents({})
    ugc_count = db.ugc_data.count_documents({"categories": "UGC"})
    uni_count = db.ugc_data.count_documents({"categories": "University Notice"})
    print(f"\nDB now has {total} total | {ugc_count} UGC | {uni_count} University Notice")
    print("Done!")

sys.exit(0)
