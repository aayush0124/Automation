"""End-to-end tests for the offline file agent. Run with: python -m pytest -q
(or plain ``python tests/test_agent.py`` — a tiny runner is included)."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from offline_agent import analyze, scan  # noqa: E402
from offline_agent.automation import AutomationEngine  # noqa: E402
from offline_agent.rules import Condition, Rule, _parse_size  # noqa: E402


def _make_tree(root):
    """Create a small fixture tree and return it."""
    os.makedirs(os.path.join(root, "sub"), exist_ok=True)
    files = {
        "a.txt": b"hello world",
        "b.txt": b"hello world",          # duplicate of a.txt
        "photo.jpg": b"\xff\xd8\xff" + b"x" * 100,
        "big.bin": b"0" * 5000,
        os.path.join("sub", "note.md"): b"# heading\nsome text",
        ".hidden": b"secret",
    }
    for rel, data in files.items():
        with open(os.path.join(root, rel), "wb") as fh:
            fh.write(data)
    return root


def test_scan_skips_hidden_by_default():
    with tempfile.TemporaryDirectory() as root:
        _make_tree(root)
        names = {fi.name for fi in scan(root)}
        assert ".hidden" not in names
        assert "a.txt" in names
        assert "note.md" in names  # recursive by default


def test_scan_non_recursive():
    with tempfile.TemporaryDirectory() as root:
        _make_tree(root)
        names = {fi.name for fi in scan(root, recursive=False)}
        assert "note.md" not in names


def test_categorize_and_analyze():
    with tempfile.TemporaryDirectory() as root:
        _make_tree(root)
        analysis = analyze(scan(root))
        assert analysis.total_files == 5  # hidden excluded
        assert analysis.by_category.get("document") == 3  # a, b, note.md
        assert analysis.by_category.get("image") == 1
        # a.txt and b.txt are byte-identical -> one duplicate group
        assert len(analysis.duplicates) == 1
        group = next(iter(analysis.duplicates.values()))
        assert len(group) == 2


def test_condition_matching():
    with tempfile.TemporaryDirectory() as root:
        _make_tree(root)
        files = list(scan(root))
        big = Condition(min_size=1000)
        matched = [f.name for f in files if big.matches(f)]
        assert "big.bin" in matched
        assert "a.txt" not in matched

        images = Condition(category=["image"])
        assert [f.name for f in files if images.matches(f)] == ["photo.jpg"]


def test_parse_size():
    assert _parse_size("10MB") == 10 * 1024**2
    assert _parse_size("1.5k") == int(1.5 * 1024)
    assert _parse_size(2048) == 2048
    assert _parse_size(None) is None


def test_automation_dry_run_does_not_touch_fs():
    with tempfile.TemporaryDirectory() as root:
        _make_tree(root)
        dest = os.path.join(root, "sorted")
        rule = Rule(
            name="move images",
            match=Condition(category=["image"]),
            actions=[__import__("offline_agent.rules", fromlist=["Action"]).Action(
                type="move", dest=dest)],
        )
        engine = AutomationEngine([rule], dry_run=True)
        results = engine.run(scan(root))
        assert any(r.action == "move" for r in results)
        assert all(r.dry_run for r in results)
        # nothing actually moved
        assert os.path.exists(os.path.join(root, "photo.jpg"))
        assert not os.path.exists(dest)


def test_automation_apply_moves_file():
    from offline_agent.rules import Action

    with tempfile.TemporaryDirectory() as root:
        _make_tree(root)
        dest = os.path.join(root, "sorted", "images")
        rule = Rule(
            name="move images",
            match=Condition(category=["image"]),
            actions=[Action(type="move", dest=dest)],
        )
        engine = AutomationEngine([rule], dry_run=False)
        engine.run(scan(root))
        assert not os.path.exists(os.path.join(root, "photo.jpg"))
        assert os.path.exists(os.path.join(dest, "photo.jpg"))


def test_rename_template_and_unique_path():
    from offline_agent.rules import Action

    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, "a.txt"), "w") as fh:
            fh.write("x")
        rule = Rule(
            name="rename",
            match=Condition(ext=[".txt"]),
            actions=[Action(type="rename", template="{category}_{stem}.{ext}")],
        )
        engine = AutomationEngine([rule], dry_run=False)
        engine.run(scan(root))
        assert os.path.exists(os.path.join(root, "document_a.txt"))


def test_relative_dest_resolves_against_base_dir():
    from offline_agent.rules import Action

    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, "pic.jpg"), "wb") as fh:
            fh.write(b"\xff\xd8\xff")
        rule = Rule(
            name="sort images",
            match=Condition(category=["image"]),
            actions=[Action(type="move", dest="./sorted/images")],
        )
        engine = AutomationEngine([rule], dry_run=False, base_dir=root)
        engine.run(scan(root))
        # relative dest must land inside the scanned root, not the CWD
        assert os.path.exists(os.path.join(root, "sorted", "images", "pic.jpg"))


def _run_all():
    """Minimal runner so the file works without pytest installed."""
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
