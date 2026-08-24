# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A CV generator: a single JSON source of truth (`data/cv.json`) is rendered through Jinja2 templates into `.tex` (compiled to PDF via `pdflatex`) or plain `.txt`. The actual personal data lives in a separate private repo (`cv-data`) and is passed in via `DATA_DIR`/`INPUT_JSON` — this repo only holds the generator, templates, and rendering logic.

## Commands

```sh
make setup-dev              # uv sync + pre-commit install (once)
make build                  # generate + compile -> out/cv.pdf
make test                   # uv run pytest
uv run pytest tests/test_generate.py::TestMarkets   # single test class/file
make local-build             # check-latex + build
make prod-build DATA_DIR=/path/to/cv-data MARKET=CH  # CI entry point: uv sync --frozen, STRICT=1
make clean / make cleanall   # remove build artifacts / whole out/ dir
```

Key `make build` variables (all overridable on the command line, see README for the full table):

- `MARKET` (`default`, `CH`, `DE`, `BR`, `US`, `UK`) — which presentation rules apply
- `LAYOUT` (`classic`, `ats`, `txt`) — which template set renders the data
- `LINKS` (`1`/`0`) — whether PDF link annotations are emitted
- `COMPANY_DESCRIPTIONS` (`min`/`mid`/`max`) — how many employer blurbs print
- `STRICT` (`0`/`1`) — fail vs. warn-and-degrade on unknown market/missing files
- `DATA_DIR` / `INPUT_JSON` / `MARKET_RULES` — input locations
- `RULES_OVERRIDE` — ad-hoc `key=value,key=value` flag overrides (e.g. `show_photo=false`), applied after `MARKET` and `LAYOUT`'s own rules, for a one-off build that doesn't warrant a named market entry

`TARGET` auto-composes from whichever of these are non-default (e.g. `cv-ats-CH-nolinks`), so different build combinations never overwrite each other's output in `out/`.

Pre-commit runs `make test` plus four `make local-build` variants (default market, BR market, ats layout, txt layout) on every commit — a change should survive all of these, not just `make test`.

## Architecture

Everything funnels through `src/generate_cv.py`, a single-file generator (no package structure). It:

1. Loads `data/cv.json` and `config/market_rules.json`.
2. Resolves cross-references and derived fields **once**, before any template runs, so every layout reads the same plain, pre-resolved values instead of re-deriving them:
   - `experience[].company` (a `short_name` string) is resolved against the top-level `companies[]` list into the full company object, with `show_description` computed from `--company-descriptions` × `companies[].is_well_known`.
   - `languages[].level` (an integer `0`–`4`, market-independent) is translated to a display string (`descriptive` scale, or `cefr` for `CH`/`DE`) via `LANGUAGE_LEVEL_LABELS`.
   - `personal.nationality` is normalized from a string-or-list into a joined string.
   - `personal.photo` is resolved to an absolute path relative to `--data-dir` and dropped (warn or `--strict` fail) if missing.
3. Merges market rules: `config/market_rules.json`'s `default` object merged with the entry for `--market`, producing boolean flags (`show_photo`, `show_dob`, `show_address`, `show_nationality`) — read in templates as `market.get("flag", true)`. A missing rules file or unknown market degrades to showing everything rather than failing (unless `--strict`).
4. Applies `LAYOUT_RULE_OVERRIDES` **after** market rules, so a layout that structurally cannot render something (e.g. `ats`/`txt` never show a photo) always wins over what the market asks for. `--rules-override`/`RULES_OVERRIDE` is applied last of all, so an explicit CLI override always wins over both the market and the layout — same warn-or-fail convention as an unknown market for an unknown flag name or a non-boolean value.
5. Renders `<template-dir>/<layout>/cv.j2` with Jinja2 (`autoescape=False`; `trim_blocks`/`lstrip_blocks` only for `txt`, since LaTeX shrugs off stray whitespace but plain text doesn't).

### Layouts (`src/template/<layout>/`)

Each layout is a self-contained directory with a root `cv.j2` and its own `sections/*.j2` — same data, different rendering contract. `MARKET` (what's shown) and `LAYOUT` (how it's rendered) are fully orthogonal and compose freely.

- **`classic`** — the typographic CV using `res.cls`; margin section titles, right-aligned dates, photo where the market allows. Letter size (inherited from `res.cls`).
- **`ats`** — single-column, strictly linear order, no `\hfill`/tabulars, hyphenation off, full URLs as their own link text, conventional section names, `cmap` ToUnicode maps — built so a résumé-scanner's PDF text-layer extraction doesn't scramble it (classic's margin titles, `\hfill`-pushed dates, and hyphenation all break naively-extracted text). Never emits a photo. A4.
- **`txt`** — no `pdflatex` pass at all; what Jinja renders to `out/cv-txt.txt` *is* the artefact, for portals whose PDF extraction can't be trusted. Shares `ats`'s section conventions but drops all markup. Also collapses a remote role's location string (`"Remote (Brazil -- US)"` → `"Remote"`) via the `simplify_remote_location` filter, since an ATS location field can't parse the parenthetical.

Adding a layout = adding `src/template/<name>/cv.j2` + `sections/*.j2`; it's picked up by `make build LAYOUT=<name>` with no code change. A layout that needs to override a market rule declares it in `LAYOUT_RULE_OVERRIDES` in `generate_cv.py`.

### Tests (`tests/`)

`test_generate.py` is the bulk of coverage, organized by concern (`TestMarkets`, `TestLayouts`, `TestAtsLayoutIsParseable`, `TestLanguageLevels`, `TestCompanyResolution`, `TestLayoutRuleOverrides`, `TestWarnOrFail`, etc.) — grep for the relevant `class Test...` when touching a specific behavior. One test enforces that every flag declared in `market_rules.json` is actually read by some template, so a new market flag needs template wiring, not just a JSON entry. `test_addresses.py`, `test_dates.py`, and `test_latex_escape.py` cover the corresponding pure helper functions in isolation.

## Conventions

- Commits (this repo and `cv-data`) follow Conventional Commits: lowercase `type:` prefix (`feat:`, `fix:`, `chore:`, `style:`, `ci:`, `doc:` — note `doc:`, not `docs:`), no trailing period, one logical change per commit.
- Indentation is tabs (see `.editorconfig`), except YAML and Markdown (2 spaces).
