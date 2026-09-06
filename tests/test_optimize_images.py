import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

SPEC = importlib.util.spec_from_file_location("optimizer", Path(__file__).resolve().parents[1] / "scripts/optimize_images.py")
optimizer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(optimizer)


class OptimizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "assets/img/trip").mkdir(parents=True)
        (self.root / "_posts").mkdir()
        (self.root / "_config.yml").write_text('exclude: ["node_modules"]\n')
        self.photo = self.root / "assets/img/trip/My photo.JPEG"
        original = Image.new("RGB", (2400, 1800), "blue")
        exif = Image.Exif()
        exif[274] = 6
        original.save(self.photo, exif=exif)
        self.post = self.root / "_posts/2026-01-01-trip.md"
        self.post.write_text('---\nimg: trip/My photo.JPEG\n---\n'
                             '![A & B]({{site.baseurl}}/assets/img/trip/My photo.JPEG){:width="50%"}\n'
                             '*A caption*\n')

    def test_migration_orientation_idempotence_and_update(self):
        original_bytes = self.photo.read_bytes()
        optimizer.run(self.root)
        manifest = json.loads((self.root / "_data/images.json").read_text())
        photo = manifest["trip/My photo.JPEG"]
        self.assertEqual((photo["article"]["width"], photo["article"]["height"]), (1200, 1600))
        self.assertEqual(photo["thumbnail"]["width"], 800)
        self.assertIn("My%20photo.JPEG.article.jpg", photo["article"]["path"])
        self.assertEqual(original_bytes, self.photo.read_bytes())
        self.assertIn('src="trip/My photo.JPEG" alt="A &amp; B" width="50%" loading="eager"', self.post.read_text())
        self.assertIn('*A caption*', self.post.read_text())
        snapshot = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        optimizer.run(self.root)
        self.assertEqual(snapshot, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in snapshot})
        Image.new("RGB", (600, 400), "red").save(self.photo)
        optimizer.run(self.root)
        refreshed = json.loads((self.root / "_data/images.json").read_text())["trip/My photo.JPEG"]
        self.assertEqual(refreshed["article"]["width"], 600)
        self.assertNotEqual(photo["sha256"], refreshed["sha256"])

    def test_dry_run_and_missing_source_do_not_write(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        optimizer.run(self.root, dry_run=True)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.post.write_text('![missing](/assets/img/trip/missing.jpg)')
        with self.assertRaisesRegex(ValueError, "missing or unsupported"):
            optimizer.run(self.root)
        self.assertFalse((self.root / "assets/optimized").exists())

    def test_transparency_collision_and_skipped_examples(self):
        Image.new("RGBA", (20, 30), (255, 0, 0, 100)).save(self.root / "assets/img/trip/same.png")
        Image.new("RGB", (30, 20), "red").save(self.root / "assets/img/trip/same.jpg")
        untouched = '\n<!-- ![ignored](/assets/img/missing.jpg) -->\n```markdown\n![example](/assets/img/example.jpg)\n```\n'
        self.post.write_text(self.post.read_text() + untouched)
        optimizer.run(self.root)
        self.assertIn(untouched, self.post.read_text())
        data = json.loads((self.root / "_data/images.json").read_text())
        self.assertNotEqual(data["trip/same.png"]["article"]["path"], data["trip/same.jpg"]["article"]["path"])
        self.assertTrue(data["trip/same.png"]["article"]["path"].endswith(".png"))
        with Image.open(self.root / data["trip/same.png"]["article"]["path"].lstrip("/")) as image:
            self.assertEqual(image.getpixel((0, 0))[3], 100)

    def test_unsupported_markup_is_reported(self):
        self.post.write_text('<img src="/assets/img/trip/My photo.JPEG">')
        with self.assertRaisesRegex(ValueError, "unsupported original image markup"):
            optimizer.run(self.root)

    def test_broken_multiline_url_is_reported(self):
        self.post.write_text('![broken](/assets/img/trip/My photo\n.JPEG){:width="50%"}')
        with self.assertRaisesRegex(ValueError, "missing or unsupported"):
            optimizer.run(self.root)

    def test_opaque_png_new_markdown_and_unpublished_draft(self):
        Image.new("RGBA", (40, 30), (0, 255, 0, 255)).save(self.root / "assets/img/trip/opaque.png")
        (self.root / "_posts/draft.md").write_text('---\npublished: false\nimg: missing.jpg\n---\n')
        optimizer.run(self.root)
        self.post.write_text(self.post.read_text() + '\n![new](/assets/img/trip/opaque.png){:width="28%"}\n')
        optimizer.run(self.root)
        self.assertIn('src="trip/opaque.png" alt="new" width="28%"', self.post.read_text())
        data = json.loads((self.root / "_data/images.json").read_text())
        self.assertTrue(data["trip/opaque.png"]["article"]["path"].endswith(".jpg"))

    def test_animated_png_remains_published_and_unconverted(self):
        path = self.root / "assets/img/trip/animation.png"
        Image.new("RGBA", (20, 20), "red").save(path, save_all=True,
            append_images=[Image.new("RGBA", (20, 20), "blue")], duration=100, loop=0)
        markup = '\n![animation](/assets/img/trip/animation.png)\n'
        self.post.write_text(self.post.read_text() + markup)
        optimizer.run(self.root)
        self.assertIn(markup, self.post.read_text())
        self.assertNotIn('assets/img/trip/animation.png', (self.root / "_config.yml").read_text())


if __name__ == "__main__":
    unittest.main()
