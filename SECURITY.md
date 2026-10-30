# Security policy

## Supported versions

Security fixes go into the latest release only. Please update to the newest version on the [Releases page](https://github.com/DrummingBird1/clipforge-app/releases/latest) before reporting.

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

Report it privately through GitHub instead: on the repository's **Security** tab, choose **Report a vulnerability**. Include:

- the version (shown in the update check, or in `portable.json` in the portable package),
- what an attacker can do and from where (the same PC, the local network, or the internet),
- the steps to reproduce it.

You should get an answer within a week. Once a fix is released, the advisory is published with credit to you, unless you prefer to stay anonymous.

## How ClipForge is meant to be exposed

Knowing the intended setup helps judge whether something is a vulnerability:

- The web app listens on `127.0.0.1` by default, and every request needs the access token that is printed at startup, or a cookie set from it.
- `--lan` mode, the Tailscale address and paired devices (phone, NAS) are opt-in. Paired devices get their own token that can be revoked, and some actions stay limited to the PC itself.
- API keys and tokens (YouTube, Discord, Gemini and others) are stored in the Windows Credential Manager or in `.env`, never in the repository.
- ClipForge is not designed to be exposed directly to the internet. Use a VPN such as Tailscale for remote access.
