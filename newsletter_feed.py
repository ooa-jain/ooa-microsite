"""
OOA monthly AI Innovation Newsletter feed.

Editions live in db.ooa_newsletters, newest first. They come from two places:
  1. data/ooa_newsletters.json — curated digests of the editions already sent
     (seeded on first use; re-seeding never overwrites an existing edition).
  2. Gmail — sync_from_gmail() reads the Office of Academics mailbox for new
     editions sent to the HoD lists and adds them automatically. It runs from
     the monthly /cron/sync-newsletters endpoint and from the admin button.
"""
import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

SEED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'ooa_newsletters.json')

# Monthly editions are sent from the OOA mailbox to the HoD distribution lists.
GMAIL_QUERY = os.getenv(
    'NEWSLETTER_GMAIL_QUERY',
    'from:officeofacademicaffairs@jainuniversity.ac.in '
    '(to:hods_bng@jainuniversity.ac.in OR to:hods_kochi@jainuniversity.ac.in) '
    '(newsletter OR edition OR "Office of Academic Affairs") -subject:(BoS OR AQAR OR review OR survey OR notification)'
)
SETTINGS_KEY = 'gmail_newsletter_creds'
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
          'August', 'September', 'October', 'November', 'December']


# ─────────────────────────────────────────────────────────────────────
#  Storage
# ─────────────────────────────────────────────────────────────────────
def ensure_seeded(db):
    """Insert curated editions that are not in the database yet."""
    try:
        with open(SEED_FILE, encoding='utf-8') as f:
            seed = json.load(f)
    except Exception as e:
        logger.error(f'newsletter seed load failed: {e}')
        return 0
    added = 0
    for ed in seed:
        doc = dict(ed)
        doc['sent_at'] = _parse_iso(ed['sent_at'])
        doc['source'] = 'seed'
        res = db.ooa_newsletters.update_one({'gmail_id': ed['gmail_id']}, {'$setOnInsert': doc}, upsert=True)
        added += 1 if res.upserted_id else 0
    return added


def list_editions(db, limit=None):
    cur = db.ooa_newsletters.find({'hidden': {'$ne': True}}).sort('sent_at', -1)
    if limit:
        cur = cur.limit(limit)
    return [_public(d) for d in cur]


def get_edition(db, slug):
    d = db.ooa_newsletters.find_one({'slug': slug, 'hidden': {'$ne': True}})
    return _public(d) if d else None


def _public(d):
    d = dict(d)
    d['_id'] = str(d.get('_id'))
    sent = d.get('sent_at')
    if isinstance(sent, datetime):
        d['sent_label'] = sent.strftime('%d %b %Y')
    return d


def _parse_iso(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00')).replace(tzinfo=None)


# ─────────────────────────────────────────────────────────────────────
#  Gmail parsing — turns one newsletter email into an edition document
# ─────────────────────────────────────────────────────────────────────
_NOISE = re.compile(r'^(\[image:.*\]|dear sir.*|greetings from.*|regards,?|\*?office of academic.*|jain \(deemed.*|'
                    r'unsubscribe|thoughts, suggestions, feedback.*|copyrights? ©.*|your monthly ai)$', re.I)
_URL = re.compile(r'<(https?://[^>\s]+)>')


def _clean_url(u):
    u = re.sub(r'[?&]utm_[^&]+', '', u)
    return u.rstrip('?&')


def _paragraphs(text):
    text = text.replace('\r', '')
    text = re.sub(r'(?m)^>.*$', '', text)          # drop quoted replies
    paras = []
    for block in re.split(r'\n\s*\n', text):
        line = ' '.join(l.strip() for l in block.split('\n') if l.strip())
        line = line.replace('*', '').strip()
        if not line or _NOISE.match(line):
            continue
        paras.append(line)
    # newsletters sometimes repeat each paragraph twice in plain text
    out = []
    for p in paras:
        if not out or out[-1] != p:
            out.append(p)
    return out


def parse_newsletter(msg_id, subject, sent_at, body):
    """Build an edition dict from a plain-text newsletter email."""
    links = []
    for m in re.finditer(r'([^\n<>]{3,120}?)\s*\n?<(https?://[^>\s]+)>', body):
        label = re.sub(r'\s+', ' ', m.group(1)).strip(' →:-*')
        url = _clean_url(m.group(2))
        if 'mailchannels' in url or 'docs.google.com/forms' in url or 'forms.gle' in url:
            continue
        if label and not any(l['url'] == url for l in links):
            links.append({'label': label[-90:], 'url': url})
    text = _URL.sub('', body)
    paras = _paragraphs(text)

    title = re.sub(r'^(fwd?:|re:)\s*', '', subject, flags=re.I).strip()
    title = re.split(r'\s+(?:\|\||–|-)\s+(?=[A-Z][a-z]+ (?:20\d\d|Edition))', title)[0]

    # body headings are short lines without terminal punctuation; content is the paragraph after
    sections, i = [], 0
    while i < len(paras) - 1 and len(sections) < 5:
        h, nxt = paras[i], paras[i + 1]
        is_heading = 8 <= len(h) <= 90 and not h.endswith(('.', ':', '?', '!')) and len(nxt) > 120
        if is_heading and h.lower() not in title.lower():
            sections.append({'heading': h, 'body': _first_sentences(nxt, 3)})
            i += 2
        else:
            i += 1
    long_paras = [p for p in paras if len(p) > 140]
    summary = _first_sentences(long_paras[0], 2) if long_paras else ''

    edition = _edition_label(subject + ' ' + ' '.join(paras[:4]), sent_at)
    slug = f"{sent_at:%Y-%m}-" + re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:60]
    return {
        'gmail_id': msg_id, 'slug': slug, 'edition': edition, 'sent_at': sent_at,
        'title': title, 'theme': '', 'summary': summary,
        'sections': sections, 'links': links[:6], 'source': 'gmail',
    }


