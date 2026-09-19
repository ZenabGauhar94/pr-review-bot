import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pr_reviewer.diff_parser import parse_unified_diff, render_for_llm

SAMPLE_DIFF = """diff --git a/foo.py b/foo.py
index e69de29..b6fc4c6 100644
--- a/foo.py
+++ b/foo.py
@@ -1,3 +1,5 @@
 def foo():
-    return 1
+    x = 1
+    return x
+
 def bar():
"""


def test_parses_single_file():
    files = parse_unified_diff(SAMPLE_DIFF)
    assert len(files) == 1
    assert files[0].new_path == "foo.py"


def test_added_lines_have_correct_line_numbers():
    files = parse_unified_diff(SAMPLE_DIFF)
    added = files[0].added_lines()
    contents_and_lines = [(l.content, l.new_lineno) for l in added]
    assert ("    x = 1", 2) in contents_and_lines
    assert ("    return x", 3) in contents_and_lines


def test_removed_lines_have_no_new_lineno():
    files = parse_unified_diff(SAMPLE_DIFF)
    removed = [l for l in files[0].lines if l.kind == "-"]
    assert len(removed) == 1
    assert removed[0].new_lineno is None
    assert removed[0].content == "    return 1"


def test_render_for_llm_includes_line_numbers():
    files = parse_unified_diff(SAMPLE_DIFF)
    rendered = render_for_llm(files)
    assert "FILE: foo.py" in rendered
    assert "2 +" in rendered


def test_render_for_llm_respects_char_budget():
    files = parse_unified_diff(SAMPLE_DIFF)
    rendered = render_for_llm(files, max_chars=5)
    assert "skipped" in rendered
