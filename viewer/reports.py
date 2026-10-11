"""Standalone gallery and image-kernel reports for the existing CPU lab.

All measurements are supplied by the runner. This module never simulates the
CPU, computes replacement image results, or claims a timing measurement.
"""

from __future__ import annotations

import base64
import html
import json
import struct
from pathlib import Path
from urllib.parse import urlsplit


HERE = Path(__file__).resolve().parent


def _text(value):
    return html.escape(str(value), quote=True)


def _href(value):
    value = str(value)
    if urlsplit(value).scheme.lower() not in ("", "http", "https", "file"):
        raise ValueError("Report links must be local paths or browser URLs")
    return value


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).replace(
        "<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _count(value):
    return format(int(value), ",")


def normalize_navigation(value):
    """Validate a self-contained example catalog; links resolve from this report.

    Shape: {home_href?, current_id?, groups:[{id,title,examples:[{id,title,href,
    description?}]}]}. No catalog fetch, fixed hostname, or fixed port is needed.
    Example IDs must be unique across groups. Empty groups remain selectable.
    """
    if not value:
        return None
    source = dict(value)
    result = {"groups": []}
    if source.get("home_href"):
        result["home_href"] = _href(source["home_href"])
    if source.get("current_id") is not None:
        result["current_id"] = str(source["current_id"])
    group_ids, example_ids = set(), set()
    for raw_group in source.get("groups", []):
        group = {"id": str(raw_group["id"]), "title": str(raw_group["title"]), "examples": []}
        if group["id"] in group_ids:
            raise ValueError("Navigation group IDs must be unique")
        group_ids.add(group["id"])
        for raw_example in raw_group.get("examples", []):
            example = {"id": str(raw_example["id"]), "title": str(raw_example["title"]),
                       "href": _href(raw_example["href"])}
            if example["id"] in example_ids:
                raise ValueError("Navigation example IDs must be unique")
            example_ids.add(example["id"])
            if raw_example.get("description"):
                example["description"] = str(raw_example["description"])
            group["examples"].append(example)
        result["groups"].append(group)
    return result


def normalize_image_result(value):
    """Validate embedded PNG application buffers without changing any pixels."""
    if not value:
        return None
    result = dict(value)
    images = []
    for original in result.get("images", []):
        image = dict(original)
        url = image.get("data_url", "")
        if not isinstance(url, str) or not url.startswith("data:image/png;base64,"):
            raise ValueError("Application result images must be embedded PNG buffers")
        try:
            raw = base64.b64decode(url.split(",", 1)[1], validate=True)
        except (ValueError, base64.binascii.Error) as error:
            raise ValueError("Invalid application image base64") from error
        if len(raw) < 33 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
            raise ValueError("Invalid application PNG header")
        width, height = struct.unpack(">II", raw[16:24])
        if not width or not height or width > 4096 or height > 4096:
            raise ValueError("Application PNG dimensions must be between 1 and 4096")
        if result.get("width") is not None and int(result["width"]) != width:
            raise ValueError("Application PNG width disagrees with metadata")
        if result.get("height") is not None and int(result["height"]) != height:
            raise ValueError("Application PNG height disagrees with metadata")
        image["title"] = str(image.get("title", "Application image"))
        images.append(image)
    result["images"] = images
    if "verified_bytes" in result:
        result["verified_bytes"] = int(result["verified_bytes"])
        if result["verified_bytes"] < 0:
            raise ValueError("verified_bytes must be nonnegative")
    return result


def generate_gallery(entries, output_path, metadata=None):
    """Generate an offline entry page for the available, already-run examples.

    Each entry requires ``title``, ``description``, and ``href``. Optional keys:
    ``id``, ``group_id`` (``simple`` or ``image``), ``kind`` (``camera`` or ``cycles``), ``cycles``, ``retired``,
    ``trace_cycles``, ``status``, ``checks``, and ``eyebrow``. No timing or PASS
    label is invented for missing fields. Links are relative to the output page.

    Optional metadata: title, description, profile, open_command, preview_href,
    navigation (see normalize_navigation). Without navigation, the catalog is
    built from the supplied entries and their group_id/kind.
    Return value contains the HTML path and example count.
    """
    entries = [dict(entry) for entry in entries]
    meta = dict(metadata or {})
    cards = []
    card_groups = {}
    for index, entry in enumerate(entries, 1):
        for required in ("title", "description", "href"):
            if required not in entry:
                raise ValueError("Gallery entry is missing " + required)
        camera = entry.get("kind") == "camera"
        entry.setdefault("id", "example-" + str(index))
        entry.setdefault("group_id", "image" if camera else "simple")
        status = str(entry.get("status", "")).lower()
        status_class = "pass" if status in ("pass", "passed") else "other"
        status_html = (f'<span class="status {status_class}">{_text(status.upper())}</span>'
                       if status else '')
        stats = []
        for key, label in (("cycles", "full-run cycles"), ("trace_cycles", "captured samples"),
                           ("retired", "retired instructions"), ("checks", "checks")):
            if entry.get(key) is not None:
                stats.append(f'<span><b>{_count(entry[key])}</b> {_text(label)}</span>')
        if camera:
            icon = '<svg viewBox="0 0 280 60" aria-hidden="true"><rect x="9" y="12" width="43" height="36" rx="5"/><path d="M19 36l8-9 6 6 7-12 6 15"/><path class="arrow" d="M65 30h42m-7-5 7 5-7 5"/><rect x="120" y="12" width="43" height="36" rx="5"/><path d="M129 37l8-9 8 5 8-15"/><path class="arrow" d="M176 30h42m-7-5 7 5-7 5"/><rect x="230" y="12" width="43" height="36" rx="5"/><path d="M237 36l9-11 8 8 10-17"/></svg>'
        else:
            icon = '<svg viewBox="0 0 280 60" aria-hidden="true"><rect x="9" y="17" width="52" height="26" rx="5"/><path class="arrow" d="M66 30h23m-7-5 7 5-7 5"/><rect x="96" y="9" width="69" height="42" rx="5"/><path d="M107 23h47m-47 8h32m-32 8h39"/><path class="arrow" d="M171 30h23m-7-5 7 5-7 5"/><rect x="201" y="17" width="69" height="26" rx="5"/><path d="M212 30h15m8 0h22"/></svg>'
        cards.append(f'''<a data-example-id="{_text(entry["id"])}" class="card{' camera' if camera else ''}" href="{_text(_href(entry['href']))}">
          <div class="card-top"><span class="number">{index:02d}</span>{status_html}</div>
          <div class="mini-diagram">{icon}</div>
          <div class="eyebrow">{_text(entry.get('eyebrow', 'Image-kernel experiment' if camera else 'Cycle-by-cycle execution'))}</div>
          <h2>{_text(entry['title'])}</h2><p>{_text(entry['description'])}</p>
          <div class="stats">{''.join(stats)}</div>
          <span class="open">{'Inspect images and cycles' if camera else 'Explore the recorded run'} <span aria-hidden="true">→</span></span>
        </a>''')
        card_groups.setdefault(str(entry['group_id']), []).append(cards[-1])
    if not cards:
        cards.append('''<section class="empty" aria-labelledby="empty-title">
          <div class="eyebrow">Ready for your first run</div>
          <h2 id="empty-title">No completed examples yet</h2>
          <p>Generate the instruction examples with <code>make gallery</code>,
          or run the image-processing experiments with <code>make camera</code>.
          After the command finishes, refresh this browser tab.</p>
          <p>Only available results appear here. A failed or unfinished run is
          not displayed as a completed example.</p>
        </section>''')
    navigation = normalize_navigation(meta.get("navigation"))
    if navigation is None:
        titles = {"simple": "Simple test suite", "image": "Image processing"}
        group_order = [g for g in ("simple", "image") if g in card_groups]
        group_order += [g for g in card_groups if g not in group_order]
        navigation = normalize_navigation({"groups": [
            {"id": group_id, "title": titles.get(group_id, group_id), "examples": [
                {"id": entry["id"], "title": entry["title"], "href": entry["href"],
                 "description": entry["description"]} for entry in entries if entry["group_id"] == group_id]}
            for group_id in group_order]}) or {"groups": []}
    groups_html = []
    for group in navigation["groups"]:
        if group["id"] in card_groups:
            groups_html.append('<section class="gallery-group" data-group-id="' + _text(group["id"]) + '">' +
                              '<h2 class="group-title">' + _text(group["title"]) + '</h2>' +
                              '<div class="grid">' + '\n'.join(card_groups.pop(group["id"])) + '</div></section>')
    for group_id, remaining in card_groups.items():
        groups_html.append('<section class="gallery-group" data-group-id="' + _text(group_id) + '">' +
                          '<h2 class="group-title">' + _text(group_id) + '</h2><div class="grid">' +
                          '\n'.join(remaining) + '</div></section>')
    template = (HERE / "gallery.html").read_text(encoding="utf-8")
    values = {
        "COURSE_LINK": ('<p><a href="' + _text(_href(meta['course_href'])) + '">Start here: step-by-step laboratory exercises</a></p>') if meta.get('course_href') else '',
        "RESULTS_LINK": ('<p><a href="' + _text(_href(meta['results_href'])) + '">Program output &amp; performance results</a></p>') if meta.get('results_href') else '',
        "TITLE": _text(meta.get("title", "From application to hardware")),
        "DESCRIPTION": _text(meta.get("description", "Write a program, check its result, and follow its instructions through the CPU. Each example below opens a real simulation result.")),
        "PROFILE": _text(meta.get("profile", "RV32IM")),
        "COUNT": str(len(entries)),
        "COUNT_LABEL": "guided examples" if entries else "completed examples",
        "CARDS": "\n".join(groups_html) if entries else "\n".join(cards),
        "NAVIGATION_DATA": _json(navigation),
        "OPEN_COMMAND": _text(meta.get("open_command", "python3 lab.py serve")),
        "PREVIEW": ('<a href="' + _text(_href(meta["preview_href"])) + '">View a static preview</a>'
                    if meta.get("preview_href") else ''),
    }
    for key, value in values.items():
        template = template.replace("<!-- " + key + " -->", value)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(template, encoding="utf-8")
    return {"html": str(output_path), "examples": len(entries)}


def generate_camera_report(metadata, frames, output_path):
    """Render actual input/output PNGs and runner-provided measurements.

    ``frames`` is a sequence of mappings with id, title, and data_url containing
    a PNG as ``data:image/png;base64,...``. width/height may be provided and are
    checked against its header. All frames must have the same dimensions so a
    coordinate has the same meaning in input and output. Optional frame fields:
    description, trace_href, full_cycles, roi_cycles (or cycles), pixels_processed, checks,
    format. Per-frame full_cycles selects the corresponding run's total when a
    collection contains multiple independent benchmark runs.

    Metadata may contain application, title, status, backend, cycles, roi_cycles,
    pixels_processed, trace_href, gallery_href, description, and source_note.
    Missing metrics remain absent; derived cycles/pixel uses the supplied cycle
    count and pixels_processed or, explicitly, the PNG's frame pixel count.
    Pixel inspection reads decoded PNG bytes in-browser. No replacement filter
    runs in Python or JavaScript, so displayed results remain the supplied data.
    """
    meta = dict(metadata or {})
    normalized, ids, dimensions = [], set(), None
    for index, original in enumerate(frames):
        frame = dict(original)
        frame.setdefault("id", "frame-" + str(index))
        frame.setdefault("title", str(frame["id"]))
        if frame["id"] in ids:
            raise ValueError("Frame IDs must be unique")
        ids.add(frame["id"])
        url = frame.get("data_url", "")
        if not isinstance(url, str) or not url.startswith("data:image/png;base64,"):
            raise ValueError("Each camera frame needs an embedded PNG data_url")
        try:
            raw = base64.b64decode(url.split(",", 1)[1], validate=True)
        except (ValueError, base64.binascii.Error) as error:
            raise ValueError("Invalid PNG base64 for " + str(frame["id"])) from error
        if len(raw) < 33 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
            raise ValueError("Invalid PNG header for " + str(frame["id"]))
        width, height = struct.unpack(">II", raw[16:24])
        if not width or not height or width > 4096 or height > 4096:
            raise ValueError("Camera report expects nonempty frames of at most 4096 by 4096 pixels")
        if "width" in frame and int(frame["width"]) != width:
            raise ValueError("Frame width disagrees with PNG header")
        if "height" in frame and int(frame["height"]) != height:
            raise ValueError("Frame height disagrees with PNG header")
        if dimensions is not None and dimensions != (width, height):
            raise ValueError("Input and output frames must have matching dimensions")
        dimensions = width, height
        frame["width"], frame["height"] = width, height
        frame["frame_pixels"] = width * height
        if "roi_cycles" not in frame and "cycles" in frame:
            frame["roi_cycles"] = frame["cycles"]
        # Pixels are optional for caller compatibility; PNG is the display and
        # inspection source, so do not embed a redundant second pixel buffer.
        frame.pop("pixels", None)
        if frame.get("trace_href"):
            frame["trace_href"] = _href(frame["trace_href"])
        normalized.append(frame)
    if not normalized:
        raise ValueError("A camera report needs at least one real frame")
    for key in ("trace_href", "gallery_href"):
        if meta.get(key):
            meta[key] = _href(meta[key])
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    template = (HERE / "camera.html").read_text(encoding="utf-8")
    template = template.replace("<!-- CAMERA_DATA -->", _json({"metadata": meta, "frames": normalized}))
    output_path.write_text(template, encoding="utf-8")
    return {"html": str(output_path), "frames": len(normalized),
            "width": dimensions[0], "height": dimensions[1]}
