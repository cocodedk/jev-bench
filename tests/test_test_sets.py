"""The test-sets page is generated from the datasets, escaped, and embeds the same data its tools serve."""
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("build_test_sets", Path(__file__).resolve().parents[1] / "scripts/build_test_sets.py")
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class TestSetPageTests(unittest.TestCase):
    def test_page_escapes_text_and_embeds_every_case(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "datasets").mkdir()
            (root / "website").mkdir()
            data = {"name": "decisions-noul", "type": "noul", "instructions": "Say <b>yes</b>", "labels": ["true", "false"],
                    "cases": [{"id": "n-01", "text": "</script><img src=x>", "expected": "true"},
                              {"id": "n-02", "text": "x <!-- <script> y", "expected": "false"}]}
            (root / "datasets/decisions-noul.json").write_text(json.dumps(data))
            self.assertEqual(BUILDER.build(root), 1)
            page = (root / "website/test-sets.html").read_text()
            self.assertIn("Say &lt;b&gt;yes&lt;/b&gt;", page)
            self.assertIn("<td>&lt;/script&gt;&lt;img src=x&gt;</td>", page)
            self.assertNotIn("</script><img", page)
            self.assertEqual(page.count("<script"), 2)
            self.assertNotIn("<!--", page.split('id="test-sets">')[1])
            embedded = re.search(r'<script type="application/json" id="test-sets">(.*?)</script>', page, re.DOTALL)
            assert embedded is not None
            self.assertEqual(json.loads(embedded.group(1)), [data])
            (root / "datasets/decisions-noul.json").unlink()
            with self.assertRaises(ValueError):
                BUILDER.build(root)
