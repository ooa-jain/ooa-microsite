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


def _title(subject):
    return re.sub(r'^\s*((re|fwd?)\s*:\s*)+', '', subject or '', flags=re.I).strip()


def _doc(gmail_id, subject, sent_utc, lists, body='', files=None):
    where = ' and '.join(lists) if lists else 'Bangalore and Kochi'
    title = _title(subject)
    return {
        'gmail_id': gmail_id,
        'source': 'hod-mail',
        'categories': ['University Notice'],
        'title': title,
        'text_data': f"{title}\n\n{body}" if body else
                     f"{title}\n\nCircular from the Office of Academics to the Heads of Department ({where}). "
                     f"Full details were sent by email on {(sent_utc + IST):%d %b %Y}.",
        'body': body,
        'external_link': '',
        'files': [],                      # admin-upload file names (none for mailed circulars)
        'attachments': files or [],       # [{'name', 'url', 'size'}] templates and posters from the mail
        'admin_email': 'officeofacademicaffairs@jainuniversity.ac.in',
        'uploaded_at': sent_utc + IST,          # the panel shows Indian time, like admin uploads
        'hod_lists': lists,
    }


OFFICE_HOURS = re.compile(r'office\s*hours', re.I)
ATTACH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'files', 'hod')
URL_RE = re.compile(r'(https?://[^\s<>()]+[^\s<>().,;:!?\'"])')


def body_html(text):
    """The mail's plain text as safe HTML: paragraphs, numbered and bulleted lists, *bold*, links."""
    import html as _h
    if not text:
        return ''
    t = text.replace('\r', '')
    t = re.sub(r'([^\n<>]{2,80}?)\s*\n?\s*<(https?://[^>\s]+)>', lambda m: f'[[{m.group(1).strip()}|{m.group(2)}]]', t)
    t = re.sub(r'<(https?://[^>\s]+)>', r'\1', t)

    def inline(s):
        s = _h.escape(s, quote=False)
        s = re.sub(r'\[\[([^|\]]+)\|([^\]]+)\]\]', lambda m: f'<a href="{_h.escape(m.group(2))}" target="_blank" rel="noopener">{m.group(1)}</a>', s)
        s = re.sub(r'(?<![="\w])' + URL_RE.pattern, lambda m: f'<a href="{m.group(1)}" target="_blank" rel="noopener">{m.group(1)}</a>', s)
        s = re.sub(r'\*{1,2}([^*\n]{2,240}?)(\s*)\*{1,2}', r'<b>\1</b>\2', s)
        return s.replace('*', '')

    out = []
    for block in re.split(r'\n\s*\n', t.strip()):
        if block.strip() == '——— Earlier message ———':
            out.append('<div class="hc-earlier">Earlier message</div>')
            continue
        items, cur, kind = [], [], None
        for ln in block.split('\n'):
            m = re.match(r'\s*(\d+\.|[-·•]|[IVX]+\.)\s+(.*)', ln)
            if m:
                if cur:
                    items.append((kind, ' '.join(cur)))
                kind, cur = ('ol' if m.group(1)[0].isdigit() else 'ul'), [m.group(2).strip()]
            else:
                cur.append(ln.strip())
        if cur:
            items.append((kind, ' '.join(cur)))
        para = []
        for k, txt in items:
            if k:
                if not out or not out[-1].startswith(f'<{k}'):
                    para.append(f'<{k}>')
                para.append(f'<li>{inline(txt)}</li>')
                para.append(f'</{k}>')
            else:
                para.append(f'<p>{inline(txt)}</p>')
        html_block = ''.join(para)
        html_block = re.sub(r'</(ol|ul)><\1>', '', html_block)
        out.append(html_block)
    return re.sub(r'</(ol|ul)><\1>', '', ''.join(out))


def _kind(name):
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    return {'pdf': 'pdf', 'doc': 'doc', 'docx': 'doc', 'xls': 'sheet', 'xlsx': 'sheet', 'csv': 'sheet',
            'zip': 'zip', 'jpg': 'image', 'jpeg': 'image', 'png': 'image', 'webp': 'image',
            'ppt': 'slides', 'pptx': 'slides'}.get(ext, 'file')


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
        doc = _doc(row['gmail_id'], row['subject'], sent, row.get('lists', []), row.get('body', ''), row.get('files', []))
        res = db.ugc_data.update_one({'gmail_id': row['gmail_id']}, {'$setOnInsert': doc}, upsert=True)
        added += 1 if res.upserted_id else 0
        if not res.upserted_id and row.get('body'):
            # circulars stored before the full text was kept get it now
            db.ugc_data.update_one({'gmail_id': row['gmail_id'], 'source': 'hod-mail'},
                                   {'$set': {k: doc[k] for k in ('title', 'text_data', 'body', 'attachments')}})
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
        body, files = '', []
        try:
            full = service.users().messages().get(userId='me', id=ref['id'], format='full').execute()
            body = _plain_body(full.get('payload', {}))
            files = _save_attachments(service, ref['id'], full.get('payload', {}))
        except Exception as e:
            logger.warning(f'HoD circular {ref["id"]}: body/attachments not read ({e})')
        db.ugc_data.insert_one(_doc(ref['id'], subject, sent, lists, body, files))
        added.append(subject)
    return {'success': True, 'added': added}


