"""
Office of Academics announcements from the circulars sent to the HoD lists
(hods_bng@ = Bangalore, hods_kochi@ = Kochi).

They appear in Jain Hub's "Office of Academics Announcements" panel, which lists
db.ugc_data records in the 'University Notice' category. Two sources:
  1. data/hod_announcements.json — circulars already sent (seeded once; never duplicated)
  2. Gmail — sync_from_gmail() adds new circulars from the OOA mailbox, using the same
     saved Gmail connection as the newsletter sync. Newsletters and greetings are skipped.
"""
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import newsletter_feed as nf

logger = logging.getLogger(__name__)

SEED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'hod_announcements.json')
LISTS = {'hods_bng@jainuniversity.ac.in': 'Bangalore', 'hods_kochi@jainuniversity.ac.in': 'Kochi'}
GMAIL_QUERY = ('from:officeofacademicaffairs@jainuniversity.ac.in '
               '{to:hods_bng@jainuniversity.ac.in to:hods_kochi@jainuniversity.ac.in '
               'bcc:hods_bng@jainuniversity.ac.in bcc:hods_kochi@jainuniversity.ac.in} newer_than:60d')
# newsletters and seasonal greetings are not circulars
SKIP = re.compile(r'newsletter|edition|happy |greetings|diwali|independence day|teacher.?s day|new year|'
                  r'ai comes of age|when ai gets', re.I)
IST = timedelta(hours=5, minutes=30)
_seeded = False


def _doc(gmail_id, subject, sent_utc, lists):
    where = ' and '.join(lists) if lists else 'Bangalore and Kochi'
    return {
        'gmail_id': gmail_id,
        'source': 'hod-mail',
        'categories': ['University Notice'],
        'text_data': f"{subject}\n\nCircular from the Office of Academics to the Heads of Department ({where}). "
                     f"Full details were sent by email on {(sent_utc + IST):%d %b %Y}.",
        'external_link': '',
        'files': [],
        'admin_email': 'officeofacademicaffairs@jainuniversity.ac.in',
        'uploaded_at': sent_utc + IST,          # the panel shows Indian time, like admin uploads
        'hod_lists': lists,
    }


def ensure_seeded(db):
    """Add the circulars from the seed file once per process; existing ones are left alone."""
    global _seeded
    if _seeded:
        return 0
    try:
        with open(SEED_FILE, encoding='utf-8') as f:
            seed = json.load(f)
    except Exception as e:
        logger.error(f'HoD announcements seed load failed: {e}')
        return 0
    added = 0
    for row in seed:
        sent = datetime.fromisoformat(row['sent_at'].replace('Z', '+00:00')).replace(tzinfo=None)
        res = db.ugc_data.update_one({'gmail_id': row['gmail_id']},
                                     {'$setOnInsert': _doc(row['gmail_id'], row['subject'], sent, row.get('lists', []))},
                                     upsert=True)
        added += 1 if res.upserted_id else 0
    _seeded = True
    return added


def sync_from_gmail(db, creds_dict=None, max_results=30):
    """Add circulars sent to the HoD lists that are not stored yet."""
    service = nf._gmail_service(db, creds_dict)
    if service is None:
        return {'success': False, 'error': 'Gmail is not connected.'}
    resp = service.users().messages().list(userId='me', q=GMAIL_QUERY, maxResults=max_results).execute()
    added = []
    for ref in resp.get('messages', []):
        if db.ugc_data.find_one({'gmail_id': ref['id']}, {'_id': 1}):
            continue
        msg = service.users().messages().get(userId='me', id=ref['id'], format='metadata',
                                             metadataHeaders=['Subject', 'Date', 'To', 'Cc', 'Bcc']).execute()
        h = {x['name'].lower(): x['value'] for x in msg['payload'].get('headers', [])}
        subject = (h.get('subject') or '').strip()
        if not subject or SKIP.search(subject):
            continue
        rcpt = ' '.join(h.get(k, '') for k in ('to', 'cc', 'bcc')).lower()
        lists = [name for addr, name in LISTS.items() if addr in rcpt]
        try:
            sent = parsedate_to_datetime(h.get('date')).astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            sent = datetime.utcfromtimestamp(int(msg.get('internalDate', 0)) / 1000)
        db.ugc_data.insert_one(_doc(ref['id'], subject, sent, lists))
        added.append(subject)
    return {'success': True, 'added': added}
