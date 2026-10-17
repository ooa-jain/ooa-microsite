# swayam_data.py
"""SWAYAM course list and enrolment guidelines shown on the Jain Hub page.

Source: "AY 2026 Odd Semester – SWAYAM Course List (MDC) and Guidelines for
Enrollment" and "SWAYAM Enrolment Guidelines AY 2026-27", issued by the SWAYAM
Nodal Office. For a new cycle, edit this file only — the template reads
everything from SWAYAM.
"""

CATEGORIES = [
    # key, label, Font Awesome icon, short label for course-card tags
    ('vac', 'VAC (Mandate Course)', 'fa-landmark', 'Mandate course'),
    ('ai', 'AI and New Technologies', 'fa-robot', 'AI & New Tech'),
    ('bb', 'Bharatiya Bhasha', 'fa-language', 'Bharatiya Bhasha'),
    ('ent', 'Entrepreneurship', 'fa-rocket', 'Entrepreneurship'),
    ('iks', 'Indian Knowledge Systems', 'fa-om', 'IKS'),
    ('sus', 'Sustainability', 'fa-leaf', 'Sustainability'),
]

_PREVIEW = 'https://onlinecourses.swayam2.ac.in/e-learning/preview/'

# Every course is 3 credits, Theory, LTPE 3-0-0-0. `type` is VAC or MDC.
COURSES = [
    dict(cat='vac', type='VAC', title='Introduction to Indian Constitution',
         ug='25SWIC0VE1', pg=None, offered='Rerun', link=_PREVIEW + 'imb26_mg250'),
    dict(cat='ai', type='MDC', title='Prompt Engineering',
         ug='25SWGAI01', pg='25SWOAI01', offered='Rerun', link=_PREVIEW + 'imb26_mg232'),
    dict(cat='ai', type='MDC', title='AI in Digital and Social Media Marketing',
         ug='25SWGAI02', pg='25SWOAI02', offered='Rerun', link=_PREVIEW + 'imb26_mg246'),
    dict(cat='ai', type='MDC', title='Information System for Innovation',
         ug='26SWGAI03', pg='26SWOAI03', offered='Odd', link=_PREVIEW + 'imb26_mg241'),
    dict(cat='ai', type='MDC', title='AI in Leadership and Governance',
         ug='26SWGAI04', pg='26SWOAI04', offered='Odd', link=_PREVIEW + 'imb26_mg243'),
    dict(cat='bb', type='MDC', title='ग्लोबल कम्युनिकेशन के लिए हिन्दी',
         subtitle='Hindi for Global Communication', lang='hi',
         ug='26SWGBB01', pg='26SWOBB01', offered='Odd', link=_PREVIEW + 'imb26_mg240'),
    dict(cat='ent', type='MDC', title='Social Entrepreneurship and Sustainability',
         ug='25SWGEN07', pg='25SWOEN07', offered='Rerun', link=_PREVIEW + 'imb26_mg236'),
    dict(cat='ent', type='MDC', title='Business Skills: A Global Perspective – I',
         ug='25SWGEN02', pg='25SWOEN02', offered='Rerun', link=_PREVIEW + 'imb26_mg235'),
    dict(cat='ent', type='MDC', title='Affiliate Marketing',
         ug='25SWGEN03', pg='25SWOEN03', offered='Rerun', link=_PREVIEW + 'imb26_mg245'),
    dict(cat='ent', type='MDC', title='Decision Science in Management',
         ug='26SWGEN04', pg='26SWOEN04', offered='Odd', link=_PREVIEW + 'imb26_mg233'),
    dict(cat='ent', type='MDC', title='Advanced Marketing: Marketing 5.0',
         ug='26SWGEN05', pg='26SWOEN05', offered='Odd', link=_PREVIEW + 'imb26_mg244'),
    dict(cat='iks', type='MDC',
         title='Indian Knowledge System (IKS) and Human Resource Management (HRM): Work, Wisdom and Wellbeing',
         ug='25SWGIK01', pg='25SWOIK01', offered='Rerun', link=_PREVIEW + 'imb26_mg239'),
    dict(cat='sus', type='MDC', title='Gender Studies',
         ug='25SWGST01', pg='25SWOST01', offered='Rerun', link=_PREVIEW + 'imb26_mg234'),
    dict(cat='sus', type='MDC', title='Green Computing',
         ug='26SWGST02', pg='26SWOST02', offered='Odd', link=_PREVIEW + 'imb26_mg230'),
    dict(cat='sus', type='MDC', title='Nutrition and Health',
         ug='26SWGST03', pg='26SWOST03', offered='Odd', link=_PREVIEW + 'imb26_mg251'),
]

