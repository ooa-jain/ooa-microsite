"""Parser tests for the two newsletter email layouts (run: python3 -m pytest tests/test_newsletter_blog.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import newsletter_blog as nb  # noqa: E402

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')


def load(name):
    with open(os.path.join(HERE, name), encoding='utf-8') as f:
        return nb.parse_email_html(f.read())


def test_drive_layout():
    a = load('newsletter_drive_layout.html')
    assert a['title'].startswith('AI Comes of Age')
    assert a['cover']['src'].startswith('https://drive.google.com/thumbnail?id=1uVRS')
    heads = [(s['kicker'], s['heading']) for s in a['sections']]
    assert heads[0] == ('', 'EDITORIAL - The Battle is no Longer Just About Better AI')
    assert heads[1] == ('THE GATEKEEPERS', 'Amazon blocks. Walmart opens the door.')
    gate = [b['type'] for b in a['sections'][1]['blocks']]
    assert gate == ['img', 'p', 'p', 'highlight', 'link']
    assert '<b>Agent Gateway</b>' in a['sections'][1]['blocks'][2]['html']
    assert [l['label'] for l in a['links']] == ['While Amazon blocks AI agents, Walmart rolls out the welcome mat', 'Introducing Dots']
    text = ' '.join(b.get('html', '') for s in a['sections'] for b in s['blocks'])
    assert 'Regards' not in text and 'Office of Academic Affairs' not in text


def test_inline_layout():
    a = load('newsletter_inline_layout.html')
    assert a['title'] == 'Introduction to Vibe Coding'
    assert a['cover'] == {'type': 'img', 'cid': 'ii_mpwgefsm1'}          # the logo (width 172) is skipped
    heads = [s['heading'] for s in a['sections']]
    assert heads[:3] == ['Welcome to the Vibe✨', 'What makes it feel different?✌️', 'Why does it matter for learners?']
    assert [b['type'] for b in a['sections'][0]['blocks']] == ['p', 'p', 'img', 'quote']
    assert a['sections'][2]['blocks'] == [{'type': 'img', 'cid': 'ii_mpwgeft33'}]
    assert 'Dear Sir' not in str(a) and 'June 2026 Edition' not in str(a)


def test_escaping():
    a = nb.parse_email_html('<p><b>Heading here</b></p><p>Text with &lt;script&gt;alert(1)&lt;/script&gt; and more words to make it a paragraph that is long enough.</p>'
                            '<p><a href="javascript:alert(1)">bad link</a> stays plain text in a long enough sentence here.</p>')
    html = ' '.join(b['html'] for s in a['sections'] for b in s['blocks'] if b['type'] == 'p')
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'javascript:' not in html


def test_drive_urls():
    assert nb.drive_image('https://drive.google.com/uc?export=view&id=1SIhZcP8SdGmYZylGGFbjdbqm12cgfWTe') == \
        'https://drive.google.com/thumbnail?id=1SIhZcP8SdGmYZylGGFbjdbqm12cgfWTe&sz=w1600'
    assert nb.drive_image('https://example.com/a.png') == 'https://example.com/a.png'
