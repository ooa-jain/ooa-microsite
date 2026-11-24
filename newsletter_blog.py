"""
Turn a newsletter email (HTML) into a blog article.

The Office of Academics newsletters come in two email layouts:
  * newer editions: a small kicker ("THE GATEKEEPERS"), a Google Drive photo, a bold heading,
    paragraphs separated by <br>, a "KEY HIGHLIGHT" line and a "Read more →" link per section
  * older editions: <h2> headings, <p> paragraphs, photos attached inline (cid:) and quotes

parse_email_html() walks the HTML once and returns the article as ordered sections:

    {'title': str, 'cover': img|None, 'sections': [section], 'links': [{label, url}], 'words': int}
    section = {'kicker': str, 'heading': str, 'blocks': [block]}
    block   = {'type': 'p'|'img'|'quote'|'highlight'|'sub'|'link', 'html'|'text'|'src'|'url'|'label': ...}

Paragraph HTML is rebuilt from escaped text with only <a>, <b> and <i>, so it is safe to render.
Images are returned as {'src': url} for web images or {'cid': content_id} for attached ones;
the caller swaps a cid for a stored copy.
"""
import re
from html import escape
from html.parser import HTMLParser

# Lines that are greetings, sign-offs or mailing-list footers, never article content
NOISE = re.compile(
    r'^(dear sir.*|dear all.*|greetings from.*|regards,?|warm regards,?|thanks? (&|and) regards,?|'
    r'office of academics?|office of academic affairs.*|jain \(deemed.*|jain university.*|'
    r'copyrights? ©.*|©.*|all rights reserved.*|thoughts, suggestions, feedback.*|please send to us\.?|'
    r'our mailing address is.*|you are receiving this email.*|want to change how you receive.*|'
    r'you can unsubscribe.*|unsubscribe.*|update your preferences.*|have a minute\?.*|'
    r'ai innovation newsletter \|.*|.*\bedition\s*(no\.?\s*\d+)?$|edition no\.? ?\d+|'
    r'j ?ai ?n building an ai.?first education institute)$', re.I)
HIGHLIGHT = re.compile(r'^\W*key\s*highlights?\W*$', re.I)
EXPLORE = re.compile(r'^\W*(explore further|further reading|read more|useful links)\W*$', re.I)
BLOCK_TAGS = {'p', 'div', 'td', 'tr', 'table', 'tbody', 'li', 'ul', 'ol', 'h1', 'h2', 'h3', 'h4',
              'blockquote', 'center', 'section', 'article'}
SKIP_TAGS = {'style', 'script', 'head', 'title'}


def _size_is_big(style, font_size_attr):
    """True for heading-sized text: >= 17px, >= 13pt or <font size=5+>."""
    if font_size_attr and font_size_attr.strip().isdigit() and int(font_size_attr) >= 5:
        return True
    m = re.search(r'font-size\s*:\s*([\d.]+)\s*(px|pt)', style or '', re.I)
    if m:
        v, unit = float(m.group(1)), m.group(2).lower()
        return v >= 17 if unit == 'px' else v >= 13
    return False


def drive_image(url):
    """Google Drive share links → a direct, embeddable image URL."""
    m = re.search(r'drive\.google\.com/(?:uc\?(?:[^#]*&)?id=|file/d/|open\?id=|thumbnail\?id=)([\w-]{20,})', url)
    return f'https://drive.google.com/thumbnail?id={m.group(1)}&sz=w1600' if m else url


