# Roadmap

What we'd like ClipForge to do next, by area. Nothing here is a promise or has a date; plans change with what people need. Shipped changes are listed in [CHANGELOG.md](CHANGELOG.md).

## Where we are: 2.0.1

ClipForge 2.0.1 is the current release (2026-11-17). It added the Recording screen (screen, PC games and consoles through a capture card, a replay buffer, OBS control), importing clips from other recorders, long recording to Shorts with zoom, slow motion and face tracking, and public CI. Everything shipped is in [CHANGELOG.md](CHANGELOG.md).

## Next: 2.0.x

- Testing recording and encoding on more hardware: other capture cards and AMD graphics cards.
- Uploading to TikTok and Instagram through their APIs (today ClipForge prepares an upload package for them).
- A steadier browser test (the focus ring one), and working through the open CodeQL alerts.

## Studio

- A vertical crop that follows the action (scene-aware reframe).
- Keyword highlighting in captions, and automatic chapters.
- Automatic blurring of faces, usernames and chat on screen.

## Data videos

- A rotating treemap.
- Bubbles on a map.
- A narration script for each event.
- Comparing two versions of the same data.

## Performance

- Color correction on the GPU.
- 10-bit decoding on the GPU.

## Distribution

- Installing with winget: the package is submitted and waiting for review (Scoop works already, see the README).
- Done: public CI, CodeQL code scanning, releases built and attested by CI from a tag, and a documentation site.

## Get involved

- Ideas and votes: [Discussions → Ideas](https://github.com/DrummingBird1/clipforge-app/discussions/categories/ideas).
- Want to help? Look for issues labeled [good first issue](https://github.com/DrummingBird1/clipforge-app/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22), and see [CONTRIBUTING.md](CONTRIBUTING.md) to get started.
