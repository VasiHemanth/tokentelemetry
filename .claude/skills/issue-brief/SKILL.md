---
name: issue-brief
description: Explain a GitHub issue, discussion, or feature request in plain language before deciding whether to build it. Covers what the reporter actually wants, a numbered walkthrough of the failure using real hostnames/ports/endpoints, how the code behaves today with file:line anchors, what implementing it would take, and the traps (security regressions, open PRs touching the same files, older issues with the same root cause). Use whenever a github.com issues/ or discussions/ link is pasted, or the user says check / look at / verify / assess / analyse this issue, what does this issue want, is it worth doing, what would it take, or refers to one by number (issue 198, discussion 49). Also handles the follow-ups "what are the cons" and "explain that in simple terms". NOT for pull requests (use /review) and NOT for implementing. An issue-brief ends with the working tree untouched.
---

# issue-brief — explain an issue before building it

The output is an **explanation**, not a design doc and not a diff. Assume the
reader has not read the reporter's post and does not have the file layout in
their head. Lead with the plain meaning; the architecture comes fourth.

## 1. Fetch the thing

Issues:

```bash
gh issue view <number-or-url> --json number,title,state,author,createdAt,closedAt,labels,body,comments
```

**Discussions need GraphQL.** There is no `gh discussion` command (verified on
gh 2.92), and `gh issue view` will not resolve a discussion number. Use:

```bash
gh api graphql -f query='
{ repository(owner:"VasiHemanth", name:"tokentelemetry") {
    discussion(number: NNN) {
      number title url category{name} author{login} createdAt body
      comments(first:20){ nodes { author{login} body } }
    } } }'
```

Then, before writing anything:

- **Check it isn't already done.** Grep the codebase for the feature's nouns.
  Issue 135 (Pi agent support) was closed and fully shipped; the tell was
  `PI_SESSIONS_DIR` and `test_pi_scan.py` already sitting on main.
- **Search for the same root cause elsewhere**, open and closed
  (`gh issue list --search`). Issues 198 and 96 were the same two-port problem
  reported twice, a year apart, by different people.
- **Check open PRs that touch the files you'd touch** (`gh pr list`). They set
  the landing order.

## 2. Answer in this order

1. **What the reporter actually wants**, in one or two sentences of plain
   language, jargon stripped. Name them. Link the earlier issue or PR if it's
   a repeat.
2. **A concrete walkthrough of the problem.** Pick one realistic setup and
   trace it as numbered steps, with real hostnames, real ports, real
   endpoints. Never "suppose a user does X". Say what the user *sees* first,
   then why it happens.
3. **How it works today**, only the part that bears on the issue, with
   `file.py:line` anchors so the claim can be checked.
4. **What implementing it would take**: the shape of the change and which
   layer it belongs in, not a full diff.
5. **Traps and interactions.** Security regressions, open PRs on the same
   files, closed issues with the same root cause, what has to land first.
6. **A verdict and one next step** ("worth accepting, want me to draft the
   reply comment?").

Steps 3 and 4 collapse to a sentence each when the issue is simple. Steps 1,
2 and 6 are never skipped.

## 3. Prose rules

- **Symptom before mechanism.** "It looks broken but nothing crashed, the page
  just never got its data," and only then the middleware ordering.
- **Expand every acronym and product name once**, the first time it appears.
  The reporter's Pangolin / SSE / CORS gets one clause of explanation.
- **Don't paste code blocks.** Quote a few lines at most, or cite `file:line`
  and let the reader open it.
- **No hedging stacks.** One verdict. If it is genuinely balanced, say what
  evidence would decide it.
- **Say what you touched.** State explicitly that the tree is untouched, or
  what changed if implementation was requested separately.

## 4. "What are the cons?"

Answer as **con → mitigation pairs**, grouped by how much they matter, and say
plainly which group each falls in:

- **Blocker.** Must ship in the same PR or the feature is a regression.
- **Verify before merge.** Fine in principle, needs a number on the bench.
- **Acceptable.** The ordinary cost of the approach. Name it and move on.

Every con gets a mitigation or it isn't finished. A con with no mitigation is
a blocker by definition.

## 5. Worked example (issue 198, single-port proxy)

> **What they want.** Jiaocz runs TokenTelemetry behind Pangolin, a reverse
> proxy that maps a *domain* to *one* port. They want the API reachable
> through the web port so one domain is enough. Same root cause as issue 96
> (SSH tunnel with only 3000 forwarded).
>
> **What breaks.** TokenTelemetry runs two servers: 3000 serves the page, 8000
> serves the data.
> 1. You open `tt.mydomain.com`. The dashboard loads, layout fine.
> 2. The page fetches `tt.mydomain.com:8000` for sessions.
> 3. Nothing is there. The proxy only published 3000.
> 4. Empty shell. Blank charts, zero sessions.
>
> **Today.** `frontend/src/lib/api.ts` builds `API_BASE` from
> `window.location.hostname` plus `NEXT_PUBLIC_API_PORT`. Everything funnels
> through `apiFetch`, no SSE, no WebSockets, one binary endpoint.
>
> **The trap.** `RemoteAuthMiddleware` (`backend/main.py:228`) exempts
> loopback. Proxy everything through Next and every request arrives from
> 127.0.0.1, so the token gate is bypassed for the whole internet and
> `/remote-access` (`main.py:5709`) hands the token to any visitor who asks.

Note what the example does. The failure is walked before a single filename
appears, and the security trap is stated consequence-first ("bypassed for the
whole internet"), not as a description of middleware registration order.

## 6. Don't

- Don't open a worktree or edit files. This skill is read-only.
- Don't comment on the issue, close it, or label it unless asked.
- Don't use this for pull requests. `/review` covers those.
