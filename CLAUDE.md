# Orithena Pulse Git Rules

These rules apply to every Claude Code invocation in this workspace. No exceptions.

## Branch Policy

Check the `ORITHENA_AGENT_RUN` environment variable to determine the correct workflow:

**If `ORITHENA_AGENT_RUN` is set** (autonomous agent run):
- Use `scout/<name>` branches and PRs — never push to main.

**If `ORITHENA_AGENT_RUN` is not set** (human interactive session):
- Push directly to main.

Always pull latest main before starting: `git pull origin main`.

## Commit and Push

- Commit after every meaningful unit of work.
- Push after every commit: `git push origin HEAD`.
- Write clear commit messages that describe *what changed and why*.

## Forbidden

- `git push --force` — never, on any branch, for any reason.
- `git reset --hard` — never discard work.
