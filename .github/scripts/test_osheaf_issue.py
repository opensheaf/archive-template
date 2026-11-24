"""Tests of the functions of osheaf_issue.py that need no archive and no network:
python3 .github/scripts/test_osheaf_issue.py (run by the workflow `examples`)."""

import sys
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


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_") and callable(f)]
    for t in tests:
        t()
        print(f"ok {t.__name__}")
    print(f"{len(tests)} passed")
