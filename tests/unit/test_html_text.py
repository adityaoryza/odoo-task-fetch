import unittest

from odoo_task.html_text import html_to_markdown


class HtmlToMarkdown(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(html_to_markdown(""), "")
        self.assertEqual(html_to_markdown(None), "")

    def test_paragraphs_lists_and_emphasis(self):
        html = "<p>One <b>bold</b> and <i>it</i>.</p><ul><li>a</li><li>b</li></ul><ol><li>x</li><li>y</li></ol>"
        text = html_to_markdown(html)
        self.assertIn("One **bold** and *it*.", text)
        self.assertIn("- a\n- b", text)
        self.assertIn("1. x\n2. y", text)

    def test_links_and_images(self):
        html = '<p><a href="https://e.com/x">site</a> <img src="img_1.png" alt="shot"/></p>'
        self.assertIn("[site](https://e.com/x)", html_to_markdown(html))
        self.assertIn("![shot](img_1.png)", html_to_markdown(html))
        self.assertNotIn("img_1.png", html_to_markdown(html, keep_images=False))

    def test_javascript_links_are_dropped(self):
        self.assertNotIn("javascript:", html_to_markdown('<a href="javascript:alert(1)">x</a>'))

    def test_scripts_and_styles_are_ignored(self):
        text = html_to_markdown("<style>p{color:red}</style><script>alert(1)</script><p>ok</p>")
        self.assertEqual(text, "ok")

    def test_code_blocks_keep_their_layout(self):
        text = html_to_markdown("<pre>a\n  b</pre>")
        self.assertIn("```\na\n  b\n```", text)

    def test_headings_go_one_level_down(self):
        self.assertTrue(html_to_markdown("<h1>Title</h1><p>x</p>").startswith("## Title"))

    def test_blocks_are_separated_by_blank_lines(self):
        text = html_to_markdown(
            '<p>A</p><p>B</p><ul><li>x</li><li>y<ul><li>n</li></ul></li></ul><p><img src="i.png"/></p><p>end</p>'
        )
        self.assertEqual(text, "A\n\nB\n\n- x\n- y\n  - n\n\n![image](i.png)\n\nend")

    def test_max_length(self):
        text = html_to_markdown("<p>" + "x" * 100 + "</p>", max_length=20)
        self.assertLessEqual(len(text), 20)
        self.assertTrue(text.endswith("..."))


if __name__ == "__main__":
    unittest.main()


class SecretLinks(unittest.TestCase):
    def test_access_tokens_are_removed_from_links(self):
        html = '<a href="/web/content/9?unique=abc&download=true&access_token=SECRET-TOKEN-1">file.zip</a>'
        text = html_to_markdown(html, base_url="https://odoo.example.com")
        self.assertNotIn("SECRET-TOKEN-1", text)
        self.assertNotIn("access_token", text)
        self.assertIn("https://odoo.example.com/web/content/9?", text)
        self.assertIn("download=true", text)

    def test_tokens_are_removed_from_image_sources_too(self):
        html = '<img src="/web/image/5?access_token=SECRET-TOKEN-2&x=1" alt="a"/>'
        text = html_to_markdown(html, base_url="https://odoo.example.com")
        self.assertNotIn("SECRET-TOKEN-2", text)
        self.assertIn("![a](https://odoo.example.com/web/image/5?x=1)", text)

    def test_other_token_like_parameters_and_case(self):
        text = html_to_markdown('<a href="https://x.example.com/f?Token=T1&signature=S1&ok=1">x</a>')
        self.assertNotIn("T1", text)
        self.assertNotIn("S1", text)
        self.assertIn("ok=1", text)

    def test_relative_links_stay_relative_without_a_base(self):
        self.assertIn("(/web/content/9)", html_to_markdown('<a href="/web/content/9">f</a>'))

    def test_anchors_and_mail_links_are_left_alone(self):
        text = html_to_markdown(
            '<a href="#top">up</a> <a href="mailto:a@example.com">mail</a>', base_url="https://o.example.com"
        )
        self.assertIn("(#top)", text)
        self.assertIn("(mailto:a@example.com)", text)
