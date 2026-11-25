"""
OOA monthly AI Innovation Newsletter feed.

Editions live in db.ooa_newsletters, newest first. They come from two places:
  1. data/ooa_newsletters.json — curated digests of the editions already sent
     (seeded on first use; re-seeding never overwrites an existing edition).
  2. Gmail — sync_from_gmail() reads the Office of Academics mailbox for new
     editions sent to the HoD lists and adds them automatically. It runs from
     the monthly /cron/sync-newsletters endpoint and from the admin button.

Each edition is shown as a blog article. refresh_articles() re-reads the original
email (HTML), keeps every section with its photos, and stores photos that were
attached to the email (cid: images) in db.ooa_newsletter_images, served by the
/ai-newsletter/img/<id> route. Photos linked from Google Drive are used directly.
"""
import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import newsletter_blog as nb

logger = logging.getLogger(__name__)

SEED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'ooa_newsletters.json')
ARTICLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'newsletter_articles')

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
def load_article_file(slug):
    """Full article for an edition from data/newsletter_articles/<slug>.txt, or None.

    Format (one item per line; blank lines ignored):
        cover: <image url>
        deck: <subtitle>
        ## <kicker> | <heading>        (or "## <heading>")
        p: <paragraph>                 (**bold** and [label](url) allowed)
        img: <image url>
        hl: <key highlight>
        q: <quote>
        sub: <sub-heading>
        link: <label> | <url>          (read-more link in the section)
        more: <label> | <url>          (Explore further list)
    """
    path = os.path.join(ARTICLE_DIR, f'{slug}.txt')
    if not os.path.exists(path):
        return None
    from html import escape as _esc

    def rich(t):
        t = _esc(t, quote=False)
        t = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t)
        t = re.sub(r'(?<![*\w])\*(?!\s)([^*]+?)\*(?![*\w])', r'<i>\1</i>', t)
        return re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+)\)',
                      lambda m: f'<a href="{_esc(m.group(2), quote=True)}" target="_blank" rel="noopener">{m.group(1)}</a>', t)

    art = {'sections': [], 'links': [], 'words': 0, 'deck': '', 'source': 'seed'}
    cover, cur = '', None
    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#!'):
                continue
            if line.startswith('## '):
                k, _, h = line[3:].partition(' | ')
                cur = {'kicker': k.strip() if h else '', 'heading': (h or k).strip(), 'blocks': []}
                art['sections'].append(cur)
                continue
            key, _, val = line.partition(': ')
            val = val.strip()
            if key == 'cover':
                cover = val
                continue
            if key == 'deck':
                art['deck'] = val
                continue
            if key == 'more':
                label, _, url = val.partition(' | ')
                art['links'].append({'label': label.strip(), 'url': url.strip()})
                continue
            if cur is None:
                cur = {'kicker': '', 'heading': '', 'blocks': []}
                art['sections'].append(cur)
            if key == 'img':
                cur['blocks'].append({'type': 'img', 'src': val})
            elif key == 'link':
                label, _, url = val.partition(' | ')
                cur['blocks'].append({'type': 'link', 'label': label.strip(), 'url': url.strip()})
            elif key == 'sub':
                cur['blocks'].append({'type': 'sub', 'text': val})
            elif key in ('p', 'hl', 'q'):
                cur['blocks'].append({'type': {'p': 'p', 'hl': 'highlight', 'q': 'quote'}[key], 'html': rich(val)})
                art['words'] += len(val.split())
    images = [b['src'] for s_ in art['sections'] for b in s_['blocks'] if b['type'] == 'img']
    return {'article': art, 'cover_image': cover or (images[0] if images else ''),
            'images': images, 'read_minutes': max(1, round(art['words'] / 200))}


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
        full = load_article_file(ed['slug'])
        if full:
            # the curated file is the complete edition (every section and picture of the email): it wins
            stored = db.ooa_newsletters.find_one({'gmail_id': ed['gmail_id']}, {'article': 1, 'cover_image': 1}) or {}
            if stored.get('article') != full['article'] or stored.get('cover_image') != full['cover_image']:
                db.ooa_newsletters.update_one({'gmail_id': ed['gmail_id']}, {'$set': full})
            continue
        # photos added to the seed later reach editions that are already stored
        for key in ('cover_image', 'images'):
            if ed.get(key) and not res.upserted_id:
                db.ooa_newsletters.update_one({'gmail_id': ed['gmail_id'], key: {'$in': [None, '', []]}},
                                              {'$set': {key: ed[key]}})
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
    art = d.get('article') or {}
    if not d.get('read_minutes'):
        words = art.get('words') or sum(len((s.get('heading', '') + ' ' + s.get('body', '')).split())
                                         for s in d.get('sections') or []) + len((d.get('summary') or '').split())
        d['read_minutes'] = max(1, round(words / 200))
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