class _Walker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []          # open tags with their flags
        self.runs = []           # current line: [(text, bold, italic, href, big)]
        self.lines = []          # flushed: {'kind': 'text'|'img', ...}
        self.skip = 0

    # ---- context helpers
    def _flag(self, name):
        return any(f.get(name) for _, f in self.stack)

    def _href(self):
        for _, f in reversed(self.stack):
            if f.get('href'):
                return f['href']
        return None

    def _heading_tag(self):
        for t, _ in reversed(self.stack):
            if t in ('h1', 'h2', 'h3', 'h4'):
                return t
        return None

    def flush(self):
        runs, self.runs = self.runs, []
        text = re.sub(r'\s+', ' ', ''.join(r[0] for r in runs)).strip()
        if not text:
            return
        solid = [r for r in runs if r[0].strip()]
        self.lines.append({
            'kind': 'text', 'text': text, 'runs': runs,
            'bold': all(r[1] for r in solid), 'big': any(r[4] for r in solid),
            'center': self._flag('center'), 'quote': self._flag('quote'), 'htag': self._heading_tag(),
            'only_link': bool(solid) and all(r[3] for r in solid) and len({r[3] for r in solid}) == 1,
        })

    # ---- parser callbacks
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP_TAGS:
            self.skip += 1
            return
        if tag == 'br':
            self.flush()
            return
        if tag == 'img':
            self.flush()
            src, alt = (a.get('src') or '').strip(), (a.get('alt') or '').strip()
            try:
                w = int(re.sub(r'\D', '', a.get('width') or '') or 0)
            except ValueError:
                w = 0
            self.lines.append({'kind': 'img', 'src': src, 'alt': alt, 'width': w})
            return
        if tag in BLOCK_TAGS:
            self.flush()
        style = a.get('style') or ''
        flags = {
            'bold': tag in ('b', 'strong') or bool(re.search(r'font-weight\s*:\s*(bold|[6-9]00)', style)),
            'italic': tag in ('i', 'em'),
            'big': _size_is_big(style, a.get('size') if tag == 'font' else None) or tag in ('h1', 'h2', 'h3'),
            'center': (a.get('align') or '').lower() == 'center' or 'text-align:center' in style.replace(' ', ''),
            'quote': tag == 'blockquote',
            'href': a.get('href') if tag == 'a' and (a.get('href') or '').startswith(('http://', 'https://')) else None,
        }
        self.stack.append((tag, flags))

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if tag in BLOCK_TAGS:
            self.flush()
        for i in range(len(self.stack) - 1, -1, -1):     # close the nearest matching tag
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.skip or not data:
            return
        self.runs.append((data, self._flag('bold'), self._flag('italic'), self._href(), self._flag('big')))


def _runs_html(runs):
    """Escaped text with only <a>, <b>, <i> kept; adjacent runs with the same style are merged."""
    out, cur = [], None
    for text, b, i, href, _ in runs:
        key = (b, i, href)
        if cur and cur[0] == key:
            cur[1].append(text)
        else:
            cur = (key, [text])
            out.append(cur)
    html = []
    for (b, i, href), parts in out:
        t = escape(re.sub(r'\s+', ' ', ''.join(parts)))
        if not t.strip():
            html.append(t)
            continue
        if b:
            t = f'<b>{t}</b>'
        if i:
            t = f'<i>{t}</i>'
        if href:
            t = f'<a href="{escape(href, quote=True)}" target="_blank" rel="noopener">{t}</a>'
        html.append(t)
    return re.sub(r'\s+', ' ', ''.join(html)).strip()


def _is_heading(ln):
    t = ln['text']
    if len(t) > 120 or HIGHLIGHT.match(t):
        return False
    if ln['htag'] in ('h2', 'h3', 'h4'):
        return True
    if ln['big'] and len(t) <= 110:
        return True
    if ln['bold'] and not ln['only_link'] and len(t) <= 100 and not t.endswith(('.', ',', ';')):
        return True
    return t.isupper() and ln['center'] and 3 < len(t) <= 60


