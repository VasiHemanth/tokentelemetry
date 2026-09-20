---
name: change-brief
description: Explain a change that already exists — a pull request, a merged commit, a closed issue's fix, or an uncommitted diff — in terms of the FEATURE it touches and how someone actually uses that feature, then the bug or gap it addresses. Always states who wrote it (Claude in an earlier session, an outside contributor, or the maintainer), right after the opening model and before any mechanism. Use when the user pastes a PR link or number, says explain this PR / what does this PR do / what is 331 / what's this commit / explain these changes / what did you change, asks "in simple words" or "explain the scenario", or wants to understand work they did not write themselves. Always opens with a concrete everyday analogy and a one-sentence plain statement of the defect; plain language is the DEFAULT output, never a mode the user has to ask for. Read-only: it reads the diff, the surrounding code and git history, and never runs the app, never checks out a branch, never edits. NOT for deciding whether to build something not yet written (use /issue-brief) and NOT for finding defects (use /code-review).
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

## 2. Establish authorship — this is not optional

The user asked for this explicitly: **never explain a change without saying who
wrote it.** They need to know whether they are reading their own past decision,
a contributor's proposal, or Claude's output from a session they don't recall.

It lands in position 2, immediately after the opening model (§3 step 1) and
before any mechanism. That is a deliberate change: it used to go first, and a
brief that opened with a username, three PR numbers and a timestamp got
"explain it clearly, I still didn't understand" in reply. A name means nothing
until the reader knows what the thing does. Two lines, still never skipped.

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

The first thing on screen is a mental model the reader can hold without knowing
the codebase. Not the authorship, not the file, not the constant. If they read
only the first six lines, they should be able to state the bug back to you in
their own words.

1. **The model and the thesis.** Open with a concrete, everyday analogy for the
   subsystem, then state the entire defect in ONE bolded sentence of plain
   words. Then write "That's the whole thing. Everything below is just why."

   **Hard budget for this section: zero `file:line`, zero constant names, zero
   PR numbers, zero usernames, every sentence under 15 words.** If you cannot
   write the thesis without an identifier in it, you do not yet understand the
   change well enough to explain it. Go back to the diff.

   Where the system has a small set of possible behaviours, enumerate the whole
   set first, then say which one is wrong. Three rows of a table beats three
   paragraphs:

   > You ask: "how much of my quota is left?"
   > There are only three honest answers:
   >
   > | Answer | Means |
   > |---|---|
   > | "You're at 95%" | Here's your data |
   > | "You have no agents set up" | Nothing to report |
   > | "I couldn't check just now" | Something went wrong |
   >
   > **The bug: it gives answer 2 when the truth is answer 3.**

2. **Who wrote what.** Two or three lines. Still never skipped and never hedged
   (§2), it just does not go first. A name and a PR number mean nothing until
   the reader knows what the thing does.
