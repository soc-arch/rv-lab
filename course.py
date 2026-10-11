"""Build the portable student manual from its canonical Markdown sources.

Only the Python standard library is required. Supported Markdown consists of
headings, paragraphs, fenced/indented code, lists, blockquotes, tables, rules,
inline code, emphasis, links, and images. Raw HTML is escaped. Links to files
inside the standalone lab are copied or rendered recursively; missing files,
generated results, and parent-repository references are explicitly labeled.
This module never runs firmware or creates measurement results.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path
import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit


HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "viewer" / "course.html"
_LIST = re.compile(r"^( *)([-+*]|\d+[.)])\s+(.*)$")
_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_INLINE = re.compile(
    r"(`+)(.+?)\1|(!?)\[([^\]\n]*)\]\((<[^>]+>|[^\s)]+)(?:\s+\"[^\"]*\")?\)"
    r"|\*\*(.+?)\*\*|__(.+?)__|\*([^*\n]+)\*|_([^_\n]+)_")


def _escape(value):
    return html.escape(str(value), quote=True)


def _plain(value):
    value = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", value)
    return re.sub(r"[`*_]", "", value)


def _relative(target, page):
    return quote(os.path.relpath(target, page.parent).replace(os.sep, "/"), safe="/-._~")


def _within(path, directory):
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def _table_row(line):
    """Split pipes outside inline code, including escaped literal pipes."""
    line = line.strip().strip("|")
    cells, part, ticks = [], [], False
    index = 0
    while index < len(line):
        char = line[index]
        if char == "\\" and index + 1 < len(line) and line[index + 1] == "|":
            part.append("|")
            index += 2
            continue
        if char == "`":
            ticks = not ticks
        if char == "|" and not ticks:
            cells.append("".join(part).strip())
            part = []
        else:
            part.append(char)
        index += 1
    cells.append("".join(part).strip())
    return cells


def _table_separator(line):
    return all(re.fullmatch(r":?-{3,}:?", cell) for cell in _table_row(line))


class Markdown:
    """A deliberately small renderer for the documented course source subset."""

    def __init__(self, resolve_link):
        self.resolve_link = resolve_link
        self.headings = []
        self.ids = {}

    def inline(self, value):
        output, offset = [], 0
        for match in _INLINE.finditer(value):
            output.append(_escape(value[offset:match.start()]))
            if match.group(1):
                output.append("<code>" + _escape(match.group(2)) + "</code>")
            elif match.group(3) is not None:
                image = bool(match.group(3))
                label, target = match.group(4), match.group(5).strip("<>")
                href, reason = self.resolve_link(target, image)
                if href is None:
                    output.append('<span class="unavailable" title="' + _escape(reason) + '">' +
                                  self.inline(label) + ' <small>(not in this portable copy)</small></span>')
                elif image and urlsplit(href).scheme not in ("http", "https"):
                    output.append('<img src="' + _escape(href) + '" alt="' + _escape(_plain(label)) +
                                  '" loading="lazy">')
                else:
                    output.append('<a href="' + _escape(href) + '">' + self.inline(label) + '</a>')
            else:
                strong = match.group(6) or match.group(7)
                tag, inner = ("strong", strong) if strong is not None else ("em", match.group(8) or match.group(9))
                output.append("<" + tag + ">" + self.inline(inner) + "</" + tag + ">")
            offset = match.end()
        output.append(_escape(value[offset:]))
        return "".join(output)

    def render(self, source):
        return self._blocks(source.expandtabs(4).splitlines())

    def _blocks(self, lines):
        output, i = [], 0
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            fence = _FENCE.match(line)
            heading = _HEADING.match(line)
            listing = _LIST.match(line)
            if fence:
                mark, language = fence.group(1), fence.group(2).strip()
                content = []
                i += 1
                close = re.compile(r"^ {0,3}" + re.escape(mark[0]) + "{" + str(len(mark)) + r",}\s*$")
                while i < len(lines) and not close.match(lines[i]):
                    content.append(lines[i])
                    i += 1
                i += 1
                label = language.split()[0] if language else "text"
                output.append('<div class="code-block"><div class="code-toolbar"><span>' +
                              _escape(label) + '</span><button type="button" class="copy-code">Copy</button></div>' +
                              '<pre><code>' + _escape("\n".join(content)) + '</code></pre></div>')
            elif heading:
                level, text = len(heading.group(1)), heading.group(2)
                slug = re.sub(r"[^\w -]", "", _plain(text).lower()).strip().replace(" ", "-") or "section"
                slug = re.sub(r"-+", "-", slug)
                count = self.ids.get(slug, 0)
                self.ids[slug] = count + 1
                identifier = slug + ("-" + str(count) if count else "")
                self.headings.append((level, _plain(text), identifier))
                output.append(f'<h{level} id="{_escape(identifier)}">{self.inline(text)}</h{level}>')
                i += 1
            elif re.fullmatch(r" {0,3}(?:\*\s*){3,}| {0,3}(?:-\s*){3,}| {0,3}(?:_\s*){3,}", line):
                output.append("<hr>")
                i += 1
            elif i + 1 < len(lines) and "|" in line and _table_separator(lines[i + 1]):
                headers = _table_row(line)
                i += 2
                rows = []
                while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                    cells = _table_row(lines[i])
                    cells += [""] * (len(headers) - len(cells))
                    rows.append("<tr>" + "".join("<td>" + self.inline(cell) + "</td>" for cell in cells[:len(headers)]) + "</tr>")
                    i += 1
                output.append('<div class="table-scroll"><table><thead><tr>' +
                              "".join('<th scope="col">' + self.inline(cell) + '</th>' for cell in headers) +
                              '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')
            elif listing:
                base = len(listing.group(1))
                ordered = listing.group(2)[0].isdigit()
                tag = "ol" if ordered else "ul"
                start = int(re.match(r"\d+", listing.group(2)).group()) if ordered else 1
                items = []
                while i < len(lines):
                    item = _LIST.match(lines[i])
                    if not item or len(item.group(1)) != base or item.group(2)[0].isdigit() != ordered:
                        break
                    indent = item.start(3)
                    content = [item.group(3)]
                    i += 1
                    while i < len(lines):
                        candidate = lines[i]
                        nxt = _LIST.match(candidate)
                        if nxt and len(nxt.group(1)) == base:
                            break
                        if candidate.strip() and len(candidate) - len(candidate.lstrip()) <= base:
                            break
                        content.append(candidate[min(indent, len(candidate) - len(candidate.lstrip())):])
                        i += 1
                    items.append("<li>" + self._blocks(content) + "</li>")
                output.append("<" + tag + (f' start="{start}"' if ordered and start != 1 else "") + ">" + "".join(items) + "</" + tag + ">")
            elif line.lstrip().startswith(">"):
                content = []
                while i < len(lines) and lines[i].lstrip().startswith(">"):
                    content.append(re.sub(r"^\s*> ?", "", lines[i]))
                    i += 1
                output.append("<blockquote>" + self._blocks(content) + "</blockquote>")
            elif line.startswith("    "):
                content = []
                while i < len(lines) and (lines[i].startswith("    ") or not lines[i].strip()):
                    content.append(lines[i][4:])
                    i += 1
                output.append("<pre><code>" + _escape("\n".join(content).rstrip()) + "</code></pre>")
            else:
                content = [line.strip()]
                i += 1
                while i < len(lines) and lines[i].strip():
                    candidate = lines[i]
                    list_start = _LIST.match(candidate)
                    interrupts = list_start and (not list_start.group(2)[0].isdigit() or
                                                 re.match(r"\d+", list_start.group(2)).group() == "1")
                    if (_HEADING.match(candidate) or _FENCE.match(candidate) or interrupts or
                            candidate.lstrip().startswith(">") or
                            (i + 1 < len(lines) and "|" in candidate and _table_separator(lines[i + 1]))):
                        break
                    content.append(candidate.strip())
                    i += 1
                output.append("<p>" + self.inline(" ".join(content)) + "</p>")
        return "\n".join(output)


def generate(root, build):
    """Return {html, pages, files, unavailable_references}; write <build>/course.

    Files are portable under both HTTP and file://. Only generated files listed
    in the previous manifest may be removed when a source/link disappears.
    """
    root, build = Path(root).resolve(), Path(build).resolve()
    source_dir, output = root / "docs" / "course", build / "course"
    sources = sorted(source_dir.glob("*.md"), key=lambda path: (path.name != "index.md", path.name))
    if not sources or sources[0].name != "index.md":
        raise ValueError("The course requires docs/course/index.md")
    template = TEMPLATE.read_text()
    output.mkdir(parents=True, exist_ok=True)
    manifest_file = output / "manifest.json"
    try:
        previous = json.loads(manifest_file.read_text()).get("files", {})
    except (OSError, ValueError):
        previous = {}
    pages = {path.resolve(): output / path.with_suffix(".html").name for path in sources}
    pending, written, source_hashes, warnings = list(pages), {}, {}, set()

    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_bytes() != data:
            path.write_bytes(data)
        written[path.relative_to(output).as_posix()] = hashlib.sha256(data).hexdigest()

    def remember(source):
        data = source.read_bytes()
        source_hashes[source.relative_to(root).as_posix()] = hashlib.sha256(data).hexdigest()
        return data

    def title(path):
        first = next((line for line in path.read_text().splitlines() if line.startswith("# ")), path.stem)
        return _plain(first[2:] if first.startswith("# ") else first)

    titles = {path: title(path) for path in sources}

    def resolve(source, page, target, image):
        parsed = urlsplit(target)
        if parsed.scheme in ("http", "https") and parsed.hostname in ("127.0.0.1", "localhost"):
            destination = (build / (unquote(parsed.path).lstrip("/") or "index.html")).resolve()
            if _within(destination, build) and (destination.is_file() or destination in pages.values()):
                return urlunsplit(("", "", _relative(destination, page), parsed.query, parsed.fragment)), None
            return None, "Run the corresponding experiment to generate this result in the selected build directory"
        if parsed.scheme.lower() in ("http", "https", "mailto"):
            return target, None
        if parsed.scheme or parsed.netloc:
            warnings.add((source.relative_to(root).as_posix(), target, "Unsupported link scheme"))
            return None, "Unsupported link scheme"
        if not parsed.path:
            return target, None
        local = (source.parent / unquote(parsed.path)).resolve()
        if local.is_dir():
            local /= "README.md"
        reason = None
        if not _within(local, root):
            reason = "Parent-repository reference: " + target
        elif _within(local, build) or _within(local, root / "build") or ".git" in local.relative_to(root).parts:
            reason = "Generated results are available from the run gallery, when present"
        elif not local.is_file():
            reason = "Source file is not present: " + target
        if reason:
            warnings.add((source.relative_to(root).as_posix(), target, reason))
            return None, reason
        if local.suffix.lower() == ".md" and not image:
            if local not in pages:
                pages[local] = output / "references" / local.relative_to(root).with_suffix(".html")
                pending.append(local)
            destination = pages[local]
        else:
            destination = output / "files" / local.relative_to(root)
            write(destination, remember(local))
        href = _relative(destination, page)
        return urlunsplit(("", "", href, parsed.query, parsed.fragment)), None

    for source in pending:
        page = pages[source]
        renderer = Markdown(lambda target, image: resolve(source, page, target, image))
        content = renderer.render(remember(source).decode("utf-8"))
        page_title = next((name for level, name, _ in renderer.headings if level == 1), source.stem)
        navigation = []
        for path in sources:
            current = ' aria-current="page"' if path == source else ""
            navigation.append('<a href="' + _escape(_relative(pages[path], page)) + '"' + current + '>' + _escape(titles[path]) + '</a>')
        sections = ''.join('<a class="level-' + str(level) + '" href="#' + _escape(identifier) + '">' + _escape(name) + '</a>'
                           for level, name, identifier in renderer.headings if level in (2, 3))
        pager = []
        if source in sources:
            position = sources.index(source)
            for label, index in (("Previous", position - 1), ("Next", position + 1)):
                if 0 <= index < len(sources):
                    other = sources[index]
                    pager.append('<a href="' + _escape(_relative(pages[other], page)) + '"><small>' + label + '</small>' + _escape(titles[other]) + '</a>')
        else:
            pager.append('<a href="' + _escape(_relative(output / "index.html", page)) + '">Return to course overview</a>')
        tools_links = []
        for filename, label in (("index.html", "Run gallery"), ("results.html", "Application results")):
            if (build / filename).is_file():
                tools_links.append('<a href="' + _escape(_relative(build / filename, page)) + '">' + label + '</a>')
        replacements = {
            "TITLE": _escape(page_title), "CONTENT": content,
            "HOME": _escape(_relative(output / "index.html", page)),
            "NAVIGATION": '\n'.join(navigation), "SECTIONS": sections,
            "PAGER": ''.join(pager), "TOOLS": ''.join(tools_links),
            "SOURCE": _escape(source.relative_to(root).as_posix()),
        }
        rendered = re.sub(r"\{\{([A-Z]+)\}\}", lambda match: replacements[match.group(1)], template)
        write(page, rendered.encode("utf-8"))

    for name in previous.keys() - written.keys():
        obsolete = (output / name).resolve()
        if _within(obsolete, output) and obsolete.is_file():
            obsolete.unlink()
    warning_list = [{"source": source, "target": target, "reason": reason} for source, target, reason in sorted(warnings)]
    manifest = {"version": 1, "pages": len(pages), "lessons": len(sources) - 1,
                "files": written, "sources": source_hashes, "unavailable_references": warning_list}
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")
    return {"html": str(output / "index.html"), "pages": len(pages), "files": len(written),
            "unavailable_references": warning_list}
