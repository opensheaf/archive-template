# An OpenSheaf archive

A template for keeping your own archive of papers: every version with its
sources and PDF, fixed by digests, standard metadata, a website with a page
per paper (read by Google Scholar), and optionally DOIs from Zenodo. The
archive is plain files in a git repository, following the
[OpenSheaf specification](https://opensheaf.org) (an
[OCFL](https://ocfl.io) storage root with [DataCite](https://datacite.org)
metadata), and is kept with [opensheaf-py](https://github.com/opensheaf/opensheaf-py)
(the `osheaf` command). The first archive made this way is
[mgubi.org/papers](https://mgubi.org/papers/).

## 1. Make your copy

Press **Use this template** on GitHub (for instance a repository called
`papers`), clone it, and install the tools (Python 3.9 or later):

```
pipx install "opensheaf[validate] @ git+https://github.com/opensheaf/opensheaf-py"
```

## 2. Set it up

In your clone:

```
osheaf init . \
  --archive-id tag:example.org,2026:papers \
  --name "Papers of Jane Doe" \
  --base-url https://janedoe.github.io/papers/ \
  --curator "Doe, Jane" --affiliation "Example University" \
  --contact https://example.org/~jane
```

- `--archive-id` names the archive forever, also if it moves: a
  [tag URI](https://www.rfc-editor.org/rfc/rfc4151) built from a domain or an
  e-mail address you control and the year (`tag:janedoe@example.org,2026:papers`
  works too).
- `--base-url` is where the site is served: with GitHub Pages,
  `https://USER.github.io/REPOSITORY/`, or your own domain.

This writes `osheaf.json` (the settings), the storage root `ocfl/`, the main
collection, the discovery document `opensheaf.json` and the website.

## 3. Deposit a paper

```
osheaf deposit kpz-uniqueness paper.tex --pdf paper.pdf \
  --extra-source refs.bib --extra-source figures/fig1.pdf=figures/fig1.pdf \
  --title 'Energy solutions of KPZ are unique' \
  --author "Doe, Jane|Example University" --author "Roe, Richard|Another University" \
  --abstract-file abstract.txt --rights cc-by-4.0 \
  --related "IsIdenticalTo:arxiv:1508.07764"
osheaf collect
osheaf index
osheaf verify
git add -A && git commit -m "Deposit kpz-uniqueness" && git push
```

- The identifier (`kpz-uniqueness`) is permanent and appears in the URL of
  the paper: short (at most 32 characters), lower case, words joined by `-`.
- Sources are any files (LaTeX, Markdown, ...); `--extra-source FILE=PATH`
  puts a file at the path the main source refers to. The PDF is yours: the
  archive keeps exactly the files you give. A paper whose sources are lost can
  be deposited as a PDF alone (`--no-source "the sources were lost"`).
- Titles and abstracts are plain text with mathematics in `$...$`.
- Licence: `--rights cc-by-4.0` (or `cc0-1.0`, or a statement such as
  "All rights reserved", the default); check what your publisher allows for
  papers published in journals.
- A new version: deposit again with the same identifier (`--changes "..."`
  says what changed; abstract, keywords and licence are kept unless given).
  A version written earlier but never public (a submitted manuscript) is
  deposited with `--created DATE`; one found later goes in its place in the
  history with `--after N`.
- Dates: `--available DATE` when the version became public (default today),
  `--issued DATE` when the paper first appeared anywhere.

Nothing deposited is ever changed: corrections are new versions, and a
licence or a link is changed by a description-only version
(`osheaf relicense`, `osheaf relate`). `osheaf --help` lists everything.

## 4. Publish

On GitHub: **Settings → Pages → Deploy from a branch**, branch `main`, folder
`/ (root)`. The site is then at the base URL you chose. Every push is
checked by the workflow `verify` (`osheaf verify`, with the JSON Schemas and
an independent OCFL validator).

## 5. Make it yours

- The look: edit `templates/index.html`, `templates/paper.html` and
  `templates/style.css` (placeholders like `{{title}}`), then `osheaf index`.
- DOIs: `osheaf zenodo ID` deposits the current version of a paper on Zenodo
  and records its DOI (on the Zenodo sandbox, on a copy, unless
  `--production`; tokens in the macOS keychain, see `osheaf zenodo --help`).
- Papers from arXiv: `osheaf arxiv fetch downloads --author YOUR_ARXIV_ID`,
  then `osheaf arxiv import downloads` (every version, with arXiv's files and
  licences; see the README of opensheaf-py).
- Collections of other people's papers, mirrors and signatures: see the
  [specification](https://opensheaf.org) and the
  [FAQ](https://github.com/opensheaf/opensheaf/blob/main/FAQ.md).

## Licence

This template (the pages, style and workflow) is dedicated to the public
domain under [CC0 1.0](LICENSE): use it as you like. The papers you deposit
carry the licences you give them; the archive's metadata is placed under CC0,
as the specification asks.
