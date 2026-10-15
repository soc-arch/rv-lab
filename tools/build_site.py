#!/usr/bin/env python3
# =============================================================================
# HY-RV | build_site
# Description: Build the portable eight-lab GitHub Pages manual.
# Purpose: Computer architecture and RTL design education and lab exercises.
# Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
# Website: https://dsa.hanyang.ac.kr
# Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
# AI tools such as Codex or Claude may have assisted in creating or modifying
# this file. See applicable manifests and verification records for provenance.
# Preserve existing license, copyright, and original author notices.
# =============================================================================

"""Render the eight lesson sources into the committed GitHub Pages directory."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import course

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true', help='Fail if committed lesson HTML is stale')
args = parser.parse_args()
destination = ROOT / 'docs'
manifest_path = destination / 'site-manifest.json'
with tempfile.TemporaryDirectory(prefix='rv-lab-site-') as temp:
    output = Path(temp)
    summary = course.generate(ROOT, output)
    if summary['unavailable_references']:
        raise SystemExit('Unresolved course source links: ' + json.dumps(summary['unavailable_references']))
    manifest = json.loads((output / 'course/manifest.json').read_text())
    expected = {'course/' + name: (output / 'course' / name).read_bytes() for name in manifest['files']}
    expected['site-manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'files': {}}
    obsolete = {'course/' + name for name in previous['files']} - set(expected)
    differences = sorted(name for name, data in expected.items()
                         if not (destination / name).is_file() or (destination / name).read_bytes() != data)
    differences += sorted(name for name in obsolete if (destination / name).exists())
    if args.check:
        if differences:
            raise SystemExit('Stale lesson HTML; run make site: ' + ', '.join(differences))
    else:
        for name in obsolete:
            path = (destination / name).resolve()
            if destination.resolve() not in path.parents or path.suffix == '.md':
                raise SystemExit('Invalid generated-file cleanup path: ' + name)
            if path.is_file():
                path.unlink()
        for name, data in expected.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print(json.dumps({'lessons': manifest['lessons'], 'html_pages': manifest['pages'],
                      'generated_files': len(manifest['files']), 'check': args.check, 'status': 'PASS'}))
