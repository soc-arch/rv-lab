# =============================================================================
# HY-RV | catalog
# Description: Preserve actual CPU identity while refreshing portable cycle-report menus.
# Purpose: Computer architecture and RTL design education and lab exercises.
# Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
# Website: https://dsa.hanyang.ac.kr
# Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
# AI tools such as Codex or Claude may have assisted in creating or modifying
# this file. See applicable manifests and verification records for provenance.
# Preserve existing license, copyright, and original author notices.
# =============================================================================
"""Discover completed cycle reports and embed a portable, relative example menu."""
from __future__ import annotations
import base64
import json
import os
import hashlib
import zipfile
from pathlib import Path
from .reports import generate_gallery, normalize_navigation, normalize_image_result

HERE = Path(__file__).resolve().parent
LESSONS = {
    '01_arithmetic': ('simple', 'Arithmetic', 'Register reads, integer ALU operations and writeback.'),
    '02_memory': ('simple', 'Memory access', 'Byte lanes, load extension and request/response handshakes.'),
    '03_control': ('simple', 'Control flow', 'Branches, calls, redirects and discarded fetch responses.'),
    '04_muldiv': ('simple', 'Multiply and divide', 'A frontend word waits beside a multicycle execution unit.'),
    '05_functions': ('simple', 'Functions and stack', 'Follow C calls, stack accesses and their machine instructions.'),
    '10_performance': ('simple', 'Application performance', 'Read CSR counters and compare measured ROI cycles with the complete retirement history.'),
    '06_camera-copy': ('image', 'RGB copy', 'Read and write every pixel through the data port.'),
    '06_camera-grayscale': ('image', 'Grayscale conversion', 'Integer RGB weighting, pixel loads and output stores.'),
    '06_camera-sobel': ('image', 'Sobel edges', 'Signed gradients and saturation; grayscale preparation is outside the measured region.'),
    '06_camera-pipeline': ('image', 'Grayscale → Sobel', 'Measure and inspect the complete RGB-to-edge pipeline.'),
    '07_denoise': ('image', 'Impulse-noise removal', 'Convert noisy RGB to grayscale, then remove salt-and-pepper noise with a 3×3 median filter.'),
    '08_cartoon': ('image', 'Cartoon rendering', 'RGB median filtering, color quantization and edge composition.'),
    '09_ball': ('image', 'Integer bouncing ball', 'Render one selected animation frame with integer geometry, lighting and shadows.'),
}

def navigation(entries, page, build, current_id=None):
    groups = [{'id': key, 'title': title, 'examples': []} for key, title in
              [('simple', 'Simple test suite'), ('image', 'Image processing')]]
    if any(entry['group_id'] == 'custom' for entry in entries):
        groups.append({'id': 'custom', 'title': 'My applications', 'examples': []})
    for entry in entries:
        group = next(g for g in groups if g['id'] == entry['group_id'])
        group['examples'].append({k: entry[k] for k in ('id', 'title', 'description')})
        group['examples'][-1]['href'] = Path(os.path.relpath(build / entry['href'], page.parent)).as_posix()
    return {'home_href': Path(os.path.relpath(build / 'index.html', page.parent)).as_posix(),
            'current_id': current_id, 'groups': groups}

def image_result(folder, manifest, record):
    config = manifest.get('visual') or manifest.get('camera')
    check = record.get('image_check')
    if not config or not check or not check.get('passed'): return None
    frames = []
    files = [('input.png', 'Input RGB'), ('hw.output.png', 'Actual RTL output')]
    if config['mode'] == 'denoise':
        files = [('clean.png', 'Before noise'), ('input.png', 'Noisy input'), ('hw.output.png', 'Actual RTL output')]
    if config['mode'] == 'ball': files = [('hw.output.png', f"Actual RTL output · frame {config['frame']}")]
    for filename, title in files:
        path = folder / filename
        if path.is_file(): frames.append({'title': title, 'data_url': 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode()})
    return {'title': 'Pixels computed by this RISC-V program',
            'description': 'Images come from the complete SRAM output dump. The timeline is a bounded capture from that same RTL run; ROI timing covers the complete measured kernel.',
            'width': config['width'], 'height': config['height'],
            'verified_bytes': check['bytes_compared'], 'oracle': check.get('oracle', 'Independent Python image reference'),
            'images': frames}

