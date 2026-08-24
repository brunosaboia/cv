# Bruno Saboia's CV generator
## What
This is a small pet project that helps me with the building of my CV and deploy it to my website in an automated fashion.

It reads from a single source of truth (a [JSON](https://www.json.org/json-en.html) file), and through a [Jinja2](https://jinja.palletsprojects.com/en/stable/) template, it generates a `.tex` file, which is then compiled into the final PDF file.

For the deployment, [another repo](https://github.com/brunosaboia/cv-data) is used. This repo is private because my personal data is there. If you have a real need for it, drop me an inbox and I can analyze your request and grant access.

## Why
Throughout my career, I have had to write many versions of my CV. As a programmer, I do not like to repeat myself, so copy-pasting data from one CV standard to another seemed to be a little bit of a re-work. Initially, my idea was to use [LinkedIn](https://www.linkedin.com/) as a source of truth for my data, but they don't have a good API for that. Therefore, I decide to take control of my own data and make this little project.

Another big reason for doing this project is my believe that you should own your on data, so here we are :)

## Where
A sample PDF compiled used this project can be found [here](https://saboia.it/assets/pdf/cv/cv-sample.pdf).

## Who
[Bruno Saboia de Albuquerque](https://linkedin.com/in/brunosaboia).

## How
If for some odd reason you want to run this own your own, it should be straight-forward. You need [uv](https://docs.astral.sh/uv/) and a LaTeX distribution providing `pdflatex`; a `Makefile` does most of the heavy-lifting (`make setup-dev` once, then `make build`). Python dependencies are declared in `pyproject.toml` and locked in `uv.lock`.

Everything a pipeline needs is parametrized (via `make` variables or environment):

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATA_DIR` | `data` | Directory holding `cv.json` and its assets (e.g. the photo, referenced in the JSON relative to this dir) |
| `INPUT_JSON` | `$(DATA_DIR)/cv.json` | The CV data file |
| `MARKET` | `international` | Target market (`switzerland`, `continental_europe`, `international`) selecting presentation rules |
| `MARKET_RULES` | `config/market_rules.json` | Presentation rules; the in-repo file is the default, override if needed |
| `LAYOUT` | `classic` | Which rendering to produce — `classic`, `ats`, or `txt` (see below) |
| `LINKS` | `1` | `0` emits no clickable link annotations, keeping every URL as text (see below) |
| `COMPANY_DESCRIPTIONS` | `mid` | `min`/`mid`/`max` — how many employer blurbs to print (see below) |
| `RULES_OVERRIDE` | *(empty)* | Ad-hoc `key=value,key=value` flag overrides applied after `MARKET` and `LAYOUT`'s own rules, e.g. `show_photo=false,show_address=true` (see below) |
| `TARGET` | `cv`, plus `-$(LAYOUT)`, `-$(MARKET)`, `-nolinks`, `-alldesc`/`-nodesc`, `-custom` when non-default | Output base name — no two builds overwrite each other |
| `OUTDIR` | `out` | Output directory |
| `STRICT` | `0` | `1` fails on unknown market or missing files instead of degrading gracefully |
| `COMMIT_SHA` | `git rev-parse` | Stamp embedded in `classic`'s footer; CI can inject its own — `ats`/`txt` carry no footer |

`make prod-build` is the CI entry point: it syncs dependencies with `uv sync --frozen` (the lockfile is authoritative) and builds with `STRICT=1`. Typical pipeline invocation:

```sh
make prod-build DATA_DIR=/path/to/cv-data MARKET=switzerland
```

## Market rules
`config/market_rules.json` holds a `"markets"` object, one fully-spelled-out flag set per named market, plus a `"default_market"` key naming which one applies when `--market`/`MARKET` is omitted or unrecognized. Templates read each flag with `market.get("flag", true)` — a missing rules file or an unknown market degrades to showing everything rather than producing an empty CV — so every market entry states each flag explicitly to keep that fallback from leaking personal fields into a conservative build.

| Flag | `international` (default) | `continental_europe`, `switzerland` | Controls |
|------|:--------------------------:|:------------------------------------:|----------|
| `show_photo` | ✗ | ✓ | `personal.photo` |
| `show_dob` | ✗ | ✓ | `personal.dob` |
| `show_address` | ✗ | ✓ | `personal.address` |
| `show_nationality` | ✗ | ✓ | `personal.nationality` |

A layout can veto a market: `LAYOUT_RULE_OVERRIDES` in `src/generate_cv.py` is applied after the market rules, which is how `ats` and `txt` stay photo-free even when built for `switzerland`.

For a one-off build that doesn't warrant a whole named market, `RULES_OVERRIDE`/`--rules-override` flips individual flags directly from the command line, applied last so it wins over both the market and the layout:

```sh
make build MARKET=switzerland RULES_OVERRIDE='show_photo=false'
```

An unknown flag name or a value other than `true`/`false` warns and is skipped (or fails under `--strict`), the same convention as an unknown market. A missing `market_rules.json` doesn't block a `RULES_OVERRIDE`-only build either — it degrades to showing everything, same as without an override, and the override still applies on top.

## Language levels
`languages[].level` in the data is our own scale, not a display string: `0` native, `1` fluent, `2` advanced, `3` intermediate, `4` basic. `generate_cv.py` translates it to a display string once, per market, before any template sees it — so unlike a market rule, there's no flag for a template to read:

| Level | `international` | `continental_europe`, `switzerland` |
|:-----:|------|:----------:|
| `0` | Native | Native |
| `1` | Full professional proficiency | C2 |
| `2` | Professional working proficiency | B2 |
| `3` | Limited professional proficiency | B1 |
| `4` | Basic | A2 |

CEFR has six tiers (A1–C2) to our four non-native ones, so the mapping skips A1 and C1 rather than cluster at either end of the scale; native is kept as its own label on both sides rather than folded into C2, since a mother tongue isn't a CEFR tier at all. A level outside `0`–`4` warns and prints the raw value (or fails under `--strict`) rather than guessing.

## Layouts
`MARKET` decides *what* is shown; `LAYOUT` decides *how* it is rendered. The two are independent and compose, so `LAYOUT=ats MARKET=switzerland` is a thing you can build. Each layout is a self-contained directory under `src/template/` holding a root `cv.j2` and its own `sections/`.

| Layout | Output | For |
|--------|--------|-----|
| `classic` | `out/cv.pdf` | The typographic CV — `res.cls`, margin section titles, right-aligned dates, photo where the market allows one |
| `ats` | `out/cv-ats.pdf` | The copy you upload to a job portal, tuned for résumé scanners and LLM parsers |
| `txt` | `out/cv-txt.txt` | Plain text, no PDF step at all — for portals that take a `.txt` upload, or whose PDF extraction can't be trusted |

```sh
make build LAYOUT=ats                     # -> out/cv-ats.pdf
make build LAYOUT=ats MARKET=switzerland  # -> out/cv-ats-switzerland.pdf
make build LAYOUT=txt                     # -> out/cv-txt.txt
```

### Why a separate ATS layout
Applicant tracking systems (Workday, Taleo, Greenhouse …) don't read the *page*, they read the PDF's **text layer**, roughly in content-stream order. The classic layout is built for human eyes and loses information on the way through:

* `res.cls` puts section titles in the left margin, so extraction interleaves the heading with the first line of body text — `Summary   AI/ML engineer with...` — and the section boundary disappears;
* dates are pushed right with `\hfill`, which emits them far from their heading, detaching *June 2023 – Present* from the employer it belongs to;
* justified text hyphenates across line breaks, and nothing rejoins the halves, so `Kuber-` / `netes` stops matching the keyword *Kubernetes*;
* links are labelled `GitHub` and `LinkedIn` — the addresses live in the annotation layer, which text extraction never sees.

The `ats` layout is a plain `article` that gives all of that up on purpose: one column, strictly linear order, no `\hfill` and no tabulars, hyphenation off, labelled one-per-line contact fields, full URLs printed as their own link text, conventional section names (*Work Experience*, *Professional Summary*, …) that parsers match against, skills as flat comma-separated keyword lines, `cmap`-generated ToUnicode maps so glyphs decode back to Unicode, no page numbers, and each entry's employer/role/dates block held together across page breaks. It never emits a photo, whatever the market says — it carries nothing a parser can read, and the floating box it needs is exactly the overlapping geometry that derails page segmentation. It is A4; the classic layout inherits Letter from `res.cls`.

### Link-free builds
Some employers' systems dislike PDF link annotations — the `<a href>` of a PDF — and some parsers trip over them. `LINKS=0` emits none, while keeping every address readable as text:

```sh
make build LINKS=0                    # -> out/cv-nolinks.pdf
make build LAYOUT=ats LINKS=0         # -> out/cv-ats-nolinks.pdf
```

Both PDF layouts honour it, but they pay different prices. In `ats` every link's text was already the URL itself, so the text layer comes out byte-for-byte identical — only the annotations disappear. In `classic` several links are *labelled* (`GitHub`, `LinkedIn`, `Transcript of records`, and the award / certification / review dates), and dropping those would take the addresses out of the document entirely, so `LINKS=0` prints them instead: as a URL pair in the header, and on a continuation line under the entry elsewhere. That makes a link-free `classic` noticeably denser than the normal one. A `LINKS=1` build is unaffected — it renders exactly as it always has. `txt` has no link annotations to drop in the first place — every address is already plain text — so `LINKS` makes no difference to its output.

### Company description verbosity
An `experience[]` entry can carry two different blurbs: `item.description` (what *you* did there — always printed) and `item.company`'s own `description` (what the *employer* is — a household name doesn't need it explained). Each employer in `companies[]` can be marked `"is_well_known": true`, but whether a build actually acts on that is a separate knob:

```sh
make build                                  # -> out/cv.pdf         (mid, default)
make build COMPANY_DESCRIPTIONS=max         # -> out/cv-alldesc.pdf
make build COMPANY_DESCRIPTIONS=min         # -> out/cv-nodesc.pdf
```

| Level | Behaviour |
|-------|-----------|
| `min` | Hides every employer's blurb, even one *not* flagged `is_well_known` |
| `mid` (default) | Hides only an employer flagged `is_well_known: true` — today's behaviour |
| `max` | Shows every employer's blurb, even one flagged `is_well_known: true` |

The level is resolved once per build, in `generate_cv.py`, into a plain `company.show_description` boolean — every layout's template reads that one flag rather than re-deriving it from `is_well_known` itself.

### Why a separate txt layout
Even the `ats` layout only wins the *text layer a scanner extracts from the PDF* — it still goes through `pdflatex`, and font substitution, a missing package, or a broken toolchain install can all corrupt that layer before a parser ever sees it. Some portals take a `.txt` upload directly, or run extraction too crude to trust with a PDF at all. `txt` sidesteps the PDF step entirely: what Jinja renders to `out/cv-txt.txt` *is* the artefact, so there is nothing between the data and the parser. It shares the `ats` layout's section ordering, conventional heading names, and one-fact-per-line contact block, but drops all markup — no LaTeX, no escaping, just plain lines. `make build LAYOUT=txt` needs neither `pdflatex` nor `check-latex` to succeed.

`txt` also collapses a remote role's location: `"Remote (Brazil -- US)"` in the data prints as the bare `"Remote"`. An ATS's location field parser expects a single place name, not a parenthetical country pair, so the full string was landing there as noise or a mis-parsed field. `classic` and `ats` keep the full string — a human or a scanner reading the *page* handles the parenthetical fine.

Adding a layout means adding a directory: `src/template/<name>/cv.j2` plus `sections/*.j2`, and it shows up in `make build LAYOUT=<name>` with no code change. Presentation rules a layout cannot express are declared in `LAYOUT_RULE_OVERRIDES` in `src/generate_cv.py`, and win over the market.

## Future
Adjusting a CV for a specific role — for example, by changing some wording or emphasizing some skill set — is something that I want to look further. Also, exploring LLMs to rephrase some wording for some specific context might sound like a good idea.

## Contributing
Commits to this repo and to `cv-data` always follow conventional commits: a lowercase `type:` prefix (`feat:`, `fix:`, `chore:`, `style:`, `ci:`, `doc:` — `doc:`, not `docs:`), no trailing period, and one logical change per commit.

## License
This project is licensed under the [MIT License](https://license.md/licenses/mit-license/).
