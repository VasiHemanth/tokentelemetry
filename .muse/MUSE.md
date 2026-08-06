# Muse Code Integration

Muse Code operates slightly differently from other coding agents like Claude or Grok:
1. It uses `AGENTS.md` at the project root for project rules.
2. It reuses `.claude/skills` directory when run with `--trust-workspace`.
3. It stores sessions in `~/.local/share/muse` globally rather than a local `.muse/sessions` directory.

We have included this `.muse` folder to maintain the pattern established by `.claude`, `.grok`, `.pi`, and `.smallcode`, but the primary configuration file that Muse Code reads natively is `AGENTS.md`.

## Running Muse Code

To run Muse Code in this workspace with access to project skills and rules:

```bash
muse --trust-workspace
```
