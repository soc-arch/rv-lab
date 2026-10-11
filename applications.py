"""Registration receipts for student programs verified on both backends.

Receipts live with generated runs, not with CPU sources. Rebuilding a run
invalidates its receipt; a new successful comparison is required to publish it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

EVIDENCE = ('build.json', 'result.json', 'sw.json', 'hw.json', 'program.elf',
            'trace.jsonl', 'performance.json', 'program.dis', 'commits.jsonl', 'commits.csv')


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()

def viewer_identity(path):
    """Hash recorded data while permitting gallery navigation/template updates."""
    html = path.read_text()
    opening = '<script id="trace-data" type="application/json">'
    start = html.index(opening) + len(opening)
    payload = html[start:html.index('</script>', start)]
    prefix = '{"metadata":'
    if not payload.startswith(prefix):
        raise ValueError('Unexpected trace data container')
    metadata, end = json.JSONDecoder().raw_decode(payload, len(prefix))
    metadata.pop('navigation', None)
    metadata.pop('image_result', None)
    content = json.dumps(metadata, sort_keys=True, separators=(',', ':')) + payload[end:]
    return metadata.get('elf_sha256'), hashlib.sha256(content.encode()).hexdigest()


def validate_request(args, build):
    if not args.source:
        raise ValueError('Registration requires --source your_main.c (repeat for multiple files)')
    name = getattr(args, 'name', None)
    if not name or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', name):
        raise ValueError('--name must start with a lowercase letter and contain at most 48 lowercase letters, digits, underscores or hyphens')
    sources = [str(Path(p).resolve()) for p in args.source]
    for path in Path(build).glob('*/registration.json'):
        receipt = json.loads(path.read_text())
        if receipt.get('name') == name and receipt.get('sources') != sources:
            raise ValueError(f'Name {name!r} already identifies other sources in {path.parent.name}; choose a different --name')
    for key, limit in (('title', 120), ('description', 600)):
        value = getattr(args, key, None)
        if value is not None and (not value.strip() or len(value) > limit):
            raise ValueError(f'--{key} must contain 1 through {limit} characters')


def publish(args, folder):
    """Bind a human-readable entry to this successful comparison and trace."""
    folder = Path(folder)
    summary = json.loads((folder / 'result.json').read_text())
    hw = json.loads((folder / 'hw.json').read_text())
    if (summary.get('status') != 'pass' or summary.get('signature_match') is not True
            or summary.get('backends') != {'sw': 'pass', 'hw': 'pass'}):
        raise ValueError('Only a successful Spike/RTL comparison can be registered')
    if not (folder / 'trace.html').is_file() or hw.get('metrics', {}).get('trace_cycles', 0) <= 0:
        raise ValueError('No RTL cycles were captured; choose a reached --trace-symbol or use --trace-startup')
    receipt = dict(schema_version=1, name=args.name,
                   title=getattr(args, 'title', None) or args.name,
                   description=getattr(args, 'description', None) or 'Student application verified on Spike and RTL. Explore its recorded CPU activity.',
                   sources=[str(Path(p).resolve()) for p in args.source],
                   elf_sha256=summary['elf_sha256'],
                   viewer_payload_sha256=viewer_identity(folder / 'trace.html')[1],
                   options={key: value for key, value in vars(args).items() if not key.startswith('_')},
                   sha256={name: digest(folder / name) for name in EVIDENCE})
    target = folder / 'registration.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(receipt, indent=2) + '\n')
    temporary.replace(target)
    return receipt


def completed(folder):
    """Return a current receipt; edited, failed or incomplete runs stay unlisted."""
    folder = Path(folder)
    try:
        receipt = json.loads((folder / 'registration.json').read_text())
        if receipt.get('schema_version') != 1 or set(receipt.get('sha256', {})) != set(EVIDENCE):
            return None
        if any(digest(folder / name) != receipt['sha256'][name] for name in EVIDENCE):
            return None
        summary = json.loads((folder / 'result.json').read_text())
        if (summary.get('status') != 'pass' or summary.get('signature_match') is not True
                or summary.get('backends') != {'sw': 'pass', 'hw': 'pass'}
                or summary.get('elf_sha256') != receipt['elf_sha256']):
            return None
        for name in ('sw.json', 'hw.json'):
            result = json.loads((folder / name).read_text())
            if result.get('status') != 'pass' or result.get('elf_sha256') != receipt['elf_sha256']:
                return None
        if digest(folder / 'program.elf') != receipt['elf_sha256']:
            return None
        if not (folder / 'trace.html').is_file():
            return None
        elf, payload_digest = viewer_identity(folder / 'trace.html')
        if elf != receipt['elf_sha256'] or payload_digest != receipt.get('viewer_payload_sha256'):
            return None
        return receipt
    except (OSError, ValueError, KeyError, TypeError):
        return None
