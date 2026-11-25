"""
Latest UGC notices for Jain Hub's Announcements page, read from ugc.gov.in.

latest(db) returns up to 15 items {'title', 'date' (YYYY-MM-DD), 'url', 'more' (extra PDFs)}, newest first.
ugc.gov.in fills its Notices table from POST /Notices/Fill_Notices; the list is re-read at most every
12 hours (cached in db.app_settings). FALLBACK holds the notices read on 25 Nov 2026 for when the
site cannot be reached.
"""
import html
import logging
import threading
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

CACHE_KEY = 'ugc_latest_notices'
TTL = timedelta(hours=12)
BASE = 'https://www.ugc.gov.in/'

FALLBACK = [
 {
  "title": "UGC letter regarding: Celebration of Constitution Day on 26th November, 2026",
  "date": "2026-11-23",
  "url": "https://www.ugc.gov.in/pdfnews/0632563_Constitution-Day-2026.pdf",
  "more": []
 },
 {
  "title": "UGC Public Notice regarding: Verification of the authentication and legal status of an HEI before seeking admission.",
  "date": "2026-11-17",
  "url": "https://www.ugc.gov.in/pdfnews/8745845_Public-Notice-Fake-University.pdf",
  "more": []
 },
 {
  "title": "UGC letter regarding: Kashi Tamil Sangamam (KTS 5.0) from November 28th to December 12th, 2026 Kashi-Tamil-Sangamam-KTS Posters_KTS",
  "date": "2026-11-13",
  "url": "https://www.ugc.gov.in/pdfnews/9707555_Kashi-Tamil-Sangamam-KTS.pdf",
  "more": [
   "https://www.ugc.gov.in/pdfnews/0469641_Posters_KTS.pdf"
  ]
 },
 {
  "title": "UGC letter regarding: Celebration of BRICS Sustainable Lifestyle Week (BSLW) from 1st to 7th November 2026 under Mission LiFE.",
  "date": "2026-10-30",
  "url": "https://www.ugc.gov.in/pdfnews/6275096_Celebration-of-BRICS-Sustainable-Lifestyle-Week-(BSLW)-2026-under-Mission-LiFE.pdf",
  "more": []
 },
 {
  "title": "UGC letter regarding: Observance of Rashtriya Ekta Diwas (National Unity Day) on 31st October, 2026",
  "date": "2026-10-30",
  "url": "https://www.ugc.gov.in/pdfnews/7942181_Rashtriy-Ekta-Diwas-National-Unity-Day-2026.pdf",
  "more": []
 },
 {
  "title": "UGC letter regarding Observation of National Cyber Security Awareness Month, October 2026: Chetna Series Lecture on Cybercrime Uncovered: Threats, Prevention and Response on 27 October 2026",
  "date": "2026-10-23",
  "url": "https://www.ugc.gov.in/pdfnews/6125470_Letter-Cyber-Security-Awareness-Month.pdf",
  "more": []
 },
 {
  "title": "UGC letter regarding: Observation of the Vigilance Awareness Week from 26th October 2026 to 1st November 2026.",
  "date": "2026-10-22",
  "url": "https://www.ugc.gov.in/pdfnews/0192052_Vigilance-Awareness-Week_2026.pdf",
  "more": []
 },
 {
  "title": "UGC letter regarding Intervention on Non-Compliance with UGC Fee Refund Policy Letter-to-all-HEIs List-of-HEIs",
  "date": "2026-10-16",
  "url": "https://www.ugc.gov.in/pdfnews/4373827_Letter-to-all-HEIs.pdf",
  "more": [
   "https://www.ugc.gov.in/pdfnews/3768850_List-of-HEIs.pdf"
  ]
 },
 {
  "title": "UGC letter regarding Participation in \"Jago Grahak Jago Quiz 2026\"",
  "date": "2026-10-16",
  "url": "https://www.ugc.gov.in/pdfnews/6923757_Jago-Grahak-Jago-Quiz-2026.pdf",
  "more": []
 },
 {
  "title": "UGC letter regarding Promotion of \"Innovation for Bharat\" 2027 - Design for Bharat. Hack for Social Cause and Youth Entrepreneurs Challenge under Viksit Bharat Young leader's Dialogue (VBYLD) 2027.",
  "date": "2026-10-08",
  "url": "https://www.ugc.gov.in/pdfnews/0f8572b9adac47a5b7977b8043921ab8.pdf",
  "more": []
 },
 {
  "title": "UGC Advisory observance of Swachhata Hi Seva (SHS) Campaign 2026 from 17th September to 17th October, 2026 Swachhata-Hi-Seva-Campaign-2026 Presentation-for-SHS-2026 Swachhata-Hi-Seva-2026-Guidelines",
  "date": "2026-09-30",
  "url": "https://www.ugc.gov.in/pdfnews/Swachhata-Hi-Seva-Campaign-2026.pdf",
  "more": [
   "https://www.ugc.gov.in/pdfnews/Presentation-for-SHS-2026.pdf",
   "https://www.ugc.gov.in/pdfnews/Swachhata-Hi-Seva-2026-Guidelines.pdf"
  ]
 },
 {
  "title": "UGC Public Notice regarding UGC Notification regarding Specification of Degrees Fifth Amendment.",
  "date": "2026-09-17",
  "url": "https://www.ugc.gov.in/pdfnews/3b94684bb3344fd5aa26ee2035ad23c3.pdf",
  "more": []
 },
 {
  "title": "UGC letter regarding National Renewable Energy Quiz 2026- Re Think - Think Beyond Energy \"ऊर्जा मंथन\" for College Students.",
  "date": "2026-09-15",
  "url": "https://www.ugc.gov.in/pdfnews/f1c1496c32714728acd72b56ec5bc7af.pdf",
  "more": []
 },
 {
  "title": "UGC Letter regarding Advisory related to Rights of Persons with Disabilities (RPwD) Act, 2016",
  "date": "2026-09-14",
  "url": "https://www.ugc.gov.in/pdfnews/d07826fd59f449c5a9334a2667eeb40d.pdf",
  "more": []
 },
 {
  "title": "UGC letter regarding Mass participation in Viksit Bharat Young Leaders Dialogue (VBYLD) 2027.",
  "date": "2026-09-09",
  "url": "https://www.ugc.gov.in/pdfnews/c7f7c727d3fb4104b82c1f580ac8f802.pdf",
  "more": []
 }
]