def _first_sentences(p, n):
    parts = re.split(r'(?<=[.!?])\s+', p)
    return ' '.join(parts[:n]).strip()


def _edition_label(text, sent_at):
    m = re.search(r'\b(' + '|'.join(MONTHS) + r')\b[\s\-–|]*(20\d\d)?', text)
    if m:
        return f"{m.group(1)} {m.group(2) or sent_at.year}"
    return f"{MONTHS[sent_at.month - 1]} {sent_at.year}"


# ─────────────────────────────────────────────────────────────────────
#  Gmail sync
# ─────────────────────────────────────────────────────────────────────
def save_creds(db, creds_dict, saved_by):
    """Remember the OOA mailbox token (with refresh token) for the monthly sync."""
    if not creds_dict.get('refresh_token'):
        return False
    db.app_settings.update_one({'_id': SETTINGS_KEY},
                               {'$set': {'creds': creds_dict, 'saved_by': saved_by,
                                         'saved_at': datetime.utcnow()}}, upsert=True)
    return True


def _gmail_service(db, creds_dict=None):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    if creds_dict is None:
        row = db.app_settings.find_one({'_id': SETTINGS_KEY}) or {}
        creds_dict = row.get('creds')
    if not creds_dict:
        return None
    c = Credentials(token=creds_dict.get('token'), refresh_token=creds_dict.get('refresh_token'),
                    token_uri=creds_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
                    client_id=creds_dict.get('client_id'), client_secret=creds_dict.get('client_secret'),
                    scopes=creds_dict.get('scopes'))
    return build('gmail', 'v1', credentials=c, cache_discovery=False)


def _plain_body(payload):
    if payload.get('mimeType') == 'text/plain' and payload.get('body', {}).get('data'):
        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', 'replace')
    for part in payload.get('parts', []) or []:
        t = _plain_body(part)
        if t:
            return t
    return ''


def sync_from_gmail(db, creds_dict=None, max_results=25):
    """Fetch newsletter emails not yet stored and add them. Returns a result dict."""
    service = _gmail_service(db, creds_dict)
    if service is None:
        return {'success': False, 'error': 'Gmail is not connected for the newsletter sync.'}
    resp = service.users().messages().list(userId='me', q=GMAIL_QUERY, maxResults=max_results).execute()
    added, skipped = [], 0
    for ref in resp.get('messages', []):
        if db.ooa_newsletters.find_one({'gmail_id': ref['id']}):
            skipped += 1
            continue
        msg = service.users().messages().get(userId='me', id=ref['id'], format='full').execute()
        headers = {h['name'].lower(): h['value'] for h in msg['payload'].get('headers', [])}
        try:
            sent_at = parsedate_to_datetime(headers.get('date')).astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            sent_at = datetime.utcfromtimestamp(int(msg.get('internalDate', 0)) / 1000)
        body = _plain_body(msg['payload'])
        if len(body) < 800:          # too short to be a newsletter edition
            skipped += 1
            continue
        doc = parse_newsletter(ref['id'], headers.get('subject', 'Newsletter'), sent_at, body)
        # one edition per month — a resend of the same month is ignored
        if db.ooa_newsletters.find_one({'edition': doc['edition']}):
            skipped += 1
            continue
        db.ooa_newsletters.insert_one(doc)
        added.append(doc['edition'] + ' — ' + doc['title'])
    return {'success': True, 'added': added, 'skipped': skipped}
