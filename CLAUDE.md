# Orithena Pulse — Content Intelligence Pipeline

Content intelligence pipeline. GitHub Pages shell — templates, static assets, and output live here. Pipeline code lives in `orithena-org/content/`.

For system-wide context, see `../CLAUDE.md`. For the org mission, see `../orithena-org/NORTH_STAR.md`.

## Key Commands

| Command | What it does |
|---|---|
| `make run` | Full pipeline (scrape + curate + build + post) |
| `make scrape` | Scrape sources only |
| `make build` | Build site from cached data |
| `make demo` | Run with sample data (no network) |

## Architecture

This repo is a **product shell**. All pipeline logic is in `orithena-org/content/`:
- Adapters, scoring, dedup → `content/adapters/`, `content/curation/`
- Intelligence reports, digest → `content/intelligence/`
- Discord posting → `content/discord/`
- Site builder → `content/sitegen/build.py`
- Domain config → `content/domains/pulse.yaml`

This repo contains only:
- `sitegen/templates/` — Jinja2 templates (product identity)
- `sitegen/static/` — CSS, JS
- `output/` — Generated site (gitignored)
- `Makefile` — Delegates to unified pipeline

## Git Rules

Check `ORITHENA_AGENT_RUN` to determine workflow:

- **Agent run** (`ORITHENA_AGENT_RUN` is set): use `scout/<name>` branches and PRs — never push to main
- **Human session** (`ORITHENA_AGENT_RUN` is not set): push directly to main

### Forbidden

- `git push --force` — never, on any branch, for any reason
- `git reset --hard` — never discard work