def _html_body(payload):
    if payload.get('mimeType') == 'text/html' and payload.get('body', {}).get('data'):
        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', 'replace')
    for part in payload.get('parts', []) or []:
        t = _html_body(part)
        if t:
            return t
    return ''


def _inline_parts(payload, out=None):
    """Content-ID → MIME part, for photos attached inside the email."""
    out = {} if out is None else out
    headers = {h['name'].lower(): h['value'] for h in payload.get('headers', []) or []}
    cid = (headers.get('content-id') or headers.get('x-attachment-id') or '').strip('<> ')
    if cid and (payload.get('mimeType') or '').startswith('image/'):
        out[cid] = payload
    for part in payload.get('parts', []) or []:
        _inline_parts(part, out)
    return out


def _store_inline_images(service, db, msg, article):
    """Download the email's attached photos once and point the article at the stored copies."""
    parts = _inline_parts(msg['payload'])
    n = 0
    for sec in article['sections']:
        for b in sec['blocks']:
            if b['type'] != 'img' or 'cid' not in b:
                continue
            part = parts.get(b.pop('cid'))
            if not part:
                b['type'] = 'skip'
                continue
            n += 1
            img_id = f"{msg['id']}-{n}"
            if not db.ooa_newsletter_images.find_one({'_id': img_id}, {'_id': 1}):
                body = part.get('body', {})
                data = body.get('data')
                if not data and body.get('attachmentId'):
                    data = service.users().messages().attachments().get(
                        userId='me', messageId=msg['id'], id=body['attachmentId']).execute().get('data')
                if not data:
                    b['type'] = 'skip'
                    continue
                db.ooa_newsletter_images.replace_one({'_id': img_id}, {
                    '_id': img_id, 'mime': part.get('mimeType', 'image/jpeg'),
                    'data': base64.urlsafe_b64decode(data), 'gmail_id': msg['id']}, upsert=True)
            b['src'] = f'/ai-newsletter/img/{img_id}'
        sec['blocks'] = [b for b in sec['blocks'] if b['type'] != 'skip']
    # the email's opening banner is the cover; otherwise use the first photo in the article
    if not (article['cover'] and article['cover'].get('src')):
        article['cover'] = next((b for s in article['sections'] for b in s['blocks'] if b['type'] == 'img'), None)
    return article


def article_fields(service, db, msg):
    """Blog fields for one message: full sections with photos, cover, links and reading time."""
    html = _html_body(msg['payload'])
    if not html:
        return None
    article = nb.parse_email_html(html)
    if sum(1 for s in article['sections'] if any(b['type'] == 'p' for b in s['blocks'])) < 1:
        return None
    article = _store_inline_images(service, db, msg, article)
    fields = {
        'article': {'sections': article['sections'], 'words': article['words'], 'deck': article.get('deck', '')},
        'cover_image': (article['cover'] or {}).get('src', ''),
        'read_minutes': max(1, round(article['words'] / 200)),
    }
    if article['links']:
        fields['article']['links'] = article['links']
    return fields


def refresh_articles(db, creds_dict=None, only_missing=False):
    """Re-read each stored edition's email and save the full article with its photos."""
    service = _gmail_service(db, creds_dict)
    if service is None:
        return {'success': False, 'error': 'Gmail is not connected for the newsletter sync.'}
    q = {'gmail_id': {'$exists': True}, 'article.source': {'$ne': 'seed'}}   # curated articles are kept
    if only_missing:
        q['article'] = {'$exists': False}
    updated, failed = [], []
    for ed in db.ooa_newsletters.find(q, {'gmail_id': 1, 'edition': 1, 'summary': 1}):
        try:
            msg = service.users().messages().get(userId='me', id=ed['gmail_id'], format='full').execute()
            fields = article_fields(service, db, msg)
            if not fields:
                failed.append(ed.get('edition', ed['gmail_id']))
                continue
            db.ooa_newsletters.update_one({'_id': ed['_id']}, {'$set': fields})
            updated.append(ed.get('edition', ed['gmail_id']))
        except Exception as e:
            logger.warning(f"newsletter refresh failed for {ed.get('gmail_id')}: {e}")
            failed.append(ed.get('edition', ed['gmail_id']))
    return {'success': True, 'updated': updated, 'failed': failed}


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
        try:
            doc.update(article_fields(service, db, msg) or {})
        except Exception as e:
            logger.warning(f"newsletter article parse failed for {ref['id']}: {e}")
        db.ooa_newsletters.insert_one(doc)
        added.append(doc['edition'] + ' — ' + doc['title'])
    return {'success': True, 'added': added, 'skipped': skipped}