def refresh_saved(page, nav, image=None):
    """Replace presentation/metadata while preserving the actual trace verbatim."""
    html = page.read_text()
    opening = '<script id="trace-data" type="application/json">'
    start = html.index(opening) + len(opening)
    payload = html[start:html.index('</script>', start)]
    prefix = '{"metadata":'
    if not payload.startswith(prefix): raise ValueError(f'Unexpected trace container in {page}')
    meta, end = json.JSONDecoder().raw_decode(payload, len(prefix))
    meta['navigation'] = normalize_navigation(nav)
    if image: meta['image_result'] = normalize_image_result(image)
    else: meta.pop('image_result', None)
    encoded = json.dumps(meta, ensure_ascii=True, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    payload = prefix + encoded + payload[end:]
    from .render import _diagram
    diagram = _diagram(meta)
    output = (HERE / 'template.html').read_text().replace('<!-- MICROARCHITECTURE -->', diagram).replace('<!-- TRACE_DATA -->', payload)
    if output != html: page.write_text(output)
    page.with_name('microarchitecture.svg').write_text(diagram)

def refresh(build):
    build = Path(build)
    entries, reports = [], []
    for application, (group, title, description) in LESSONS.items():
        for folder in sorted(build.glob(application + '-O*')):
            page = folder / 'trace.html'
            if not page.is_file() or not (folder / 'hw.json').is_file() or not (folder / 'build.json').is_file(): continue
            record = json.loads((folder / 'hw.json').read_text())
            manifest = json.loads((folder / 'build.json').read_text())
            if record.get('status') != 'pass' or record.get('elf_sha256') != manifest.get('elf_sha256'): continue
            suffix = folder.name[len(application)+1:]
            display = title if suffix == 'O2' else title + ' · ' + suffix
            entry = dict(record.get('metrics', {}))
            entry.update(id=folder.name, group_id=group, title=display, description=description,
                         href=page.relative_to(build).as_posix(), status='pass', kind='camera' if group == 'image' else 'cycles')
            entries.append(entry)
            reports.append((page, entry, image_result(folder, manifest, record)))
    from applications import completed
    for receipt_path in sorted(build.glob('*/registration.json')):
        folder = receipt_path.parent
        receipt = completed(folder)
        if not receipt: continue
        manifest = json.loads((folder / 'build.json').read_text())
        record = json.loads((folder / 'hw.json').read_text())
        suffix = folder.name[len(manifest['application']) + 1:]
        title = receipt['title'] if suffix == 'O2' else receipt['title'] + ' · ' + suffix
        entry = dict(record.get('metrics', {}))
        entry.update(id=folder.name, group_id='custom', title=title,
                     description=receipt['description'], name=receipt['name'],
                     href=(folder / 'trace.html').relative_to(build).as_posix(),
                     status='pass', kind='cycles')
        entries.append(entry)
        reports.append((folder / 'trace.html', entry, None))
    build.mkdir(parents=True, exist_ok=True)
    active = {entry['id'] for entry in entries}
    # Camera-suite aliases belong to its aggregate report, not to independent
    # old mode runs left behind when a later suite fails or is rebuilt.
    camera_aliases_ok = False
    camera_sources = {}
    camera_report_path = build / 'camera/report.json'
    if camera_report_path.is_file():
        camera_report = json.loads(camera_report_path.read_text())
        camera_aliases_ok = camera_report.get('status') == 'pass'
        for mode, data in camera_report.get('modes', {}).items():
            for folder in sorted(build.glob('06_camera-' + mode + '-O*')):
                record_path = folder / 'hw.json'
                if not record_path.is_file(): continue
                current = json.loads(record_path.read_text())
                if (current.get('status') == 'pass' and current.get('elf_sha256') == data.get('build', {}).get('elf_sha256')
                        and current.get('metrics') == data.get('hw', {}).get('metrics')):
                    camera_sources[mode] = folder.name
                    break
            if mode not in camera_sources: camera_aliases_ok = False
    if not camera_aliases_ok:
        for mode in ('copy', 'grayscale', 'sobel', 'pipeline'):
            (build / 'camera' / (mode + '-trace.html')).unlink(missing_ok=True)
        (build / 'camera/trace.html').unlink(missing_ok=True)
        (build / 'camera/report.html').unlink(missing_ok=True)
    for app, (group, _, _) in LESSONS.items():
        if app + '-O2' in active: continue
        aliases = []
        if group == 'simple':
            aliases.append(build / 'showcase' / app / 'trace.html')
            if app == '04_muldiv': aliases.append(build / 'muldiv/trace.html')
        for alias in aliases: alias.unlink(missing_ok=True)
    for page, entry, image in reports:
        refresh_saved(page, navigation(entries, page, build, entry['id']), image)
        # Preserve previously shared offline paths, with links relative to each alias.
        aliases = []
        app = entry['id'][:-3] if entry['id'].endswith('-O2') else entry['id']
        for mode, source in camera_sources.items():
            if camera_aliases_ok and source == entry['id']:
                aliases.append(build / 'camera' / (mode + '-trace.html'))
                if mode == 'sobel': aliases.append(build / 'camera/trace.html')
        if app in LESSONS and entry['id'].endswith('-O2'):
            if entry['group_id'] == 'simple':
                aliases.append(build / 'showcase' / app / 'trace.html')
                if app == '04_muldiv': aliases.append(build / 'muldiv/trace.html')
        for alias in aliases:
            alias.parent.mkdir(parents=True, exist_ok=True)
            alias.write_text(page.read_text())
            refresh_saved(alias, navigation(entries, alias, build, entry['id']), image)
    for target in (build / 'index.html', build / 'showcase/index.html'):
        adapted = [dict(e, href=Path(os.path.relpath(build / e['href'], target.parent)).as_posix()) for e in entries]
        generate_gallery(adapted, target, {'title': 'CPU laboratory · Guided examples',
                         'course_href': Path(os.path.relpath(build / 'course/index.html', target.parent)).as_posix(),
                         'results_href': Path(os.path.relpath(build / 'results.html', target.parent)).as_posix() if (build / 'results.html').is_file() else None,
                         'navigation': navigation(entries, target, build)})
    (build / 'catalog.json').write_text(json.dumps({'examples': entries}, indent=2) + '\n')
    from course import generate
    generate(HERE.parent, build)
    return build / 'index.html'

def export_reports(build):
    """Package the grouped catalog and self-contained traces for offline use."""
    build = Path(build)
    refresh(build)
    catalog = json.loads((build / 'catalog.json').read_text())
    files = {build / 'index.html', build / 'catalog.json', build / 'showcase/index.html'}
    files.update(path for path in (build / 'course').rglob('*') if path.is_file())
    # The image exercise links to the aggregate pixel report and its mode traces.
    if (build / 'camera/report.html').is_file():
        files.update((build / 'camera').glob('*.html'))
        if (build / 'camera/microarchitecture.svg').is_file():
            files.add(build / 'camera/microarchitecture.svg')
    for entry in catalog['examples']:
        page = build / entry['href']
        files.update((page, page.with_name('microarchitecture.svg')))
    # Result pages also serve student-supplied main(), which need not be lessons.
    if (build / 'results.html').is_file(): files.add(build / 'results.html')
    for report in build.glob('*/report.html'):
        if not report.with_name('performance.json').is_file(): continue
        for name in ('report.html', 'performance.json', 'program.dis', 'commits.jsonl', 'commits.csv', 'trace.html', 'microarchitecture.svg',
                     'registration.json', 'build.json', 'result.json', 'sw.json', 'hw.json', 'program.elf', 'trace.jsonl'):
            path = report.with_name(name)
            if path.is_file(): files.add(path)
    manifest = {}
    destination = build / 'cpu_lab_examples.zip'
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            relative = path.relative_to(build).as_posix()
            content = path.read_bytes()
            archive.writestr(relative, content)
            manifest[relative] = hashlib.sha256(content).hexdigest()
        archive.writestr('manifest.json', json.dumps({'examples': len(catalog['examples']), 'sha256': manifest}, indent=2) + '\n')
        archive.writestr('README.txt', 'Extract the entire ZIP, then open index.html in a web browser.\n'
            'Open course/index.html for the step-by-step exercises.\n'
            'Choose Simple test suite, Image processing, or My applications, then an example.\n'
            'Each trace embeds its recorded RTL cycles, assembly, diagram and image outputs.\n'
            'Keep the folder layout for navigation. No server, CDN or installation is needed.\n'
            'Large kernels have a bounded trace window; full-run and ROI counts describe the complete run.\n')
    return destination
