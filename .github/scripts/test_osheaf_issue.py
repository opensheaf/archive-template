"""Tests of the functions of osheaf_issue.py that need no archive and no network:
python3 .github/scripts/test_osheaf_issue.py (run by the workflow `examples`)."""

import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osheaf_issue as o  # noqa: E402


def refused(f, *args):
    try:
        f(*args)
    except o.Problem as p:
        return str(p)
    raise AssertionError(f"{f.__name__}{args}: not refused")


def test_versions_named_twice_are_vetted_once():
    assert o.versions({"V": "5, 5"}, "V") == [5]
    assert o.versions({"V": "6; 5 6, 5"}, "V") == [6, 5]
    assert o.versions({"V": ""}, "V") == []
    assert "should be document versions" in refused(o.versions, {"V": "five"}, "V")



def test_names_from_another_archive_are_checked():
    name, owner = "a" * 52, "b" * 51 + "q"
    other = "https://other.example/archive/"
    form = {"Member": "heat", "Archive": other}
    saved = o.own_base, o.remote_objects
    try:
        o.own_base = lambda: "https://example.org/repository/"
        o.remote_objects = lambda base: [{"label": "heat", "name": name, "owner": owner}]
        entry, key, _ = o.member_ref(form, "Member", "Archive")
        assert entry == {"uri": f"sheaf:{name}:{owner}", "at": [other]} and key == (name, owner)
        for bad in ({"name": "../../x", "owner": owner}, {"name": name, "owner": owner + "\n?at=x"},
                    {"name": name.upper(), "owner": owner}, {"name": name, "owner": "b" * 52},
                    {"name": name, "owner": None}, {"name": 5, "owner": owner}):
            o.remote_objects = lambda base, bad=bad: [dict(bad, label="heat")]
            assert "is not one (section 5.2)" in refused(o.member_ref, form, "Member", "Archive")
    finally:
        o.own_base, o.remote_objects = saved


def test_zip_of_sources_is_unpacked_within_limits():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        archive = tmp / "sources.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("paper/paper.tex", "x")
            z.writestr("paper/fig=1.tex", "y")
            z.writestr("../outside.tex", "no")
            z.writestr("/absolute.tex", "no")
            z.writestr("paper/a/../../../up.tex", "no")
            z.writestr("big.bin", b"0" * (1 << 20))   # 1 MiB, compressed to a few KiB
        root, names = o.unpack(archive, tmp / "out")
        assert root == tmp / "out" and sorted(names) == ["big.bin", "paper/fig=1.tex", "paper/paper.tex"]
        assert (tmp / "out" / "paper" / "fig=1.tex").read_text() == "y"
        assert not any(p.name in ("outside.tex", "absolute.tex", "up.tex") for p in tmp.rglob("*"))
        saved = o.MAX_UNPACKED, o.MAX_MEMBERS
        try:
            o.MAX_UNPACKED = 1 << 19
            assert "expands to more than" in refused(o.unpack, archive, tmp / "again")
            o.MAX_UNPACKED, o.MAX_MEMBERS = saved[0], 3
            assert "more than 3 files" in refused(o.unpack, archive, tmp / "again")
        finally:
            o.MAX_UNPACKED, o.MAX_MEMBERS = saved


def test_base_urls_have_no_spaces_or_control_characters():
    assert o.site_url("http://example.org/papers") == "https://example.org/papers/"
    assert o.site_url(" https://example.org/ ") == "https://example.org/"
    for bad in ("https://example.org/\nNODE_OPTIONS=--require=/x", "https://example.org/a b/",
                "https://example.org/\x00/", "ftp://example.org/", "https:///", "https://e.org/?q=1"):
        assert "is not the address of a site" in refused(o.site_url, bad), bad


def test_an_unexpected_error_still_answers():
    with tempfile.TemporaryDirectory() as tmp:
        result = Path(tmp) / "result.md"
        env = {"RESULT_FILE": str(result), "GITHUB_SERVER_URL": "https://github.com",
               "GITHUB_REPOSITORY": "someone/papers", "GITHUB_RUN_ID": "42"}
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            o.unexpected(AttributeError("'list' object has no attribute `items`\nsecond line"))
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k)
                else:
                    os.environ[k] = v
        text = result.read_text()
        assert text.startswith("Nothing was changed")
        assert "https://github.com/someone/papers/actions/runs/42" in text
        assert "AttributeError: 'list' object has no attribute 'items' second line" in text

if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_") and callable(f)]
    for t in tests:
        t()
        print(f"ok {t.__name__}")
    print(f"{len(tests)} passed")
