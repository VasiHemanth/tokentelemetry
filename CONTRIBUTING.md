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

## Code Style
- **Python**: follow PEP8, use type hints where possible
- **TypeScript/JS**: follow the existing patterns in `frontend/`
- Keep things simple — this is a local tool, not a SaaS

## Questions?

Open a GitHub Discussion or file an issue. We're happy to help!

---

By contributing, you agree your contributions will be licensed under the MIT License.