def parse_email_html(html):
    w = _Walker()
    w.feed(html)
    w.close()
    w.flush()

    title, sections, links, words = '', [], [], 0
    mode = None                                     # 'highlight' | 'explore'
    cur = {'kicker': '', 'heading': '', 'blocks': []}

    def has_text(sec):
        return any(b['type'] in ('p', 'quote', 'highlight') for b in sec['blocks'])

    def push():
        if cur['heading'] or cur['blocks']:
            sections.append(cur)

    for ln in w.lines:
        if ln['kind'] == 'img':
            src = ln['src']
            if ln['width'] and ln['width'] <= 200:              # logos and badges
                continue
            if re.search(r'\b(logo|jain|icon|spacer|pixel|tracking)\b', ln['alt'], re.I):
                continue
            if src.startswith('cid:'):
                cur['blocks'].append({'type': 'img', 'cid': src[4:]})
            elif src.startswith(('http://', 'https://')) and not re.search(r'(open|track|pixel)\.(gif|png)|/o/|1x1', src):
                cur['blocks'].append({'type': 'img', 'src': drive_image(src)})
            continue

        t = ln['text']
        if ln['htag'] == 'h1' and not title:
            title = t
            continue
        if NOISE.match(t) or (title and t == title):
            continue
        if HIGHLIGHT.match(t):
            mode = 'highlight'
            continue
        if EXPLORE.match(t) and len(t) < 40:
            mode = 'explore'
            continue

        if mode == 'explore':
            linked = [r for r in ln['runs'] if r[3] and r[0].strip()]
            if linked and sum(len(r[0]) for r in linked) >= 0.6 * len(t):
                by_url = {}
                for r in linked:                       # several links can sit on one line
                    by_url.setdefault(r[3], []).append(r[0])
                for url, parts in by_url.items():
                    if not any(l['url'] == url for l in links):
                        links.append({'label': re.sub(r'\s+', ' ', ''.join(parts)).strip().rstrip(' →'), 'url': url})
                continue
            mode = None

        if ln['only_link']:                                    # "Read the article →"
            href = next(r[3] for r in ln['runs'] if r[3])
            cur['blocks'].append({'type': 'link', 'label': t.rstrip(' →'), 'url': href})
            if not any(l['url'] == href for l in links):
                links.append({'label': t.rstrip(' →'), 'url': href})
            continue

        if mode == 'highlight':
            cur['blocks'].append({'type': 'highlight', 'html': _runs_html(ln['runs'])})
            words += len(t.split())
            mode = None
            continue

        if _is_heading(ln):
            if not has_text(cur) and cur['heading']:
                # An upper-case label ("THE GATEKEEPERS"), maybe with its photo, names the next heading
                if cur['heading'].isupper() and not cur['kicker']:
                    cur['kicker'], cur['heading'] = cur['heading'], t
                    continue
                # two headings in a row: the second is a sub-heading
                if not cur['blocks'] or all(b['type'] == 'sub' for b in cur['blocks']):
                    cur['blocks'].append({'type': 'sub', 'text': t})
                    continue
            push()
            cur = {'kicker': '', 'heading': t, 'blocks': []}
            continue

        kind = 'quote' if ln['quote'] else 'p'
        cur['blocks'].append({'type': kind, 'html': _runs_html(ln['runs'])})
        words += len(t.split())

    push()
    cover = next((b for s in sections for b in s['blocks'] if b['type'] == 'img'), None)
    # an opening banner photo with no heading or text becomes the cover only
    if sections and not sections[0]['heading'] and all(b['type'] == 'img' for b in sections[0]['blocks']):
        sections.pop(0)
    # drop empty shells (a heading with nothing under it, other than a lone sub-heading)
    sections = [s for s in sections if s['blocks'] or s['kicker']]
    return {'title': title, 'cover': cover, 'sections': sections, 'links': links[:8], 'words': words}


def summary_of(article, n=2):
    for s in article['sections']:
        for b in s['blocks']:
            if b['type'] == 'p':
                text = re.sub(r'<[^>]+>', '', b['html'])
                if len(text) > 120:
                    parts = re.split(r'(?<=[.!?])\s+', text)
                    return ' '.join(parts[:n]).strip()
    return ''
