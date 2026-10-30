# Changelog

What changed in each ClipForge release, by topic. Dates are release dates (YYYY-MM-DD).

## 1.1.3 - 2026-10-30

### Fixes
- English UI: no flash of Hebrew before the language is applied on load.
- English UI: the time left in a run, the built-in style names and the data-video editor's default labels are translated.
- Run notifications show a readable summary (created, failed, time, size) in the install's language, with no file paths.
- Marking notifications as read no longer stalls the server while the database is busy.

### Public release
- Install with Scoop (`scoop bucket add clipforge https://github.com/DrummingBird1/scoop-clipforge`).
- A documentation site (goes live with GitHub Pages), a roadmap, and a script for the demo video.
- CI, CodeQL and Scorecard workflows, and SHA-pinned actions, ready for the public repository.

## 1.1.2 - 2026-10-30

### Public release
- README: a demo GIF, badges and a Troubleshooting section, in English and Hebrew.
- `SHA256SUMS.txt` next to every portable zip, and the zip's hash in the release notes.
- A smaller portable package: about 133MB less unpacked (only the YouTube discovery documents, no library tests or type
  stubs).
- The tray menu, the launcher's error message and Windows notifications follow the install language.

### Fixes
- The "another render is running" badge clears when the render lock is released.

## 1.1.1 - 2026-10-30

### Security
- filelock 4.2.4 (from 4.1.0) and setuptools 84.2.1 (from 84.0.0) for open security advisories; the portable zip now
  ships filelock 4.2.4.

### Public release
- The public repository no longer gets a Dependabot configuration; dependency updates come with each release.

## 1.1.0 - 2026-10-30

### Public release
- English UI by default on a new install; existing installs keep Hebrew. Texts the server makes (default titles, Wrapped
  cards, device names, new data-video episodes) follow the install's language.
- "Rocket Shorts" is now the Shorts publisher: a configurable file-name prefix and game, output at the source resolution
  or 4K, an optional logo, and CPU encoding (libx264) by default.
- Neutral defaults for new installs: the RSS keyword filter, the Steam store region and language, and the Docker
  container are settings; the daily maintenance and digest run on local time; the disk scanner starts in the home
  folder.
- The shared database is now `clipforge_data.db`, renamed automatically on first start, with a backup first.
- A new install starts in the topic folders, and the web app can be installed as a PWA.
- A portable Windows zip with a pinned FFmpeg build (GPLv3 essentials), and an update check against the public
  repository's releases.
- Community files: a contributing guide, a security policy, and issue and pull request templates.

### Graph editor (data-to-video)
- New episodes from several data files at once, or from a ready episode folder; add, remove and edit data sources later,
  including a data grid that saves a new file and weights files.
- Level sources (values that are levels, not amounts to add up), series in different units on a second y-axis or as
  small multiples, and a fill for sparse data (steps or a straight line).
- A smart editor: point it at a data folder and get an episode draft, with column roles, units, chart choice, story,
  events, titles, a YouTube package and a thumbnail - each choice with a reason and a confidence. It also watches a folder
  and learns preferences per channel kit.
- A data-source catalog (CBS, World Bank, OECD), downloaded only on request.
- Story tools: a wizard (race, trend, compare two, before/after), annotations on the chart, focus mode, a narration
  script draft, a fact check of on-screen numbers against their source rows, and a readability check per target.
- A live animated preview, version history and named variants per episode, a trash with restore, and an image report
  for a whole folder of episodes.
- Simple, regular and expert levels, first-run onboarding, one tools menu and one settings dialog.
- Rendering: an interrupted full render resumes from the last finished piece, a time estimate for automatic Shorts, and
  a clear error when a drawing worker dies. Many reading, date and drawing fixes from a full bug hunt.

### Studio (video editor)
- Usability fixes from a full walkthrough: a folder picker with recent folders, where each output was saved, logo
  overlap warnings and box-based safe zones, a timeline docked at the bottom, the output's loudness (LUFS), and new
  projects from a template.

### Web app and phone
- Outputs screen: every video the tools produced, in one place, and publishing from any output.
- Notification center: what finished, stopped or failed, in one list.
- Phone screen: what is running, the queue, approvals and run-again; phone access over Tailscale (opt in), and pairing
  a device once with its own token.
- One export folder for every tool's final outputs, or a folder per tool.
- The end of a run (history, webhook, backup, night mode) happens even with no browser tab open, and night mode waits
  for the end of the queue before shutting down.
- An optional Windows wake timer for the next scheduled task.

### Data and storage
- Outputs are organized by tool under `workspace/<tool>/`, with a migration script for existing outputs.
- `data/` is organized by topic (`settings/`, `security/`, `bot/`, `studio/`, `dataviz/`, `cache/`), with a migration
  script that backs up first and rolls back on failure.

### Security and dependencies
- Pillow 13 and certifi 2026.10.19 for open security alerts; Python 3.11 or newer.
- Tests can no longer reach the network outside localhost.

### Reliability
- The render lock survives a reader on Windows and a lock file being deleted.
- Fixes for the NVENC probe, Discord approval retries, Docker status timeouts and Hebrew number labels.

### Development
- `src/utils/` split into `video/`, `media/`, `bot/` and `shared/`; tests split by area; the web server split into
  smaller modules; developer tools moved to `dev/`.
- Faster test runs (each worker gets its own data and workspace folders).
- MIT license and third-party notices.

## 1.0.0 - 2026-10-16

The first release: the Discord bot, the desktop control center and the browser app, the studio (video editor), the
graph editor, timelapses and highlight reels, Shorts publishing, scheduling and backups.
