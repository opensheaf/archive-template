#!/usr/bin/env python3
"""Carry out an operation on the archive described by an issue form.

Run by .github/workflows/from-issue.yml, in the root of the archive, after
the workflow has checked that the issue's author may write to the
repository. Reads the issue from the event file (GITHUB_EVENT_PATH), never
from the command line; downloads the files attached to the form; runs
osheaf; writes a message for the issue to RESULT_FILE (Markdown) and the
commit message to COMMIT_FILE. Exits 0 on success, 1 on an error the author
can fix (explained in RESULT_FILE), 2 if the issue is not an osheaf form.

The commands are those of the README, with the same options: the archive is
the same whether a deposit comes from the command line or from an issue.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

OSHEAF = shlex.split(os.environ.get("OSHEAF", "osheaf"))
NO_RESPONSE = "_No response_"
LINK = re.compile(r"!?\[([^\]]*)\]\((https?://[^)\s]+)\)")
IDENT = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
SOURCE_SUFFIXES = {".tex", ".ltx", ".tm", ".md", ".typ", ".lyx", ".rst", ".org", ".txt"}
LICENCES = {"cc-by-4.0", "cc-by-sa-4.0", "cc0-1.0", "gpl-3.0-only", "gpl-3.0-or-later"}

# The heading that identifies each form (a label of one of its fields).
FORMS = {
    "PDF of this version": "deposit",
    "Text of the notice": "notice",
    "Reason for the withdrawal": "withdraw",
    "New licence": "relicense",
}


class Problem(Exception):
    """An error the author can fix, explained in plain words."""


def sections(body):
    """The fields of an issue form: {label: text}, empty fields as ''."""
    out, label, lines = {}, None, []
    for line in (body or "").splitlines():
        m = re.match(r"^### (.+?)\s*$", line)
        if m:
            if label is not None:
                out[label] = "\n".join(lines).strip()
            label, lines = m.group(1), []
        elif label is not None:
            lines.append(line)
    if label is not None:
        out[label] = "\n".join(lines).strip()
    return {k: ("" if v == NO_RESPONSE else v) for k, v in out.items()}


def field(form, label, required=False):
    value = form.get(label, "").strip()
    if required and not value:
        raise Problem(f"The field **{label}** is empty, and it is needed.")
    return value


def lines(text):
    return [l.strip() for l in text.splitlines() if l.strip() and not LINK.fullmatch(l.strip())]


def identifier(form):
    ident = field(form, "Identifier", required=True)
    if not IDENT.match(ident) or len(ident) > 32:
        raise Problem(f"The identifier `{ident}` is not valid: use at most 32 characters, "
                      "lower-case letters and digits, words joined by `-` (for instance "
                      "`kpz-uniqueness`).")
    return ident


def date(form, label):
    value = field(form, label)
    if value and not DATE.match(value):
        raise Problem(f"The field **{label}** should be a date written as YYYY-MM-DD, not `{value}`.")
    return value


def licence(form, label):
    """The licence chosen in a dropdown: an SPDX-like code, a statement, or None."""
    value = field(form, label)
    m = re.search(r"\(([a-z0-9.-]+)\)\s*$", value)
    if m and m.group(1) in LICENCES:
        return m.group(1)
    if value.lower().startswith("all rights reserved"):
        return "All rights reserved"
    return None  # keep as before


def safe_name(name):
    name = Path(name.strip() or "file").name
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.") or "file"
    return name


def download(form, label, folder):
    """The files attached to a field, downloaded into folder: a list of paths."""
    files = []
    for text, url in LINK.findall(form.get(label, "")):
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / safe_name(text or url.rsplit("/", 1)[-1])
        n = 1
        while path.exists():
            path = path.with_name(f"{path.stem}-{n}{path.suffix}")
            n += 1
        cmd = ["curl", "-fsSL", "--retry", "3", "-o", str(path)]
        token = os.environ.get("GITHUB_TOKEN")
        if token and url.startswith("https://github.com/"):
            # curl does not send this header on to other hosts after a redirect
            cmd += ["-H", f"Authorization: Bearer {token}"]
        result = subprocess.run(cmd + [url], capture_output=True, text=True)
        if result.returncode != 0:
            raise Problem(f"The file `{text}` attached to **{label}** could not be downloaded "
                          f"({result.stderr.strip() or 'curl failed'}).")
        files.append(path)
    return files


def unpack(archive, folder):
    """Extract a zip safely: no absolute paths, no '..', no system files."""
    names = []
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            name = info.filename
            parts = Path(name).parts
            if info.is_dir() or not parts:
                continue
            if name.startswith("/") or ".." in parts or parts[0] == "__MACOSX" \
                    or parts[-1] == ".DS_Store":
                continue
            target = folder / Path(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())
            names.append(Path(*parts).as_posix())
    # a zip made of a single top folder: work inside it
    tops = {n.split("/", 1)[0] for n in names}
    if len(tops) == 1 and all("/" in n for n in names):
        top = tops.pop()
        return folder / top, [n.split("/", 1)[1] for n in names]
    return folder, names


def sources(form, work):
    """The main source and the other sources, as (main, [(file, logical path)])."""
    attached = download(form, "Sources", work / "attached")
    main_name = field(form, "Main source")
    if not attached:
        return None, []
    if len(attached) == 1 and attached[0].suffix.lower() == ".zip":
        root, names = unpack(attached[0], work / "sources")
        if not names:
            raise Problem("The zip of the sources is empty.")
        if main_name:
            if main_name not in names:
                raise Problem(f"The main source `{main_name}` is not in the zip; it holds: "
                              + ", ".join(f"`{n}`" for n in sorted(names)[:30]) + ".")
            main = main_name
        else:
            candidates = [n for n in names if "/" not in n
                          and Path(n).suffix.lower() in SOURCE_SUFFIXES]
            if len(candidates) != 1:
                raise Problem("Say which file of the zip is the main source, in the field "
                              "**Main source** (for instance `paper.tex`).")
            main = candidates[0]
        others = [(root / n, n) for n in names if n != main]
        return root / main, others
    if len(attached) == 1:
        return attached[0], []
    if not main_name:
        raise Problem("Several source files are attached: put them in one zip, or say which one "
                      "is the main source in the field **Main source**.")
    named = [p for p in attached if p.name == safe_name(main_name)]
    if not named:
        raise Problem(f"The main source `{main_name}` is not among the attached files.")
    return named[0], [(p, p.name) for p in attached if p is not named[0]]


def osheaf(*args):
    result = subprocess.run(OSHEAF + [str(a) for a in args], capture_output=True, text=True)
    if result.returncode != 0:
        lines_ = (result.stderr or result.stdout).strip().splitlines()
        errors = [l for l in lines_ if l.startswith("osheaf: error:")]
        message = errors or lines_[-15:]
        raise Problem("osheaf stopped with this message:\n\n```\n" + "\n".join(message) + "\n```")
    return result.stdout


def current_description(ident):
    """Title and authors of the current version of a document already in the
    archive, as `osheaf deposit` takes them, or (None, []) for a new one."""
    inventory = Path("ocfl") / ident / "inventory.json"
    if not inventory.exists():
        return None, []
    head = json.loads(inventory.read_text(encoding="utf-8"))["head"]
    datacite = Path("ocfl") / ident / head / "content" / "datacite.json"
    if not datacite.exists():
        # the file is unchanged since an earlier version: find it in the state
        inv = json.loads(inventory.read_text(encoding="utf-8"))
        digest = next(d for d, paths in inv["versions"][head]["state"].items()
                      if "datacite.json" in paths)
        datacite = Path("ocfl") / ident / inv["manifest"][digest][0]
    d = json.loads(datacite.read_text(encoding="utf-8"))
    title = (d.get("titles") or [{}])[0].get("title")
    authors = []
    for c in d.get("creators", []):
        aff = [a.get("name") if isinstance(a, dict) else a for a in c.get("affiliation", [])]
        authors.append(c["name"] + (f"|{aff[0]}" if aff and aff[0] else ""))
    return title, authors


def deposit(form, number, work):
    ident = identifier(form)
    pdfs = [p for p in download(form, "PDF of this version", work / "pdf")
            if p.suffix.lower() == ".pdf"]
    if not pdfs:
        raise Problem("Attach the PDF of this version to the field **PDF of this version**.")
    main, others = sources(form, work)
    missing = field(form, "If there are no sources, why")
    if main is None and not missing:
        raise Problem("Attach the sources (one file, or a zip), or say why there are none in "
                      "the field **If there are no sources, why**.")
    args = ["deposit", ident]
    if main is not None:
        args.append(main)
    args += ["--pdf", pdfs[0]]
    if main is None:
        args += ["--no-source", missing]
    for path, logical in others:
        args += ["--extra-source", f"{path}={logical}"]
    title, authors = field(form, "Title"), lines(field(form, "Authors"))
    if not title or not authors:
        # a new version: what is left empty stays as in the current version
        old_title, old_authors = current_description(ident)
        title = title or old_title
        authors = authors or old_authors
    if not title or not authors:
        raise Problem("Give the **Title** and the **Authors** (they can be left empty only for "
                      "a new version of a paper already in the archive).")
    args += ["--title", title]
    for author in authors:
        args += ["--author", author]
    if abstract := field(form, "Abstract"):
        f = work / "abstract.txt"
        f.write_text(abstract + "\n", encoding="utf-8")
        args += ["--abstract-file", f]
    for keyword in re.split(r"[,;\n]", field(form, "Keywords")):
        if keyword.strip():
            args += ["--keyword", keyword.strip()]
    if rights := licence(form, "Licence"):
        args += ["--rights", rights]
    for related in lines(field(form, "Related identifiers")):
        args += ["--related", related]
    if changes := field(form, "What changed (for a new version)"):
        args += ["--changes", changes]
    if available := date(form, "Date this version became public"):
        args += ["--available", available]
    if issued := date(form, "Date the paper first appeared"):
        args += ["--issued", issued]
    args += ["--message", f"Deposit from issue #{number}"]
    osheaf(*args)
    return ident, f"Deposit {ident} (issue #{number})", "deposited"


def notice(form, number, work):
    ident = identifier(form)
    about = field(form, "Document version it is about", required=True)
    if not about.isdigit():
        raise Problem(f"**Document version it is about** should be a number (1, 2, ...), "
                      f"not `{about}`.")
    args = ["notice", ident, "--about", about, "--text", field(form, "Text of the notice", True)]
    files = download(form, "Full statement (optional)", work / "notice")
    if files:
        args += ["--file", files[0]]
    args += ["--message", f"Notice from issue #{number}"]
    osheaf(*args)
    return ident, f"Notice about {ident}, version {about} (issue #{number})", "given a notice"


def withdraw(form, number, work):
    ident = identifier(form)
    args = ["withdraw", ident, "--reason", field(form, "Reason for the withdrawal", True),
            "--message", f"Withdrawal from issue #{number}"]
    osheaf(*args)
    return ident, f"Withdraw {ident} (issue #{number})", "withdrawn (its files stay in the archive)"


def relicense(form, number, work):
    ident = identifier(form)
    rights = licence(form, "New licence")
    if rights not in LICENCES:
        raise Problem("Choose the new licence in the field **New licence**.")
    args = ["relicense", ident, "--rights", rights]
    if method := field(form, "How the authors agreed"):
        args += ["--method", method]
    args += ["--message", f"New licence from issue #{number}"]
    osheaf(*args)
    return ident, f"Relicense {ident} as {rights} (issue #{number})", f"relicensed as {rights}"


OPERATIONS = {"deposit": deposit, "notice": notice, "withdraw": withdraw,
              "relicense": relicense}


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    issue = event["issue"]
    form = sections(issue.get("body"))
    kind = next((FORMS[h] for h in FORMS if h in form), None)
    result_file = Path(os.environ.get("RESULT_FILE", "result.md"))
    commit_file = Path(os.environ.get("COMMIT_FILE", "commit.txt"))
    if kind is None:
        result_file.write_text("This issue is not one of the archive's forms.\n", encoding="utf-8")
        return 2
    try:
        if not Path("osheaf.json").exists():
            raise Problem("The archive is not set up yet: run the workflow **Set up the archive** "
                          "first (Actions tab), then open the issue again.")
        with tempfile.TemporaryDirectory() as tmp:
            ident, commit, done = OPERATIONS[kind](form, issue["number"], Path(tmp))
        osheaf("collect")
        osheaf("index")
        osheaf("verify")
    except Problem as p:
        result_file.write_text(
            f"Nothing was changed in the archive.\n\n{p}\n\n"
            "Edit this issue to correct it, then close and reopen it to try again.\n",
            encoding="utf-8")
        return 1
    base = json.loads(Path("osheaf.json").read_text(encoding="utf-8")).get("baseUrl", "")
    page = f"{base}paper/{ident}/" if base else f"paper/{ident}/"
    result_file.write_text(
        f"Done: `{ident}` was {done}.\n\n"
        f"Its page will be at <{page}> once GitHub Pages has published the site "
        "(usually within a few minutes).\n", encoding="utf-8")
    commit_file.write_text(commit + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