def _plain_body(payload):
    """text/plain of a Gmail API payload (quoted earlier message kept, '>' markers removed)."""
    import base64
    def walk(p):
        if p.get('mimeType') == 'text/plain' and p.get('body', {}).get('data'):
            return base64.urlsafe_b64decode(p['body']['data'] + '==').decode('utf-8', 'replace')
        for c in p.get('parts', []) or []:
            r = walk(c)
            if r:
                return r
        return ''
    text = walk(payload)
    text = '\n'.join(re.sub(r'^(>\s?)+', '', ln).rstrip() for ln in text.replace('\r', '').split('\n'))
    text = re.sub(r'\[image: [^\]]*\]\n?', '', text)
    text = re.sub(r'On (Mon|Tue|Wed|Thu|Fri|Sat|Sun), [^\n]*\n?[^\n]*wrote:', '\n——— Earlier message ———', text)
    text = re.sub(r'\*?Regards,?\*?\s*\n\s*\*?Office of Academics\s*\*?\s*\n?\s*\*?JAIN \(Deemed-to-be University\)\*?', '', text)
    text = re.sub(r'^\s*-\s*$\n', '', text, flags=re.M)
    text = re.sub(r'^\s*(\d+\.)\s*\n\s*\n?\s*', r'\1 ', text, flags=re.M)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return re.sub(r'(——— Earlier message ———\s*)+$', '', text.strip()).strip()


def _save_attachments(service, gmail_id, payload, limit_mb=12):
    """Templates and posters attached to the circular, saved under static/files/hod/<gmail_id>/."""
    out = []
    def walk(p):
        if p.get('filename') and p.get('body', {}).get('attachmentId'):
            yield p
        for c in p.get('parts', []) or []:
            yield from walk(c)
    for part in walk(payload):
        if part['body'].get('size', 0) > limit_mb * 1024 * 1024 or not part['filename'].lower().endswith('.pdf'):
            continue                      # announcements carry PDFs only
        import base64
        data = service.users().messages().attachments().get(userId='me', messageId=gmail_id,
                                                             id=part['body']['attachmentId']).execute()
        raw = base64.urlsafe_b64decode(data['data'] + '==')
        safe = re.sub(r'[^A-Za-z0-9 ._,&()-]+', '', part['filename']).strip() or 'attachment'
        d = os.path.join(ATTACH_DIR, gmail_id)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, safe), 'wb') as f:
            f.write(raw)
        out.append({'name': part['filename'], 'url': f'/static/files/hod/{gmail_id}/{safe}', 'size': len(raw)})
    return out


def for_page(db, category='University Notice', limit=60):
    """Notices of one category ('University Notice' = Office of Academics, 'UGC') for the Announcements page."""
    rows = []
    for d in db.ugc_data.find({'categories': category}).sort('uploaded_at', -1).limit(limit):
        text = d.get('text_data') or ''
        title = d.get('title') or text.split('\n', 1)[0].strip()
        body = d.get('body') if d.get('source') == 'hod-mail' else text.split('\n', 1)[1].strip() if '\n' in text else ''
        files = list(d.get('attachments') or [])
        for f in d.get('files') or []:          # admin uploads
            files.append({'name': f, 'url': f'/uploads/{f}', 'size': 0})
        files = [dict(f, kind=_kind(f['name'])) for f in files]
        files = [f for f in files if f['kind'] == 'pdf']        # PDFs only on the Announcements page
        if OFFICE_HOURS.search(_title(title)):
            continue                                            # sessions are listed in the Office Hours gallery
        rows.append({
            'id': str(d['_id']), 'title': _title(title), 'date': d.get('uploaded_at'),
            'lists': d.get('hod_lists') or [], 'body_html': body_html(body),
            'excerpt': re.sub(r'\s+', ' ', re.sub(r'[*>]|<https?://[^>]+>|——— Earlier message ———', '', body or ''))[:220].strip(),
            'files': files, 'link': d.get('external_link') or '',
            'mail': d.get('source') == 'hod-mail',
        })
    return rows


OFFICE_HOURS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'office_hours.json')


def office_hours():
    """Academic Office Hours sessions (newest first) with their posters, for the sessions gallery."""
    try:
        with open(OFFICE_HOURS_FILE, encoding='utf-8') as f:
            rows = json.load(f)
    except Exception as e:
        logger.error(f'office hours load failed: {e}')
        return []
    for r in rows:
        try:
            r['date_label'] = datetime.strptime(r['date'], '%Y-%m-%d').strftime('%d %b %Y')
        except Exception:
            r['date_label'] = r.get('date', '')
    return sorted(rows, key=lambda r: r.get('date', ''), reverse=True)
