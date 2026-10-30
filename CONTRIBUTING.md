# Contributing to ClipForge

Thanks for taking the time to help. ClipForge is a local video studio for Windows: a Python backend (FastAPI + FFmpeg) with a browser UI. Bug reports, fixes, translations and feature ideas are all welcome.

## Before you start

- **Bugs and ideas:** open an issue first (there are templates for both), so we can agree on the approach before you write code.
- **Security problems:** do not open a public issue. See [SECURITY.md](SECURITY.md).
- **Be kind:** this project follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## Set up a development copy

Requirements:

- Windows 10 or 11.
- [uv](https://github.com/astral-sh/uv), which installs the Python version in `.python-version` for you.
- FFmpeg on `PATH`, or in `ffmpeg/bin/` next to the code. The code uses `libx264`, `vidstab`, `zscale` and `drawtext`, so a "full" or "essentials" GPL build is needed. An NVIDIA GPU is optional.

```bash
git clone https://github.com/DrummingBird1/clipforge-app.git
cd clipforge-app
uv sync
uv run python src/entrypoints/web_app.py
```

The server prints a link with an access token; open it in your browser. Your settings and data go to `data/` and your videos to `workspace/`, both ignored by git.

[docs/development.md](docs/development.md) describes the architecture and the folders in more detail.

## Checks to run before a pull request

```bash
uv run ruff check .
uv run mypy --platform win32
uv run pytest tests/ -m "not browser and not tk" -n auto --dist loadgroup
```

Tests that drive a real browser (Playwright + Microsoft Edge) and the Tk tests run separately:

```bash
uv run pytest tests/ -m browser -n 2 --dist loadgroup
uv run pytest tests/ -m tk -n auto --dist loadgroup
```

A few rules worth knowing (the test suite checks the first two):

- **Tests never touch your real data.** `tests/conftest.py` points `CLIPFORGE_DATA_DIR` and `CLIPFORGE_WORKSPACE_DIR` at temporary folders, and a network guard blocks outside requests. Use `tmp_path` for files.
- **No fixed waits in browser tests.** Wait for a condition, not for a number of milliseconds.
- **Paths under `data/`** come from `src/utils/shared/data_paths.py`, not from a hand-built `os.path.join`.

## The user interface and translations

The UI text in the source is Hebrew, and `src/entrypoints/web/i18n/en.json` holds the English version of every string. When you add or change UI text, add its English entry there; `tests/infra/test_i18n.py` and the browser tests catch a missing one.

## Pull requests

- Keep each pull request to one change, with a test that fails without it.
- Describe what changed and why, and how you checked it. The pull request template lists what to include.
- Don't commit anything from `data/`, `workspace/`, `.env` or your own media.
- New dependencies go through `uv add` so `pyproject.toml` and `uv.lock` stay in step. Mention the license of anything new; `THIRD_PARTY_NOTICES.md` lists what ships today.

By contributing you agree that your work is released under the project's [MIT license](LICENSE).
