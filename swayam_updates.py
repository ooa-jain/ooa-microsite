"""
Latest SWAYAM / UGC online-learning updates for the SWAYAM section of Jain Hub.

latest(db) returns up to 10 items {'title', 'url', 'source', 'date'}, newest site order first.
It re-reads the official pages at most once a day (cached in db.app_settings) and
falls back to FALLBACK, the items read from the sites on 24 Nov 2026, when the
sites cannot be reached.
"""
import html
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

CACHE_KEY = 'swayam_latest_updates'
TTL = timedelta(hours=24)

FALLBACK = [
    {'title': 'The Beta release of the new SWAYAM web portal is now available', 'url': 'https://swayam.gov.in/',
     'source': 'SWAYAM', 'date': ''},
    {'title': 'Exam registration for July 2026 semester has been extended till 5th Nov 2026',
     'url': 'https://cdnbbsr.s3waas.gov.in/s388a839f2f6f1427879fc33ee4acf4f66/uploads/2026/10/20261031907523999.pdf',
     'source': 'SWAYAM', 'date': 'Oct 2026'},
    {'title': 'Exam dates for the July 2026 semester courses', 'url': 'https://nta.ac.in/Download/Notice/Notice_20260917165604.pdf',
     'source': 'SWAYAM · NTA', 'date': '17 Sep 2026'},
    {'title': 'Approved list of SWAYAM courses for July 2026 semester',
     'url': 'https://docs.google.com/spreadsheets/d/e/2PACX-1vTcRBMs2cF4lGkKJuE0p3V0RuX6fAfrpInw3CzgrU4nREFAmGJXG8c5Tr2aIn1k6A/pubhtml',
     'source': 'SWAYAM', 'date': ''},
    {'title': 'Framework for Universities to conduct Examinations for SWAYAM Courses, with FAQs',
     'url': 'https://swayam.gov.in/about_university', 'source': 'SWAYAM', 'date': ''},
    {'title': 'Extension of last date of admission for AY 2025-26 (February 2026 session) for Open and Distance '
              'Learning (ODL) and Online programmes', 'url': 'https://www.ugc.gov.in/pdfnews/2808195_Extantion-of-last-date-ODL-OL-Programmes.pdf',
     'source': 'UGC', 'date': ''},
    {'title': 'UGC (ODL Programmes & Online Programmes) Regulations, 2020 and amendments',
     'url': 'https://deb.ugc.ac.in/Regulations?Year=MhOcxUHY6jSK1R/AXKYwbg==', 'source': 'UGC · DEB', 'date': ''},
    {'title': 'Category-I HEIs entitled to offer ODL programmes',
     'url': 'https://deb.ugc.ac.in/Recognition?Type=1%2FTnWXCZ9hJQjB61C0da%2FA%3D%3D', 'source': 'UGC · DEB', 'date': ''},
]

ONLINE = re.compile(r'swayam|nptel|online|odl|mooc|distance|credit transfer|e-learning|semester|exam', re.I)
NOISE = re.compile(r'feedback|phishing|scam|login|redirect|testimonial|national coordinator|helpline|support', re.I)


def _links(page, base):
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S | re.I):
        text = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', m.group(2)))).strip(' |')
        if 25 <= len(text) <= 220:
            yield text, urljoin(base, html.unescape(m.group(1)))


def _fetch():
    import requests
    items, seen = [], set()
    hdr = {'User-Agent': 'Mozilla/5.0 (compatible; JAIN-OOA-portal)'}
    for url, source, pick in [
        ('https://swayam.gov.in/', 'SWAYAM', lambda t, u: not NOISE.search(t)),
        ('https://www.ugc.gov.in/', 'UGC', lambda t, u: ONLINE.search(t) and ('pdfnews' in u or u.endswith('.pdf'))),
    ]:
        try:
            page = requests.get(url, headers=hdr, timeout=6).text
        except Exception as e:
            logger.info(f'swayam updates: {url} unreachable ({e})')
            continue
        if source == 'SWAYAM':
            m = re.search(r'Beta release of the new SWAYAM web portal[^<]*', page)
            if m and 'beta' not in seen:
                seen.add('beta')
                items.append({'title': html.unescape(m.group(0)).strip(), 'url': url, 'source': source, 'date': ''})
        for text, link in _links(page, url):
            if text in seen or not pick(text, link):
                continue
            if source == 'SWAYAM' and not ONLINE.search(text):
                continue
            seen.add(text)
            d = re.search(r'/(20\d\d)/(\d\d)/', link)
            date = datetime(int(d.group(1)), int(d.group(2)), 1).strftime('%b %Y') if d else ''
            items.append({'title': text, 'url': link, 'source': source, 'date': date})
    return items


def latest(db, limit=10):
    row = db.app_settings.find_one({'_id': CACHE_KEY}) or {}
    if row.get('items') and row.get('at') and datetime.utcnow() - row['at'] < TTL:
        return row['items'][:limit]
    items = []
    try:
        items = _fetch()
    except Exception as e:
        logger.warning(f'swayam updates fetch failed: {e}')
    if len(items) < 3:
        items = row.get('items') or FALLBACK      # keep the last good list, else the built-in one
    else:
        # official items found today, then the regulation links the sites keep in fixed menus
        items += [f for f in FALLBACK if f['source'] == 'UGC · DEB' and f['url'] not in {i['url'] for i in items}]
    db.app_settings.update_one({'_id': CACHE_KEY}, {'$set': {'items': items, 'at': datetime.utcnow()}}, upsert=True)
    return items[:limit]
