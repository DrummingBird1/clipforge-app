# ClipForge

Single source of truth for any AI agent working in this repository (Claude, Codex, Copilot, Cursor, Gemini, ChatGPT, Grok, OpenCode). `CLAUDE.md` only imports this file. Keep it self-contained: do not point to files outside the repository.

<!-- BEGIN core-rules v1 (generated from the shared core-rules.md; do not edit by hand) -->
## Core rules (apply to every agent)

- Read this file first. If `HANDOFF.local.md` exists next to it, read it too (local only, not in git).
- Never push, force-push or create remotes unless the owner explicitly asks. Work on a branch named `agent/<tool>-<topic>`; merge to `main` only through a pull request.
- Never commit or print secrets (`.env`, keys, tokens). Keep personal paths, emails and private repo names out of tracked files.
- Package managers: JavaScript uses `pnpm`, Python uses `uv`. Do not switch without being asked.
- Dev servers listen on `127.0.0.1` only, unless the owner asks otherwise.
- Do not delete or overwrite user data. Move it to an archive folder or ask first, and do a dry run before bulk changes.
- Make the smallest change that solves the task. Run this project's own check and test commands (see Run and Test in this file) and say what you ran and what you could not verify.
- If you have no access to the repository (a chat-only agent), return a unified diff or complete files, and list what the owner should verify.
<!-- END core-rules -->

## Purpose

ClipForge is a video studio for gameplay clips and data videos that runs on the user's own Windows PC. It trims, crops, brands and captions clips, exports Shorts, TikTok, Instagram and YouTube versions in one run, and turns tables into animated chart videos. Local first: nothing is uploaded unless the user sets up an optional feature (YouTube upload, Discord bot, Twitch clip import, OBS replay watcher, AI titles). License: MIT.

## Type

- Python application for Windows 10/11 (Python 3.11 or newer, version pinned in `.python-version`), managed with `uv` (`pyproject.toml`, `uv.lock`, no build backend).
- Four independent processes that talk only through files on disk: the browser studio (`src/entrypoints/web_app.py`, FastAPI + a browser UI), the desktop control center (`src/entrypoints/gui_manager.pyw`, customtkinter), the Discord bot (`src/entrypoints/main.py`) and a read-only status page (`src/entrypoints/web_dashboard.py`).
- Layout: `src/` (cogs, dataviz engine, entrypoints, templates, ui, utils), `my_scripts/` (automation scripts run as subprocesses), `tests/`, `dev/` (build, export and docs tools), `docs/` (user docs and `docs/development.md`), `assets/`.
- Needs FFmpeg on `PATH` or in `ffmpeg/bin/` (the code uses `libx264`, `vidstab`, `zscale`, `drawtext`, so a "full" or "essentials" GPL build). An NVIDIA GPU is optional (NVENC).
- `docs/development.md` describes the architecture, the scripts and the release flow in detail. Read the section you need before changing that area.

## Run

```bash
uv sync
uv run python src/entrypoints/web_app.py
```

The server prints a link with an access token; open it in the browser. Settings and data go to `data/` and videos to `workspace/`, both ignored by git. Other entry points are listed in `docs/development.md` ("Usage"). Build the portable download with `uv run python dev/build_portable.py` (keep the clone at a short path).

## Test

```bash
uv run ruff check .
uv run mypy --platform win32
uv run pytest tests/ -m "not browser and not tk" -n auto --dist loadgroup
uv run pytest tests/ -m browser -n 2 --dist loadgroup
uv run pytest tests/ -m tk -n auto --dist loadgroup
```

The browser tests need Playwright and Microsoft Edge. CI fails if coverage drops below the floor in `pyproject.toml`. Say which of these you ran and which you could not.

## Rules

- The owner works in Hebrew: reply in Hebrew unless asked otherwise. The UI text in the source is Hebrew; every string also needs its English entry in `src/entrypoints/web/i18n/en.json` (`tests/infra/test_i18n.py` and the browser tests catch a missing one). Code, docs and commit messages are in English.
- Tests never touch real data: `tests/conftest.py` points `CLIPFORGE_DATA_DIR` and `CLIPFORGE_WORKSPACE_DIR` at temporary folders and a network guard blocks outside requests. Use `tmp_path` for files.
- No fixed waits in browser tests: wait for a condition, not for a number of milliseconds.
- Paths under `data/` come from `src/utils/shared/data_paths.py`, not from a hand-built `os.path.join`.
- Scripts that render run through `src/utils/shared/worker.py` and the cross-process render lock (`render_lock.py`); do not spawn script subprocesses any other way.
- Add dependencies with `uv add` so `pyproject.toml` and `uv.lock` stay in step, and note the license of anything new in `THIRD_PARTY_NOTICES.md`.
- Keep the app version in step in `pyproject.toml`, `src/utils/shared/version.py` and `CHANGELOG.md` (a test checks it).
- One concern per pull request, with a test that fails without the change. Branches `feat/...` or `fix/...`; `main` changes only through a pull request.

## Do not

- Do not commit `.env`, keys, tokens, `client_secret.json`, `data/`, `workspace/` or your own media.
- Do not add large binaries (archives, video, audio, executables) to git; decide on LFS or external storage first.
- Do not push or create a remote without the owner's explicit approval.
- Do not hide a failing check by changing what it compares against.

## State

- Public repository, default branch `main`, MIT license. It is developed here directly: everything pushed is public, so run `uv run python dev/leak_check.py` before a push (see "Releasing a new version" in `docs/development.md`). Releases are tag-driven and checked by `.github/workflows/release.yml`. Do not tag or publish a release without the owner's go-ahead.
- The Scoop bucket for this app lives in a separate repository.

## Handoff

- Recent changes, unpushed work and open items are kept in `HANDOFF.local.md` next to this file. It is git-excluded and exists only on the owner's machine: read it when it is there, and do not copy its content into tracked files.
