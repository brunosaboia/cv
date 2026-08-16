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
| `MARKET` | `default` | Target market code (`CH`, `BR`, …) selecting presentation rules |
| `MARKET_RULES` | `config/market_rules.json` | Presentation rules; the in-repo file is the default, override if needed |
| `LAYOUT` | `classic` | Which rendering to produce — `classic` or `ats` (see below) |
| `LINKS` | `1` | `0` emits no clickable link annotations, keeping every URL as text (see below) |
| `TARGET` | `cv`, plus `-$(LAYOUT)`, `-$(MARKET)` and `-nolinks` when non-default | Output base name — no two builds overwrite each other |
| `OUTDIR` | `out` | Output directory |
| `STRICT` | `0` | `1` fails on unknown market or missing files instead of degrading gracefully |
| `COMMIT_SHA` | `git rev-parse` | Stamp embedded in the PDF; CI can inject its own |

`make prod-build` is the CI entry point: it syncs dependencies with `uv sync --frozen` (the lockfile is authoritative) and builds with `STRICT=1`. Typical pipeline invocation:

```sh
make prod-build DATA_DIR=/path/to/cv-data MARKET=CH
```

## Layouts
`MARKET` decides *what* is shown; `LAYOUT` decides *how* it is rendered. The two are independent and compose, so `LAYOUT=ats MARKET=CH` is a thing you can build. Each layout is a self-contained directory under `src/template/` holding a root `cv.j2` and its own `sections/`.

| Layout | Output | For |
|--------|--------|-----|
| `classic` | `out/cv.pdf` | The typographic CV — `res.cls`, margin section titles, right-aligned dates, photo where the market allows one |
| `ats` | `out/cv-ats.pdf` | The copy you upload to a job portal, tuned for résumé scanners and LLM parsers |

```sh
make build LAYOUT=ats            # -> out/cv-ats.pdf
make build LAYOUT=ats MARKET=CH  # -> out/cv-ats-CH.pdf
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

Both layouts honour it, but they pay different prices. In `ats` every link's text was already the URL itself, so the text layer comes out byte-for-byte identical — only the annotations disappear. In `classic` several links are *labelled* (`GitHub`, `LinkedIn`, `Transcript of records`, and the award / certification / review dates), and dropping those would take the addresses out of the document entirely, so `LINKS=0` prints them instead: as a URL pair in the header, and on a continuation line under the entry elsewhere. That makes a link-free `classic` noticeably denser than the normal one. A `LINKS=1` build is unaffected — it renders exactly as it always has.

Adding a layout means adding a directory: `src/template/<name>/cv.j2` plus `sections/*.j2`, and it shows up in `make build LAYOUT=<name>` with no code change. Presentation rules a layout cannot express are declared in `LAYOUT_RULE_OVERRIDES` in `src/generate_cv.py`, and win over the market.

## Future
I want to have various CVs that I can tailor to a specific need or market. For example, in Switzerland, CVs with photos are well-received—on the other hand, in Brazil, this is frowned upon. Adjusting a CV for a specific role —for example, by changing some wording or emphasizing some skill set—is also something that I want to look further. Also, exploring LLMs to rephrase some wording for some specific context might sound like a good idea.

## License
This project is licensed under the [MIT License](https://license.md/licenses/mit-license/).
