#!/usr/bin/env python3
# =============================================================================
# HY-RV | check_site
# Description: Check the committed site links and anchors.
# Purpose: Computer architecture and RTL design education and lab exercises.
# Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
# Website: https://dsa.hanyang.ac.kr
# Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
# AI tools such as Codex or Claude may have assisted in creating or modifying
# this file. See applicable manifests and verification records for provenance.
# Preserve existing license, copyright, and original author notices.
# =============================================================================

"""Check all internal HTML links and anchors in the public lesson site."""
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1] / 'docs'

class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.ids, self.links = set(), []
        self.feed(path.read_text(encoding='utf-8'))
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        for key in ('href', 'src'):
            if key in attrs:
                self.links.append(attrs[key])

pages = {path: Page(path) for path in sorted(ROOT.rglob('*.html'))}
failures, checked = [], 0
for path, page in pages.items():
    for href in page.links:
        url = urlsplit(href)
        if url.scheme or url.netloc:
            continue
        checked += 1
        target = (path.parent / unquote(url.path)).resolve() if url.path else path
        if ROOT.resolve() not in target.parents:
            failures.append(f'{path.relative_to(ROOT)}: outside site: {href}')
        elif not target.is_file():
            failures.append(f'{path.relative_to(ROOT)}: missing: {href}')
        elif url.fragment and target.suffix == '.html':
            if unquote(url.fragment) not in pages[target].ids:
                failures.append(f'{path.relative_to(ROOT)}: missing anchor: {href}')
if failures:
    raise SystemExit('\n'.join(failures))
print(json.dumps({'html_pages': len(pages), 'local_links_and_anchors': checked, 'status': 'PASS'}))
