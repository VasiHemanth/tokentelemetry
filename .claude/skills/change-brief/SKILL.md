---
name: change-brief
description: Explain a change that already exists — a pull request, a merged commit, a closed issue's fix, or an uncommitted diff — in terms of the FEATURE it touches and how someone actually uses that feature, then the bug or gap it addresses. Always states who wrote it (Claude in an earlier session, an outside contributor, or the maintainer) before explaining anything else. Use when the user pastes a PR link or number, says explain this PR / what does this PR do / what is 331 / what's this commit / explain these changes / what did you change, asks "in simple words" or "explain the scenario", or wants to understand work they did not write themselves. Read-only: it reads the diff, the surrounding code and git history, and never runs the app, never checks out a branch, never edits. NOT for deciding whether to build something not yet written (use /issue-brief) and NOT for finding defects (use /code-review).
---

# change-brief — explain a change that already exists

`/issue-brief` explains something **not yet built**, to decide whether to build
it. This skill explains something **already written**, so the reader
understands what it does and whether to merge or trust it.

The reader did not write this code. Often nobody they can ask wrote it — it may
be an outside contributor's PR, or something Claude produced in a session they
have since forgotten. Assume no memory of the change and no file layout in
their head.

## 1. Resolve the target

| They said | Fetch with |
|---|---|
| PR number or URL | `gh pr view <n> --json number,title,author,body,files,additions,deletions,mergeable,mergeStateStatus,commits` |
| "what is 331" (bare number) | Try `gh pr view <n>` first; fall back to `gh issue view <n>` |
| commit SHA | `git show --stat <sha>` |
| "these changes" / "what did you change" | `git status --short` and `git diff` (plus `git diff --staged`) |
| merged issue | `gh issue view <n>`, then find the PR that closed it |

Get the **real** diff, not the description. A PR opened weeks ago is measured
against today's base:

```bash
git fetch origin main pull/<n>/head:pr<n>
git diff origin/main...pr<n> --stat
```

A `git diff main...` against a stale local `main` reports hundreds of unrelated
files. If the stat looks absurdly large for the PR's description, that is the
cause — fetch `origin/main` and re-diff before believing it.

## 2. Establish authorship first — this is not optional

The user asked for this explicitly: **say who wrote it before explaining what
it does.** They need to know whether they are reading their own past decision,
a contributor's proposal, or Claude's output from a session they don't recall.

- **The change itself:** `gh pr view <n> --json author`, or
  `git log -1 --format='%an <%ae>' <sha>`.
- **Claude's fingerprint:** commits Claude wrote carry a
  `Co-Authored-By: Claude` trailer and a `Generated with Claude Code` line.
  `git log --format='%H %an %s' -- <file> | head` shows who has been touching
  the area.
- **The underlying feature is usually older than the change.** A PR fixing a
  bug in a feature did not create that feature. Attribute them separately:
  who wrote the feature, who wrote this fix.

State it plainly and without hedging: "Not me — this is <contributor>'s PR. The
feature it touches is pre-existing project code, yours." If Claude did write
it, say so in the same breath, and in which session or PR.

Never claim authorship you have not checked, and never let "we" blur it.

## 3. Answer in this order

1. **Who wrote what.** Two or three lines. The change, the feature it touches,
   and — if relevant — which parts Claude produced.
