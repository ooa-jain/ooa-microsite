"""Generate OOA Microsite Workflow PDF using ReportLab"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import KeepTogether

NAVY = colors.HexColor('#04043a')
GOLD = colors.HexColor('#C5A572')
LIGHT = colors.HexColor('#f8f9fc')
ACCENT = colors.HexColor('#0A2A44')
WHITE = colors.white
GREY = colors.HexColor('#64748b')
GREEN = colors.HexColor('#065f46')
GREEN_BG = colors.HexColor('#d1fae5')

doc = SimpleDocTemplate("OOA_Jain_Workflow.pdf", pagesize=A4,
    leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)

styles = getSampleStyleSheet()
def S(name, **kw):
    return ParagraphStyle(name, **kw)

title_style = S('T', fontSize=26, textColor=WHITE, alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=6)
sub_style   = S('S', fontSize=13, textColor=GOLD,  alignment=TA_CENTER, fontName='Helvetica', spaceAfter=4)
h1_style    = S('H1', fontSize=16, textColor=NAVY, fontName='Helvetica-Bold', spaceBefore=16, spaceAfter=8)
h2_style    = S('H2', fontSize=13, textColor=ACCENT, fontName='Helvetica-Bold', spaceBefore=10, spaceAfter=6)
body_style  = S('B', fontSize=10, textColor=colors.HexColor('#1e293b'), fontName='Helvetica', leading=16, spaceAfter=4, alignment=TA_JUSTIFY)
bullet_style= S('BL', fontSize=10, textColor=colors.HexColor('#334155'), fontName='Helvetica', leading=15, leftIndent=14, spaceAfter=3)
caption_style=S('C', fontSize=8, textColor=GREY, alignment=TA_CENTER, fontName='Helvetica-Oblique')
label_style = S('L', fontSize=9, textColor=WHITE, alignment=TA_CENTER, fontName='Helvetica-Bold')

def header_block(title, subtitle):
    data = [[Paragraph(title, title_style)], [Paragraph(subtitle, sub_style)]]
    t = Table(data, colWidths=[17*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), NAVY),
        ('ROWPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,0), 24),
        ('BOTTOMPADDING', (0,-1), (-1,-1), 24),
        ('ROUNDEDCORNERS', [8]),
    ]))
    return t

def section_banner(text, color=ACCENT):
    t = Table([[Paragraph(text, S('sb', fontSize=12, textColor=WHITE, fontName='Helvetica-Bold'))]], colWidths=[17*cm])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),color),('ROWPADDING',(0,0),(-1,-1),8),('ROUNDEDCORNERS',[6])]))
    return t

def feature_table(rows):
    data = [[Paragraph('<b>Feature</b>', label_style), Paragraph('<b>Description</b>', label_style)]] + \
           [[Paragraph(f'<b>{r[0]}</b>', S('ft', fontSize=9, textColor=NAVY, fontName='Helvetica-Bold')),
             Paragraph(r[1], S('fd', fontSize=9, textColor=colors.HexColor('#334155'), fontName='Helvetica', leading=14))]
            for r in rows]
    t = Table(data, colWidths=[5*cm, 12*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        ('ROWPADDING', (0,0), (-1,-1), 8),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [LIGHT, WHITE]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    return t

def flow_table(steps):
    rows = []
    for i, (title, desc) in enumerate(steps, 1):
        num = Table([[Paragraph(f'<b>{i}</b>', S('n', fontSize=14, textColor=WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER))]],
                    colWidths=[1*cm], rowHeights=[1*cm])
        num.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),GOLD),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ROUNDEDCORNERS',[20])]))
        txt = Table([[Paragraph(f'<b>{title}</b>', S('ft2', fontSize=11, textColor=NAVY, fontName='Helvetica-Bold')),
                      Paragraph(desc, S('fd2', fontSize=9, textColor=GREY, fontName='Helvetica', leading=14))]],
                    colWidths=[5*cm, 10.5*cm])
        rows.append([num, txt])
    t = Table(rows, colWidths=[1.2*cm, 15.8*cm])
    t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ROWPADDING',(0,0),(-1,-1),8),
                            ('LINEBELOW',(0,0),(-1,-2),0.5,colors.HexColor('#e2e8f0'))]))
    return t

story = []

# ── Cover Page ──
story += [Spacer(1, 2*cm),
    header_block("OOA JAIN University Microsite","Office of Academics — Platform Workflow & Feature Guide"),
    Spacer(1,0.5*cm),
    Paragraph("Prepared by: Office of Academics | Jain (Deemed-to-be University)", S('meta', fontSize=10, textColor=GREY, alignment=TA_CENTER, fontName='Helvetica')),
    Paragraph("Version 1.0 | 2026", S('meta2', fontSize=10, textColor=GREY, alignment=TA_CENTER, fontName='Helvetica')),
    Spacer(1,1*cm),
    HRFlowable(width="100%", thickness=2, color=GOLD),
    Spacer(1,0.5*cm),
    Paragraph("This document provides a comprehensive guide to all features and workflows of the OOA Jain University digital platform — from login to academic calendar, UGC notices, reminders, profile management, and administrative tools.", body_style),
    PageBreak()]

# ── Table of Contents ──
toc_data = [
    [Paragraph('<b>#</b>', label_style), Paragraph('<b>Section</b>', label_style), Paragraph('<b>Page</b>', label_style)],
    *[[Paragraph(str(i), S('tc', fontSize=10, alignment=TA_CENTER, fontName='Helvetica')),
       Paragraph(t, S('tc2', fontSize=10, fontName='Helvetica')),
       Paragraph(p, S('tc3', fontSize=10, alignment=TA_CENTER, fontName='Helvetica'))]
      for i,(t,p) in enumerate([
          ("Platform Overview & Architecture","3"),
          ("Landing Page — Login & Access","4"),
          ("Home Dashboard","5"),
          ("Today's Events Ticker","6"),
          ("Academic Calendar","7"),
          ("UGC & University Notices","8"),
          ("Set Event Reminders","9"),
          ("User Profile Management","10"),
          ("Department & University Repository","11"),
          ("About JAIN University","12"),
          ("15-Minute Site Tour & Mini Course","13"),
          ("Admin Dashboard","14"),
          ("Workflow Summary Diagram","15"),
      ], 1)]
]
toc = Table(toc_data, colWidths=[1.2*cm, 13*cm, 2.8*cm])
toc.setStyle(TableStyle([
    ('BACKGROUND',(0,0),(-1,0),NAVY),('TEXTCOLOR',(0,0),(-1,0),WHITE),
    ('ROWBACKGROUNDS',(0,1),(-1,-1),[LIGHT,WHITE]),
    ('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#e2e8f0')),
    ('ROWPADDING',(0,0),(-1,-1),8),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
]))
story += [Paragraph("Table of Contents", h1_style), toc, PageBreak()]

# ── Section 1: Platform Overview ──
story += [section_banner("1. Platform Overview & Architecture"), Spacer(1,0.3*cm),
    Paragraph("The OOA Jain Microsite is a Flask-based web application powered by MongoDB Atlas, providing a centralised digital hub for the Office of Academics at Jain (Deemed-to-be University).", body_style),
    Spacer(1,0.3*cm),
    feature_table([
        ("Backend", "Python Flask with MongoDB Atlas (cloud database)"),
        ("Authentication", "Email/password login + Google OAuth (Firebase) — Jain domain only"),
        ("Email Service", "SMTP-based automated reminder emails with HTML templates"),
        ("Hosting", "Deployable on Render / any WSGI server (port 5001 default)"),
        ("Security", "Session-based auth, role-based access (admin/user/leader/core)"),
        ("Key Collections", "users, ugc_data, events, dept_repo_docs, event_reminders, campus_gallery"),
    ]), PageBreak()]

# ── Section 2: Landing Page ──
story += [section_banner("2. Landing Page — Login & Access"), Spacer(1,0.3*cm),
    Paragraph("The landing page (<b>/</b>) is the public-facing entry point for all users. It features a dark video background, Jain University branding, and an integrated login form.", body_style),
    Spacer(1,0.3*cm),
    Paragraph("Key Elements:", h2_style),
    feature_table([
        ("Hero Section","Full-screen video background with University title and stats (28+ Departments, 25+ Core Processes)"),
        ("Login Form","Email + Password login with validation. Supports Google Sign-In via Firebase for @jainuniversity.ac.in accounts only"),
        ("Navigation","Links to Governance Framework and Platform Capabilities sections"),
        ("Register Link","New users can create accounts, pending admin approval"),
        ("Forgot Password","OTP-based password reset flow via registered email"),
    ]),
    Spacer(1,0.3*cm),
    Paragraph("User Flow:", h2_style),
    flow_table([
        ("Open site","User visits the landing page at http://[server]:5001/"),
        ("Login","Enter Jain email + password, or click 'Sign in with Google'"),
        ("Authentication","Server validates credentials, creates session, redirects to /home"),
        ("New User","Register → Admin approval → Access granted"),
    ]), PageBreak()]

# ── Section 3: Home Dashboard ──
story += [section_banner("3. Home Dashboard"), Spacer(1,0.3*cm),
    Paragraph("After login, users land on <b>/home</b> — the main dashboard. It is a rich, interactive page with multiple sections loaded asynchronously from <b>/api/home_data</b>.", body_style),
    Spacer(1,0.3*cm),
    feature_table([
        ("Today's Events Ticker","Marquee scroll bar at the top showing today's academic events. Click to view details in calendar"),
        ("UGC Notices Panel","Scrolling panel with latest UGC circulars and guidelines. Click any notice to view full details + PDF/links"),
        ("OOA Announcements Panel","Office of Academics internal notices and announcements with external links"),
        ("Academic Calendar Slide","Interactive calendar showing upcoming events with department filter"),
        ("Campus Moments","Photo gallery of recent campus events and highlights"),
        ("Events Section","Categorised today's events + upcoming events with 'Set Reminder' button"),
        ("Mini Course","15-minute guided tour of Jain University history, NEP 2020, and platform features"),
        ("Tour Driver","Step-by-step guided product tour of the entire page (Driver.js)"),
    ]), PageBreak()]

# ── Section 4: Today's Events Ticker ──
story += [section_banner("4. Today's Events Ticker"), Spacer(1,0.3*cm),
    Paragraph("The <b>Today's Events</b> ticker appears as a scrolling gold-and-navy marquee strip at the top of the Home page. It auto-loads events happening on the current date.", body_style),
    Spacer(1,0.3*cm),
    flow_table([
        ("Auto-load","Page fetches /api/home_data on load; today_events filtered from academic calendar events"),
        ("Display","Event names scroll slowly (250s animation) — readable and non-distracting"),
        ("Click Action","Clicking a ticker event navigates to /calendar?eventName=...&eventDate=... opening the event drawer"),
        ("Empty State","If no events today, shows 'No events scheduled for today' with link to calendar"),
    ]), PageBreak()]

# ── Section 5: Academic Calendar ──
story += [section_banner("5. Academic Calendar (/calendar)"), Spacer(1,0.3*cm),
    Paragraph("The Academic Calendar at <b>/calendar</b> is a fully interactive, self-contained page with 2800+ Jain University events pre-loaded for 2026-27.", body_style),
    Spacer(1,0.3*cm),
    feature_table([
        ("Views","Month view, Timeline view, Today view, Upcoming (60-day) view"),
        ("Navigation Sidebar","Browse by Faculty → Department → Sub-department with event counts"),
        ("Campus Filter","Filter events by Bengaluru Campus or Kochi Campus"),
        ("Search","Real-time keyword search across all events"),
        ("Event Type Filter","Filter by type: Seminar, Workshop, Placement, Academic, etc."),
        ("Event Drawer","Click any event to open a side drawer with full details: venue, coordinator, dates, department"),
        ("Google Calendar","One-click 'Add to Google Calendar' from event drawer"),
        ("Deep Link","Supports ?eventName=&eventDate= URL params — clicking ticker/notices opens specific event"),
    ]), PageBreak()]

# ── Section 6: UGC & University Notices ──
story += [section_banner("6. UGC & University Notices"), Spacer(1,0.3*cm),
    Paragraph("Two scrolling notice panels on the Home dashboard serve as a live bulletin board for the academic community.", body_style),
    Spacer(1,0.3*cm),
    feature_table([
        ("UGC Notices","Displays records with category='UGC' from ugc_data collection. Includes UGC guidelines, NCrF, DIAC/DPAC, NEP 2020 handbooks"),
        ("OOA Announcements","Displays records with category='University Notice'. Includes academic calendar, exam notices, ABC registration, CBCS updates"),
        ("Notice Modal","Click any notice to open modal with full description, external link, and PDF attachment if available"),
        ("PDF Viewer","PDFs open in an embedded iframe modal with download and open-in-new-tab options"),
        ("Admin Upload","Admins can add new notices via /edit_ugc with text, categories, files, and external links"),
    ]),
    Spacer(1,0.3*cm),
    Paragraph("Current Notices (4 UGC + 4 University):", h2_style),
    feature_table([
        ("UGC — DIAC/DPAC/BOS","Guidelines for Department Industry-Academia Cell establishment"),
        ("UGC — NCrF 2023","National Credit Framework — unified credit system document"),
        ("UGC — Reservation Policy","Reservation in temporary appointments regulations"),
        ("UGC — NEP 2020 Handbook","Comprehensive handbook for NEP 2020 adoption"),
        ("OOA — Academic Calendar","JAIN Academic Calendar 2026-27 (external PDF link)"),
        ("OOA — Exam Schedule","Semester-end examination schedule and instructions"),
        ("OOA — ABC Registration","Academic Bank of Credits student registration notice"),
        ("OOA — CBCS Update","Choice Based Credit System implementation notice"),
    ]), PageBreak()]

# ── Section 7: Set Event Reminders ──
story += [section_banner("7. Set Event Reminders"), Spacer(1,0.3*cm),
    Paragraph("Users can set personalised email reminders for any academic calendar event directly from the Home dashboard.", body_style),
    Spacer(1,0.3*cm),
    flow_table([
        ("Click Event","Click any event card in the Home dashboard events section"),
        ("Reminder Modal","A modal opens showing event name, date, time, and venue"),
        ("Set Date & Time","User picks reminder date, time, and optional note"),
        ("Save Reminder","POST to /set_reminder — saves to event_reminders collection in MongoDB"),
        ("Confirmation Email","System sends a beautiful HTML confirmation email to the user's Jain email"),
        ("Reminder Email","At the set time, system sends reminder email via /cron/send-reminders endpoint"),
        ("View Reminders","All set reminders visible in My Profile → Reminders tab"),
        ("Cancel Reminder","Delete button in Profile cancels and removes the reminder"),
    ]), PageBreak()]

# ── Section 8: User Profile ──
story += [section_banner("8. User Profile Management (/profile)"), Spacer(1,0.3*cm),
    Paragraph("Each logged-in user has a dedicated Profile page at <b>/profile</b> with personal information, security settings, reminders, and documents.", body_style),
    Spacer(1,0.3*cm),
    feature_table([
        ("Profile Card","Shows name, email, role, department, location, and approval status badge"),
        ("Profile Photo","Click avatar to upload a new photo (JPG/PNG/WEBP). Stored in static/uploads/"),
        ("Change Password","Current password → new password → confirm. Validated server-side via /profile/change_password"),
        ("My Reminders Tab","Table of all set reminders: event name, date/time, scheduled reminder time, cancel button"),
        ("My Documents Tab","All documents uploaded by the user across office docs, dept repo, and public files"),
        ("Document Status","Each document shows status: Approved / Pending / Uploaded with colour-coded badges"),
    ]), PageBreak()]

# ── Section 9: Repository ──
story += [section_banner("9. Department & University Repository"), Spacer(1,0.3*cm),
    feature_table([
        ("Department Repo (/dept_repo)","Faculty upload documents visible to core team. Students see documents shared by core/leader for their department"),
        ("University Repo (/university_repo)","Shows documents shared to 'All Departments' by core/leader — university-wide circulars and policies"),
        ("Core Repo (/core_repo)","Leaders/core members upload documents and share to specific departments or all departments"),
        ("Document Viewer (/view_doc/<id>)","Embedded PDF viewer for approved documents"),
        ("Upload Security","File type validation (PDF, DOCX, images, etc.) and file size limit (50MB max)"),
        ("Expiry Dates","Documents can have end_date — automatically hidden after expiry"),
    ]), PageBreak()]

# ── Section 10: About JAIN ──
story += [section_banner("10. About JAIN University (/about_jain)"), Spacer(1,0.3*cm),
    Paragraph("A dedicated public-facing page about Jain (Deemed-to-be University) with interactive sections.", body_style),
    Spacer(1,0.3*cm),
    feature_table([
        ("Navigation Bar","Links: Jain Hub | About JAIN (active) | Campus | Tour | Take 15 Mins"),
        ("Hero Section","University intro with tagline and core values"),
        ("History Timeline","Key milestones in Jain University's history"),
        ("Accreditations","NAAC, NBA, and other accreditation highlights"),
        ("Campus Gallery","Photo highlights from university campuses"),
        ("Programmes","Overview of programmes offered across faculties"),
        ("Today's Events","Marquee ticker with today's academic events (150s slow scroll)"),
        ("User Dropdown","Logged-in users see: My Profile, department links, dashboards, Logout"),
    ]), PageBreak()]

# ── Section 11: 15-Min Course ──
story += [section_banner("11. 15-Minute Site Tour & Mini Course"), Spacer(1,0.3*cm),
    Paragraph("The Home dashboard includes a <b>15-minute interactive mini course</b> about Jain University and how the platform works, delivered as a slide-by-slide walkthrough.", body_style),
    Spacer(1,0.3*cm),
    feature_table([
        ("Slide 1 — Welcome","Introduction to OOA platform and its purpose within Jain University"),
        ("Slide 2 — About JAIN","Brief history: founded 1990, deemed status 2009, 250+ programmes"),
        ("Slide 3 — NEP 2020","How JAIN implements NEP 2020: multidisciplinary, ABC, internships"),
        ("Slide 4 — Platform Features","Dashboard walkthrough: calendar, notices, repository, reminders"),
        ("Slide 5 — Reminders","How to set event reminders and receive email notifications"),
        ("Slide 6 — Final Quiz","3-question quiz to test understanding with instant feedback"),
    ]),
    Spacer(1,0.3*cm),
    Paragraph("Guided Tour (Driver.js):", h2_style),
    Paragraph("The 'Tour' button in the navigation launches a step-by-step overlay tour highlighting: the ticker, notice panels, calendar, events section, campus gallery, and user profile area — each with descriptive tooltips.", body_style),
    PageBreak()]

# ── Section 12: Admin Dashboard ──
story += [section_banner("12. Admin Dashboard (/admin_dashboard)"), Spacer(1,0.3*cm),
    feature_table([
        ("User Management","View all users, change roles, approve/reject accounts, reset passwords, impersonate users"),
        ("Events Management","/admin/events — Add, edit, delete academic calendar events for the OOA portal"),
        ("UGC Notices","/edit_ugc — Upload new UGC/University notices with files, external links, and categories"),
        ("Newsletter","Create and send newsletters to all subscribed users"),
        ("Campus Gallery","Add/remove campus photo moments that appear on the home page"),
        ("Campus Management","Add/edit campus locations shown in the dropdown filters"),
        ("Monthly Engagement","Upload and manage monthly engagement records"),
        ("User Activity Logs","View detailed activity logs per user (page visits, actions)"),
    ]), PageBreak()]

# ── Section 13: Workflow Diagram ──
story += [section_banner("13. Complete Workflow Summary"), Spacer(1,0.3*cm),
    Paragraph("End-to-End User Journey:", h2_style),
    flow_table([
        ("Visit Landing Page","User opens the site. Sees video hero, login card, platform description."),
        ("Login / Register","Login with Jain email + password or Google. New users register and await admin approval."),
        ("Home Dashboard","Greeted by: Events ticker, UGC notices, OOA announcements, Academic Calendar, Campus Gallery."),
        ("Explore Calendar","Click ticker event or 'Academic Calendar' tab to view interactive 2026-27 calendar with 2800+ events."),
        ("Set a Reminder","Click any event card → Set Reminder modal → Pick date/time → Receive confirmation email."),
        ("View UGC Notices","Click any notice card → Modal with full description + external PDF link."),
        ("Take the Course","Scroll to 15-min course section → Learn about JAIN, NEP 2020, platform features, take quiz."),
        ("Manage Profile","Top-right avatar → My Profile → Upload photo, change password, view reminders & documents."),
        ("Upload Documents","Dept Repo or University Repo → Upload files for team or department access."),
        ("Receive Reminders","At the scheduled time, automated email reminder is sent to registered email address."),
    ]),
    Spacer(1,0.5*cm),
    HRFlowable(width="100%", thickness=1, color=GOLD),
    Spacer(1,0.3*cm),
    Paragraph("Technology Stack Summary:", h2_style),
    feature_table([
        ("Frontend","HTML5, Vanilla CSS, JavaScript (no framework) with Driver.js for guided tours"),
        ("Backend","Python 3.13 + Flask 3.x with Jinja2 templating"),
        ("Database","MongoDB Atlas (cloud) — 27 collections"),
        ("Auth","Flask sessions + Firebase Google OAuth"),
        ("Email","SMTP (Gmail/custom) with HTML email templates"),
        ("Deployment","Render.com / any WSGI host | Port 5001 | render.yaml provided"),
        ("Repository","https://github.com/ooa-jain/ooa-microsite"),
    ]),
    Spacer(1,0.5*cm),
    Paragraph("© 2026 JAIN (Deemed-to-be University) — Office of Academics. All rights reserved.", 
               S('foot', fontSize=9, textColor=GREY, alignment=TA_CENTER, fontName='Helvetica-Oblique')),
]

doc.build(story)
print("PDF created: OOA_Jain_Workflow.pdf")
