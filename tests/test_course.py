"""Portable course publishing checks; no compiler or simulator is needed."""

from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import course


class Links(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.links, self.ids, self.images = [], set(), []
        self.feed(source)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])
        if tag == "img" and "src" in attrs:
            self.images.append(attrs["src"])


class CourseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hy-rv-course-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "lab"
        self.build = self.root / "build" / "test"
        self.source = self.root / "docs" / "course"
        self.source.mkdir(parents=True)

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def assert_local_links(self):
        for page in (self.build / "course").rglob("*.html"):
            parsed = Links(page.read_text())
            for href in parsed.links + parsed.images:
                url = urlsplit(href)
                if url.scheme:
                    continue
                target = (page.parent / unquote(url.path)).resolve() if url.path else page
                self.assertTrue(target.is_file(), f"{page}: {href}")
                if url.fragment and target.suffix == ".html":
                    self.assertIn(unquote(url.fragment), Links(target.read_text()).ids,
                                  f"{page}: missing anchor {href}")

    def test_offline_lessons_references_downloads_and_optional_results(self):
        self.write(self.source / "index.md", """# Course overview

[Start](01-main.md#1-write-main) and [runtime notes](../runtime.md).
[Results](http://127.0.0.1:8771/results.html)
""")
        self.write(self.source / "01-main.md", """# Lab 1: Main

## 1. Write `main`

Download [the starter](starter/my%20main.c), then run:

```sh
make compare SOURCE='my main.c'
```

1. Build the file.
2. Check the results.
   - Save the report.
   - Read the cycles.

| Output | Meaning |
| --- | --- |
| `a | b` | **Bitwise OR** |

[Missing](../missing.md) [research](../../../research.md)
""")
        self.write(self.source / "starter" / "my main.c", "int main(void) { return 0; }\n")
        self.write(self.root / "docs" / "runtime.md", "# Runtime\n\n[Return](course/index.md).\n")
        summary = course.generate(self.root, self.build)
        self.assertEqual(summary["pages"], 3)
        self.assertEqual(len(summary["unavailable_references"]), 2)
        page = (self.build / "course" / "01-main.html").read_text()
        self.assertIn('<td><code>a | b</code></td>', page)
        self.assertIn('<strong>Bitwise OR</strong>', page)
        self.assertIn('id="1-write-main"', page)
        self.assertIn('not in this portable copy', page)
        self.assertNotIn('>Run gallery</a>', page)
        self.assertIn('Previous</small>Course overview', page)
        self.assert_local_links()
        self.assertEqual((self.build / "course" / "files" / "docs" / "course" / "starter" / "my main.c").read_text(),
                         "int main(void) { return 0; }\n")
        self.write(self.build / "index.html", "<h1>Gallery</h1>")
        self.write(self.build / "results.html", "<h1>Results</h1>")
        course.generate(self.root, self.build)
        page = (self.build / "course" / "01-main.html").read_text()
        self.assertIn('href="../index.html">Run gallery</a>', page)
        self.assertIn('href="../results.html">Application results</a>', page)
        self.assertIn('href="../results.html">Results</a>', (self.build / "course" / "index.html").read_text())
        self.assert_local_links()

    def test_numbered_sentence_continuation_is_not_a_new_list(self):
        renderer = course.Markdown(lambda target, image: (target, None))
        rendered = renderer.render("The answer is\n36. In the browser, inspect it.\n\n1. Start a list.\n")
        self.assertIn("<p>The answer is 36. In the browser, inspect it.</p>", rendered)
        self.assertNotIn('start="36"', rendered)
        self.assertIn("<ol>", rendered)

    def test_html_and_unsafe_links_are_not_executed_or_embedded(self):
        self.write(self.source / "index.md", """# Safe <script>alert(1)</script>

<img src=x onerror=alert(1)>

[blocked](javascript:alert) ![external image](https://example.com/image.png)

```html
<script>alert('literal')</script>
```

## Repeat

## Repeat
""")
        result = course.generate(self.root, self.build)
        page = Path(result["html"]).read_text()
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', page)
        self.assertNotIn('<img src=x', page)
        self.assertNotIn('href="javascript:', page)
        self.assertEqual(Links(page).images, [])
        self.assertIn('id="repeat-1"', page)
        self.assert_local_links()

    def test_stale_generated_files_removed_without_touching_unowned_files(self):
        self.write(self.source / "index.md", "# Overview\n\n[Download](data.txt)\n")
        self.write(self.source / "data.txt", "download contents\n")
        course.generate(self.root, self.build)
        out = self.build / "course"
        generated = out / "files" / "docs" / "course" / "data.txt"
        self.assertTrue(generated.is_file())
        self.write(out / "personal-notes.txt", "keep this\n")
        self.write(self.source / "index.md", "# Overview\n")
        course.generate(self.root, self.build)
        self.assertFalse(generated.exists())
        self.assertTrue((out / "personal-notes.txt").is_file())
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(manifest["pages"], 1)
        self.assertIn("docs/course/index.md", manifest["sources"])
        self.assertNotIn("personal-notes.txt", manifest["files"])


if __name__ == "__main__":
    unittest.main()
