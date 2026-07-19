# Agent instructions — GitHub Issues (issuebeam)

Use this file with **any AI coding agent** on **Windows, macOS, or Linux** that can read repository instructions and run shell commands (Cursor, Claude Code, GitHub Copilot, Windsurf, Cline, Gemini CLI, Codex CLI, Continue, Aider, custom bots).

## Source of truth

For **bugs**, **enhancements**, and **sprint tasks**, prefer **GitHub Issues** via:

```bash
python scripts/github_issue.py <command>
```

**Run the script yourself.** Do not ask the user to paste commands manually if the token is configured.

Repository slug: `tracker/github_repo`, `.env` (`GITHUB_REPO`), or environment variable.

Token resolution order:
1. `.env` at repo root (`GITHUB_TOKEN=...`) — **preferred in igedge**
2. `GITHUB_TOKEN` in the process environment (session / inherited Windows var)
3. `.secrets/github_token` (gitignored)
4. **Windows only:** user environment variables (registry — fallback)

Full guides: [issuebeam.github.io/docs](https://issuebeam.github.io/docs/) (EN) · [issuebeam.github.io/docs/it](https://issuebeam.github.io/docs/it/) (IT)

## When the user reports a problem or asks for work

1. **Check** for an existing issue (`list` or search by title / Legacy ID).
2. **Create** an issue with `create` (or import from manifest for known legacy items).
3. **Do not** create scattered markdown files only to track open bugs — use GitHub Issues.
4. Detailed plans in `docs/` stay as **specification**; operational status lives on GitHub.

## Commits and PRs

Reference the issue in commits that fix it:

```
Fixes #123
```

Or `Closes #123` / `Refs #123` for partial work.

## Label conventions

| Label | Use |
|-------|-----|
| `bug` | Wrong behavior or regression |
| `enhancement` | Product improvement, not a bug |
| `task` | Planned sprint work |
| `documentation` | Docs only |
| `priority-high` / `priority-medium` / `priority-low` | Urgency |
| `area-frontend` | UI, UX, client |
| `area-backend` | API, services, server logic |
| `area-infra` | CI/CD, Docker, deploy |
| `area-docs` | README, guides, site |
| `imported` | Migrated from a legacy local tracker |

For imported issues, include **`Legacy ID:`** in the body (e.g. `BUG-001`) and a link to the local markdown file.

## Useful commands

```bash
python scripts/github_issue.py labels --apply
python scripts/github_issue.py import --dry-run
python scripts/github_issue.py import --apply
python scripts/github_issue.py create "Title" --labels bug,area-frontend --body "..."
python scripts/github_issue.py list
python scripts/github_issue.py comment N --body "..."
python scripts/github_issue.py close N
python scripts/github_issue.py close-batch 1 2 3 --reason "..."
```

## Natural language (IT / EN)

| User says | Agent does |
|-----------|------------|
| *«Apri issue per…»* / *"Open an issue for…"* | `create` with appropriate labels |
| *«Traccia bug…»* / *"Track this bug…"* | check duplicates, then `create` |
| *«Elenca le issue aperte»* / *"List open issues"* | `list` |
| *«Commenta issue #N…»* | `comment N` |
| *«Chiudi issue #N»* | `close N` |
