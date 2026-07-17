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
| `TARGET` | `cv` or `cv-$(MARKET)` | Output base name — market-specific builds don't overwrite each other |
| `OUTDIR` | `out` | Output directory |
| `STRICT` | `0` | `1` fails on unknown market or missing files instead of degrading gracefully |
| `COMMIT_SHA` | `git rev-parse` | Stamp embedded in the PDF; CI can inject its own |

`make prod-build` is the CI entry point: it syncs dependencies with `uv sync --frozen` (the lockfile is authoritative) and builds with `STRICT=1`. Typical pipeline invocation:

```sh
make prod-build DATA_DIR=/path/to/cv-data MARKET=CH
```

## Future
I want to have various CVs that I can tailor to a specific need or market. For example, in Switzerland, CVs with photos are well-received—on the other hand, in Brazil, this is frowned upon. Adjusting a CV for a specific role —for example, by changing some wording or emphasizing some skill set—is also something that I want to look further. Also, exploring LLMs to rephrase some wording for some specific context might sound like a good idea.

## License
This project is licensed under the [MIT License](https://license.md/licenses/mit-license/).

