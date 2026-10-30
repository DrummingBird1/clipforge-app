## What changed and why

<!-- One change per pull request. Link the issue it closes, e.g. "Closes #12". -->

## How I checked it

<!-- The tests you added or ran, and anything you tried by hand in the app. -->

- [ ] `uv run ruff check .` passes
- [ ] `uv run pytest tests/ -m "not browser and not tk" -n auto --dist loadgroup` passes
- [ ] A test covers the change and fails without it
- [ ] New UI text has its English entry in `src/entrypoints/web/i18n/en.json`
- [ ] No personal data: nothing from `data/`, `workspace/`, `.env`, and no keys, tokens or private paths