# Educational Details on the SWAYAM enrolment form, to be filled exactly as given.
FORM_FIELDS = [
    ('Part of a SWAYAM Local Chapter', 'YES'),
    ('College State', 'Karnataka'),
    ('College Name', 'Jain University, Bengaluru, KARNATAKA (7730)'),
    ('University Name', 'Jain University, Bangalore, Ramanagara, KARNATAKA (0223)'),
    ('College / School Roll Number', 'USN (University Seat Number)'),
]

FORM_SELECTIONS = [
    ('Reason for doing this course', 'Earn mandatory SWAYAM Credits',
     'Applicable where the course is offered as part of the SAMUDI Basket.'),
    ('Final certification exam registration', 'No, my college is conducting an exam for this course separately.',
     None),
]

PLEASE_NOTE = [
    'Students cannot opt for the same SAMUDI course that they have already registered for or completed in the '
    'previous semester. They are required to choose a different course from the approved list.',
    'Students in the final year of any programme are not permitted to opt for SWAYAM courses.',
    'The SWAYAM Coordinator shall brief the Faculty-in-Charge on the SWAYAM registration process, eligibility '
    'criteria, and assessment requirements. The Faculty-in-Charge shall ensure that students are adequately guided '
    'through the enrollment process and comply with the prescribed timelines and guidelines.',
]

# LTPE structure and assessment pattern — identical for every course in the list.
ASSESSMENT = dict(type='Theory', credits=3, ltpe='3-0-0-0',
                  ia_max=25, ia_min=10, ese_max=75, ese_min=30, pass_marks=40)

MENTEE_STEPS = [
    ('Log in to SWAYAM', 'Sign in at onlinecourses.swayam2.ac.in with your registered student account.'),
    ('Open your course', 'From “My Courses” on the student dashboard.'),
    ('Go to the course', 'Select the course (e.g. “Prompt Engineering”) from the Upcoming/Ongoing section and '
                         'click Go To Course.'),
    ('Open the My Mentor tab', 'Check that your mentor is available, e.g. “b.muthukumar@jainuniversity.ac.in”.'),
    ('Select your mentor by email', 'Click your mentor’s email in the list, e.g. '
                                    '“b.muthukumar@jainuniversity.ac.in”.'),
    ('Save the mentor’s email', 'Click Save.'),
    ('Confirmation', 'A green pop-up confirms your mentor selection.'),
    ('Verify in “My Mentor”', 'Check that your mentor’s email now shows as “My Mentor” on your course page.'),
]

MENTOR_STEPS = [
    ('Log in to SWAYAM', 'Sign in at onlinecourses.swayam2.ac.in with your registered account.'),
    ('Open your course', 'From “My Courses” on the dashboard.'),
    ('Go to the course', 'Select the course (e.g. “Prompt Engineering”) from the Upcoming/Ongoing section and '
                         'click Go To Course.'),
    ('Open the Mentee List tab', 'Click Mentee List to see every learner who selected you.'),
    ('Download the CSV', 'Download the CSV file with all weekly assessment marks of your mentees. Marks become '
                         'visible — and downloadable — only after the assessment due date has passed.'),
]


def _with_label(course):
    cat = next(c for c in CATEGORIES if c[0] == course['cat'])
    return dict(course, cat_label=cat[1], icon=cat[2], cat_short=cat[3])


SWAYAM = dict(
    cycle='AY 2026 (Odd Semester) · July Cycle',
    academic_year='AY 2026-27',
    enrolment_ends='2026-08-31',
    enrolment_ends_label='31 August 2026',
    portal='onlinecourses.swayam2.ac.in',
    chapter_id='7730',
    categories=[dict(key=k, label=l, icon=i, count=sum(1 for c in COURSES if c['cat'] == k))
                for k, l, i, _short in CATEGORIES],
    courses=[_with_label(c) for c in COURSES],
    form_fields=FORM_FIELDS,
    form_selections=FORM_SELECTIONS,
    please_note=PLEASE_NOTE,
    assessment=ASSESSMENT,
    mentee_steps=MENTEE_STEPS,
    mentor_steps=MENTOR_STEPS,
)