3. **The feature, and how someone actually uses it.** What is this capability
   *for*? Give the real reason a person reaches for it ("your home drive is
   small and you want the store on an external SSD"), not a restatement of its
   name. One `file:line` anchor, at the end of the paragraph, not the start.
4. **What you actually see.** Pure symptom, numbered, in the order the person
   experiences it. **No mechanism in this section at all**, not a constant, not
   a function name, not a reason. "The Plan-limits box disappears from your
   sidebar" belongs here; "because the errors list was empty" does not.
5. **Why it happens.** The mechanism, now that the symptom is concrete, with
   `file:line` anchors so every claim can be checked.
6. **What the change does about it** — including **the simpler fix it passed
   over, and why**. There is almost always an obvious cheaper repair; naming it
   and saying why the author went further is what turns "here is a diff" into
   "here is a judgement I can agree or disagree with". For #331: you could tell
   the one messy test to clean up after itself, but that leaves the next
   contributor free to make the identical mistake. Also say what the change
   deliberately leaves alone.
7. **Who it actually affects** — see §4, never skip this.
8. **Traps**, if any: version bumps that force a rescan, migrations, security
   gates, other open PRs on the same files, claims in the PR body that the diff
   does not support.
9. **A verdict and one next step.**

Steps 5, 6 and 8 collapse to a sentence each when the change is small.
Steps 1, 2, 3, 4 and 7 are never skipped, and step 1 is never reordered.

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

- **The analogy goes first, or it does not work.** An analogy introduced in
  paragraph four is decoration; the reader has already tried and failed to build
  their own model from your identifiers. Introduced in line two, it is the
  scaffold everything else hangs on. Carry exactly one all the way through, and
  keep the real identifier beside it on first use so the reader can still grep.
- **Put the confusion in a table, not in prose.** Whenever two things are being
  mistaken for each other, or behaviour changed from A to B, render it as two
  columns. Prose comparison across two paragraphs is where readers lose the
  thread. The columns must be the two CONCEPTS being confused, not raw evidence:
  `Who's reading | What it checks | Does the fix help?` teaches; a ten-row dump
  of test inputs does not.
- **Plain language is the default, not a mode.** Never wait to be asked to
  simplify. "In simple words" means fewer clauses, not fewer facts: strip the
  jargon, shorten the sentences, keep every variable name, number and path, and
  keep them where they belong, which is after the model and never before it. If
  the reader has to ask "explain it clearly, I still didn't understand", the
  brief failed, and the failure is almost always that identifiers arrived before
  the mental model.
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

## 6. Worked example (PR #356, quota cache lock)

> ## Think of the app as a receptionist
>
> You ask: "how much of my Claude quota is left?"
>
> There are only three honest answers:
>
> | Answer | Means |
> |---|---|
> | "You're at 95%" | Here's your data |
> | "You have no agents set up" | Nothing to report |
> | "I couldn't check just now" | Something went wrong |
>
> **The bug: it gives answer 2 when the truth is answer 3.**
>
> That's the whole thing. Everything below is just why.
>
> **Who wrote it.** Not me, this is AmirF194's PR. The bug report is mine, from
> an earlier `/bug-audit` session. The quota feature itself is yours.
>
> ## Why the receptionist gets stuck
>
> You run two separate programs: the menubar app and the dashboard. Both save
> quota data to the same file. Two programs writing one file at the same time
> would corrupt it, so there's a rule: whoever gets there first locks the file,
> the other one waits. The waiter gives up after 15 seconds
> (`CACHE_LOCK_TIMEOUT_SECONDS`).
>
> ## What you actually see
>
> 1. Both try to refresh. One wins, one waits.
> 2. The waiter gives up after 15 seconds.
> 3. The Plan-limits box disappears from your sidebar.
> 4. The menubar says `◔ No quota data`.
>
> You could be at 95% of your weekly limit and see nothing. No error. Just gone.
>
> ## Why "gave up" looks like "nothing configured"
>
> When the app answers, it fills in two lists: `capabilities` (what it found)
> and `errors` (what went wrong). On a brand-new machine both are empty, and
> that is correct. When the lock times out, the old code at `quotas.py:1314`
> sent back **both lists empty**. Identical. Nothing downstream can tell the two
> situations apart.
>
> ## Why it only half works
>
> | Who's reading | What it checks | Does the fix help? |
> |---|---|---|
> | Menubar (`presentation.py:294`) | the `errors` list | **Yes** |
> | Sidebar (`QuotaIndicator.tsx:51`) | only `providers`/`capabilities` | **No** |

Note the ordering. The analogy is the first thing on screen and the whole defect
fits in one bolded sentence with no identifiers in it. Authorship lands second,
in two lines, once the reader knows what they are being told about. The symptom
list contains no mechanism at all. Every `file:line` appears only after the
reader already has a model to hang it on. The two things being confused are a
table, not two paragraphs.

This matters more than any rule above it, because a worked example is what
actually gets copied. An earlier version of this brief led with authorship,
three PR numbers and a timestamp, and put the analogy in heading three. The
reader replied "Break It down and explain it clearly still didn't understand."
The content was identical. Only the order changed.

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
