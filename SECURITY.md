# Security Policy

## Supported versions

TokenTelemetry has no tagged releases. The installers (`install.sh`,
`install.ps1`) clone the `main` branch, and the container images are built from
it, so the only supported version is the latest commit on `main`.

| Version                         | Supported |
| ------------------------------- | --------- |
| Latest `main`                   | Yes       |
| Older commits, forks, old images | No        |

Before reporting, please update (`git pull` in your checkout, or pull the
`latest` image) and confirm the problem is still there.

## Reporting a vulnerability

**Please do not open a public issue, discussion or pull request for a security
problem.**

Report it privately through GitHub:

1. Go to the repository's **Security** tab.
2. Choose **Report a vulnerability**
   (<https://github.com/VasiHemanth/tokentelemetry/security/advisories/new>).

This opens a private security advisory that only the maintainers and you can
see. If that button is not available to you, open a regular issue that says
only "I would like to report a security issue privately" with **no technical
details**, and a maintainer will set up a private channel.

### What to include

- The commit SHA you tested (`git rev-parse HEAD`) or the container image tag
  or digest.
- How you run the app: installer / `start.sh` / `start.bat`, Docker or Podman
  compose, or the desktop shell; and whether remote access is on (`--host`,
  `TT_HOST`, `--insecure-no-auth`).
- Operating system, Node.js version and Python version.
- What an attacker needs (same machine, same network, a web page the user
  visits, a crafted log file, a malicious repository) and what they gain.
- Steps to reproduce, ideally with a minimal proof of concept.
- Any logs or screenshots, **with secrets removed**: usernames in file paths,
  hostnames, access tokens, API keys, prompts and source code.

## What to expect

These are targets, not guarantees. The project is maintained by volunteers.

| Step                                              | Target                   |
| ------------------------------------------------- | ------------------------ |
| Acknowledge the report                            | within 3 business days   |
| First assessment (valid or not, rough severity)   | within 7 days            |
| Fix or mitigation on `main` for high or critical  | within 30 days           |
| Fix or mitigation for lower severity              | within 90 days           |

We will keep you updated in the advisory, credit you in it unless you ask us
not to, and publish the advisory once a fix is on `main`. Please give us a
reasonable chance to ship the fix before you disclose publicly.

## Scope

TokenTelemetry is a local-first dashboard. These notes say where its trust
boundaries are, so you can tell a vulnerability from intended behaviour.

### Local by default

- The backend (port 18000) and the dashboard (port 13000) listen on loopback
  only by default. Local requests are not authenticated: any process running
  as your user on the same machine can already read the same log files.
- In scope: anything that lets a party who is **not** a local process reach the
  local API or its data. Examples: a web page in the user's browser reading the
  API (CORS or DNS-rebinding problems), or a default that binds to a
  non-loopback address.

### Remote-access token mode

- Starting with a non-loopback `--host` / `TT_HOST` turns on token
  authentication. A token (`TT_AUTH_TOKEN`) is generated and printed once at
  startup, and every non-loopback request must carry it. Loopback stays exempt.
  In containers the backend never sees a loopback client, so once a token is
  set every request needs it.
- The token is the security boundary. CORS is not.
- In scope: bypassing the token, any route reachable remotely without it,
  token leaks (in logs, URLs sent to third parties, error messages, telemetry),
  weak token generation, and anything that makes the remote surface wider than
  the user asked for.
- Out of scope: exposure caused by running with `--insecure-no-auth`,
  publishing the ports on `0.0.0.0` without a token, or sharing the token.
  Those are explicit opt-outs.
- The token is sent as a bearer header over plain HTTP. Use remote mode on a
  network you trust or behind a tunnel that adds TLS (a tailnet, a reverse
  proxy). The lack of built-in TLS is a known limitation, not a vulnerability.

### Agent logs contain prompts and code

- The backend reads session logs written by AI coding agents (Claude Code,
  Codex, Gemini CLI and others). Those logs contain prompts, source code, file
  paths, command output, and sometimes secrets that were pasted into a session.
  Anything that discloses them is treated as high severity.
- Log content is untrusted input. A log can carry text that came from a
  malicious repository, web page or tool result. In scope: path traversal
  through session or project identifiers, script injection in the dashboard
  from rendered log content (XSS), command or argument injection, unsafe
  deserialisation, and reads or writes outside the agent log directories and
  the TokenTelemetry data directory.
- Agent log directories are read, not written (the container setup mounts them
  read-only). A write to an agent's own files that the user did not ask for is
  in scope.
- Optional session summaries send session content to the summariser the user
  configured (a local CLI, Ollama, or an OpenAI-compatible endpoint). Content
  going anywhere the user did not configure is in scope.

### Outbound calls

- There are two documented outbound calls: an update check against GitHub, and
  anonymous, content-free product telemetry (on by default; turn it off in
  Settings or with `DO_NOT_TRACK=1` / `TT_NO_TELEMETRY=1`). See the README
  section "Privacy & outbound calls".
- In scope: any prompt, code, path, cost, token or stable identifier leaving
  the machine through these calls, or any other undocumented outbound call.

### Install and supply chain

- In scope: problems in `install.sh`, `install.ps1`, `start.sh`, `start.bat`,
  `bin/cli.js`, the desktop shell in `desktop/`, the container images published
  to `ghcr.io/vasihemanth/tokentelemetry-*`, and the GitHub Actions workflows
  in this repository.
- Vulnerabilities in third-party dependencies are welcome when they are
  reachable in TokenTelemetry. Please say how.

### Out of scope

- Attacks that need an attacker who already runs code as the same OS user, or
  who has physical access to an unlocked machine.
- Problems in the AI agents themselves or in their log formats. Report those
  to the agent's vendor.
- The marketing site (`website/`) beyond what could harm its visitors.
- Denial of service against your own local instance.
- Automated scanner output with no demonstrated impact.
