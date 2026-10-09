import base64
import tempfile
import unittest
from pathlib import Path

from odoo_task.images import localize_images

PNG = base64.b64encode(b"\x89PNG-fake-bytes").decode()


class LocalizeImages(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_embedded_images_become_files(self):
        html, saved = localize_images(f'<img src="data:image/png;base64,{PNG}"/>', self.dir, None)
        self.assertEqual(saved, ["img_b64_1.png"])
        self.assertIn('src="img_b64_1.png"', html)
        self.assertEqual((self.dir / "img_b64_1.png").read_bytes(), b"\x89PNG-fake-bytes")

    def test_attachment_images_are_read_once(self):
        calls = []

        def reader(att_id):
            calls.append(att_id)
            return PNG, "image/png"

        html, saved = localize_images('<img src="/web/image/77?x=1"/><img src="/web/image/77"/>', self.dir, reader)
        self.assertEqual(calls, [77])
        self.assertEqual(saved, ["img_att_77.png"])
        self.assertEqual(html.count("img_att_77.png"), 2)

    def test_a_non_image_attachment_is_left_alone(self):
        html, saved = localize_images('<img src="/web/content/5"/>', self.dir, lambda _i: (PNG, "text/html"))
        self.assertEqual(saved, [])
        self.assertIn("/web/content/5", html)

    def test_unknown_mime_types_are_ignored(self):
        html, saved = localize_images(f'<img src="data:image/x-evil;base64,{PNG}"/>', self.dir, None)
        self.assertEqual(saved, [])

    def test_no_reader_keeps_attachment_references(self):
        html, saved = localize_images('<img src="/web/image/9"/>', self.dir, None)
        self.assertEqual(saved, [])
        self.assertIn("/web/image/9", html)


if __name__ == "__main__":
    unittest.main()
