# Orithena Pulse — Content Intelligence Pipeline

Content intelligence pipeline. Scrapes domain-specific sources, scores and curates content, builds a site, and generates intelligence reports.

For system-wide context, see `../CLAUDE.md`. For the org mission, see `../orithena-org/NORTH_STAR.md`.

## Key Commands

| Command | What it does |
|---|---|
| `make run` | Full pipeline (scrape -> curate -> build -> intel) |
| `make scrape DOMAIN=x` | Scrape sources for a domain |
| `make curate` | Score and filter cached data |
| `make build` | Build site from scored data |
| `make intel` | Generate intelligence reports |

## Git Rules

Check `ORITHENA_AGENT_RUN` to determine workflow:

- **Agent run** (`ORITHENA_AGENT_RUN` is set): use `scout/<name>` branches and PRs — never push to main
- **Human session** (`ORITHENA_AGENT_RUN` is not set): push directly to main

Always pull latest before starting: `git pull origin main`.
Commit after every meaningful unit of work. Push after every commit.

### Forbidden

- `git push --force` — never, on any branch, for any reason
- `git reset --hard` — never discard work