def _row(item):
    raw = item.get('title') or ''
    links = re.findall(r'href=["\']?([^"\'\s>]+)', raw)
    links = [l if l.startswith('http') else BASE + l.replace('../', '').lstrip('/') for l in links]
    title = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', raw))).strip()
    return {'title': title, 'date': (item.get('created') or '')[:10],
            'url': links[0] if links else BASE + 'Notices', 'more': links[1:4]}


def _fetch(limit=15):
    import requests
    r = requests.post(BASE + 'Notices/Fill_Notices', data={'ID': 0, 'type': 'NoticeGrid'},
                      headers={'User-Agent': 'Mozilla/5.0 (compatible; JAIN-OOA-portal)'}, timeout=8)
    data = r.json()
    items = [_row(i) for i in data.get('List', []) if i.get('title')]
    items.sort(key=lambda x: x['date'], reverse=True)
    return items[:limit]


def _refresh(db):
    row = db.app_settings.find_one({'_id': CACHE_KEY}) or {}
    items = []
    try:
        items = _fetch()
    except Exception as e:
        logger.info(f'ugc notices: ugc.gov.in unreachable ({e})')
    if len(items) < 3:
        items = row.get('items') or FALLBACK
    db.app_settings.update_one({'_id': CACHE_KEY}, {'$set': {'items': items, 'at': datetime.utcnow()}}, upsert=True)
    return items


_busy = threading.Lock()


def latest(db, limit=15):
    """The saved list straight away; when it is older than TTL it is re-read in the background,
    so a slow or unreachable government site never holds up the page."""
    row = db.app_settings.find_one({'_id': CACHE_KEY}) or {}
    items = row.get('items') or FALLBACK
    if not (row.get('at') and datetime.utcnow() - row['at'] < TTL) and _busy.acquire(blocking=False):
        def run():
            try:
                _refresh(db)
            except Exception as e:
                logger.warning(f'{CACHE_KEY} refresh failed: {e}')
            finally:
                _busy.release()
        threading.Thread(target=run, daemon=True).start()
    return items[:limit]
