# Contributing to TokenTelemetry

Thank you for your interest in contributing! TokenTelemetry is a 100% local, open-source observability dashboard for AI coding agents. All contributions are welcome.

## Getting Started

1. **Fork** the repo on GitHub
2. **Clone** your fork locally
   ```bash
   git clone https://github.com/YOUR_USERNAME/tokentelemetry.git
   cd tokentelemetry
   ```
3. **Create a branch** for your feature or fix
   ```bash
   git checkout -b feat/your-feature-name
   ```

## Development Setup

### Requirements
- Node.js 18+
- Python 3.9+
- git

### Run locally
```bash
# macOS / Linux
./start.sh

# Windows
start.bat

# Or directly
node bin/cli.js
```

This starts:
- **Frontend** (Next.js) at http://localhost:3000
- **Backend** (FastAPI) at http://127.0.0.1:8000

### Project Structure
```
backend/    # FastAPI app - reads agent log files
frontend/   # Next.js dashboard UI
bin/        # CLI entry point (cli.js)
website/    # tokentelemetry.com marketing site
install.sh  # One-line installer (macOS/Linux)
start.bat   # Windows starter
```

## How to Contribute

### Reporting Bugs
- Search existing issues first
- Use the **Bug Report** issue template
- Include your OS, Node.js version, Python version, and which agent you're using

### Suggesting Features
- Open a **Feature Request** issue
- Describe the use case clearly

### Adding a New Agent
Want to add support for a new coding agent? The backend reads log files from known directories. Add a new parser in `backend/` that:
1. Detects the agent's log directory
2. Parses session/token data into the common schema
3. Returns results via the FastAPI endpoint

### Submitting a Pull Request
1. Make your changes on a feature branch
2. Test that `./start.sh` runs without errors
3. Keep PRs focused — one feature or fix per PR
4. Write a clear PR description explaining what and why
5. Submit against the `main` branch

### Documentation — keep it minimal

**For most PRs (fixes, small features, chores, docs): you don't need to write any
formal docs.** Just explain *what* you changed and *why* in the PR description.
Maintainers handle the rest — adding it to the [Roadmap board](https://github.com/users/VasiHemanth/projects/1),
writing any decision record, and the `UPDATE.json` release note.

You also don't need to touch the board or `UPDATE.json` yourself.

### Adding a big feature? Include an ADR + design doc

A change is "big" if it does any of these:
- introduces a new module, storage layer, or external dependency;
- changes a data shape, API contract, or how an agent's data is read;
- has more than one reasonable approach, or is hard to reverse later.

If so, add two short markdown files **in the same PR as the code** so the *why* and
*how* travel with the change (this is how Kubernetes/Rust/Python-scale projects work):

1. **ADR** — copy [`docs/adr/0000-template.md`](docs/adr/0000-template.md) to
   `docs/adr/NNNN-short-title.md` (next number) and fill in:
   > **Context** — what problem/constraint forced this?
   > **Decision** — what are you doing? ("We will …")
   > **Alternatives considered** — what else you weighed, and why you rejected it.
   > **Consequences** — the upsides, the costs/limitations, and what would have to
   > change to undo it.

   Keep it to ~1 page. See [`docs/adr/README.md`](docs/adr/README.md).

2. **Design doc** — add `docs/design/<feature>.md` (the *what & how*: components,
   data shapes, key invariants). See [`docs/design/durable-history.md`](docs/design/durable-history.md)
   for the shape.

Not sure if your change counts as "big"? Open it without the docs and ask in the
PR — a maintainer will tell you, or write the ADR with you. Better to ship than to
stall on paperwork.

## Code Style
- **Python**: follow PEP8, use type hints where possible
- **TypeScript/JS**: follow the existing patterns in `frontend/`
- Keep things simple — this is a local tool, not a SaaS

## Questions?

Open a GitHub Discussion or file an issue. We're happy to help!

---

By contributing, you agree your contributions will be licensed under the MIT License.