2. **The feature, and how someone actually uses it.** Before any bug: what is
   this capability *for*? Name the env var, the button, the endpoint, with a
   `file.py:line` anchor. Give the real reason a person reaches for it ("your
   home drive is small and you want the store on an external SSD"), not a
   restatement of its name.
3. **The scenario, walked.** One realistic setup, numbered, in the order the
   person experiences it. What they do, what they expect, what they get.
   Real paths, real ports, real variable names. Say what they *see* before why
   it happens.
4. **Why it happens.** The mechanism, now that the symptom is concrete, with
   `file:line` anchors so every claim can be checked.
5. **What the change does about it** — including **the simpler fix it passed
   over, and why**. There is almost always an obvious cheaper repair; naming it
   and saying why the author went further is what turns "here is a diff" into
   "here is a judgement I can agree or disagree with". For #331: you could tell
   the one messy test to clean up after itself, but that leaves the next
   contributor free to make the identical mistake. Also say what the change
   deliberately leaves alone.
6. **Who it actually affects** — see §4, never skip this.
7. **Traps**, if any: version bumps that force a rescan, migrations, security
   gates, other open PRs on the same files, claims in the PR body that the diff
   does not support.
8. **A verdict and one next step.**

Steps 4, 5 and 7 collapse to a sentence each when the change is small. Steps 1,
2, 3 and 6 are never skipped.

## 4. The blast-radius honesty check

**Every brief must say who is actually affected**, and must not let a
"user scenario" framing imply an end user is hit when they are not.

Sort the change into one of these and say which, in plain words:

- **End users** — someone running the app sees different behaviour.
- **Contributors only** — test-suite, CI, lint, build tooling. The shipped app
  is unchanged.
- **Maintainer only** — release scripts, repo automation.
- **Nobody yet** — dead code, or gated behind a flag nobody has on.

When the user's own framing assumes an end-user impact that does not exist,
correct it directly rather than playing along. A test-isolation bug is a real
bug worth fixing, and it is *still* invisible to everyone using the dashboard;
both halves of that sentence have to be said.

## 5. Prose rules

Inherits `/issue-brief`'s rules — symptom before mechanism, expand every
acronym once, cite `file:line` instead of pasting code, one verdict, no hedging
stacks — plus:

- **Feature before defect.** A bug is only comprehensible once the reader knows
  what was supposed to happen. Never open with the failure.
- **Give the moving parts names the reader can hold.** Two env vars with a
  precedence rule become "the Boss and the Assistant — if the app sees both it
  always obeys the Boss". A test that leaks state is "the messy roommate". A
  snapshot-and-restore fixture "photographs the environment before each test and
  puts it back afterwards". Introduce the name once, then use it consistently
  and keep the real identifier beside it on first use, so the reader can still
  grep for `TOKENTELEMETRY_DATA_DIR`. One analogy per brief, carried all the way
  through — a pile of competing metaphors is worse than none, and an analogy
  that has to be stretched to fit is a sign the mechanism isn't understood yet.
- **Signpost with claims, not labels.** Headings should say something: "Why you
  don't need to worry" beats "Impact"; "The messy roommate" beats "Root cause".
  A reader skimming only the headings should still get the story.
- **"In simple words" means fewer clauses, not fewer facts.** Strip jargon and
  shorten sentences; keep the specific variable names, numbers and paths. A
  simplified explanation that drops the mechanism is not simpler, it is emptier.
- **The interesting sentence is usually the interaction**, not either part. In
  PR #331 the leak matters *because* `TOKENTELEMETRY_DATA_DIR` correctly
  outranks `TOKENTELEMETRY_HOME` — the feature working as designed is what
  makes the bug bite.
- **Quote the PR body only to disagree with it.** Otherwise describe the diff.
  Descriptions drift from what was actually committed; the diff does not.

## 6. Worked example (PR #331, test env leak)

> **Who wrote it.** Not me — slmingol's PR. The data-folder feature it touches
> is pre-existing project code, yours. Nothing of mine is in this one.
>
> **The chain of command.** `backend/tt_paths.py:60` decides where
> TokenTelemetry keeps its state, and it takes orders from two variables. The
> Boss is `TOKENTELEMETRY_DATA_DIR`, used verbatim. The Assistant is
> `TOKENTELEMETRY_HOME`, with `.tokentelemetry` appended. If both are set the
> app always obeys the Boss and ignores the Assistant; with neither, it falls
> back to `~/.tokentelemetry`. You promote the Boss when your home drive is
> small, or `~` is roaming-profile synced and you don't want a growing SQLite
> file in it — `export TOKENTELEMETRY_DATA_DIR=/Volumes/ext/tt-data` moves the
> whole store.
>
> **The messy roommate.** You've moved your data folder. You pull new code and
> run the tests.
> 1. 22 tests fail.
> 2. They assert values you can see sitting in the config files they just wrote.
> 3. Nothing in the app is actually broken.
>
> `test_agent_retention.py` needed a scratch folder, so it set the Boss to a
> temp directory — and never put it back. Every later test politely sets up its
> own sandbox using the Assistant. The app does exactly what it is told: it sees
> the Boss still standing there from an hour ago and ignores the Assistant. So
> those tests write to one folder and read from a different, empty one.
>
> **Why you don't need to worry.** Contributors only. The app is untouched —
> your relocated folder works fine at runtime — and the bug exists *because*
> the precedence rule works correctly. It needs many app states in one process
> to bite, which only a test suite does.
>
> **The cheaper fix it passed over.** You could tell that one test to clean up
> after itself. slmingol didn't, because it leaves the next contributor free to
> repeat the mistake. Instead `backend/conftest.py` adds an autouse fixture that
> photographs both variables before every test and restores them after, so no
> test can leak into another again.

Note what the example does. Authorship lands before anything else. One analogy
— the chain of command — is introduced early and carried through "obeys the
Boss", with the real variable names kept beside it so the reader can still grep.
Headings make claims. The blast-radius paragraph refuses the implication that a
user is hurt, and gives the reason the bug is invisible rather than asserting
it. The rejected cheaper fix turns the diff into a judgement.

## 7. Don't

- Don't run the app, start servers, check out branches, or edit files. This
  skill is read-only and ends with the working tree untouched.
- Don't review for defects, suggest improvements, or rank findings.
  `/code-review` does that.
- Don't use it to decide whether to build something unwritten. `/issue-brief`
  does that.
- Don't repeat the PR body back. If the diff and the body disagree, the diff
  wins and the disagreement is worth reporting.
- Don't put machine-specific paths, usernames or hostnames in the output. This
  repo is public; sanitise as you copy (`/Users/dev/...`, `C:\Users\dev\...`).
