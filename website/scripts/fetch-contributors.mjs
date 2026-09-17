// Build the contributor wall data: src/data/contributors.json plus a local copy
// of every avatar under public/contributors/.
//
// Why four sources: GitHub's /contributors endpoint only counts commits it can
// tie to an account, so a merged PR whose commits carry an unlinked email is
// missing from it (four people at the time of writing). Merged PR authors are
// added back from the issues API, and issue reporters and discussion
// participants are included because the wall credits everyone who helped, with
// their role kept so the page can tell code from reports.
//
// Avatars are downloaded here rather than hotlinked so the page makes no
// requests to GitHub on behalf of visitors.
//
// Fails soft: without a token or network the committed snapshot is left as is,
// so a local build or an API hiccup in CI never breaks the site.
//
// Usage: node scripts/fetch-contributors.mjs   (GITHUB_TOKEN, GH_TOKEN or `gh auth` login)

import { execSync } from "node:child_process";
import { mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const OWNER = "VasiHemanth";
const REPO = "tokentelemetry";
const ROOT = process.cwd();
const DATA_FILE = join(ROOT, "src/data/contributors.json");
const AVATAR_DIR = join(ROOT, "public/contributors");
const AVATAR_PX = 96;

// Accounts never shown. The maintainer's secondary account would double-count
// one person; add anyone who asks to be removed.
const EXCLUDE = new Set(["vasihemanth462"]);

const isBot = (login, type) => type === "Bot" || /\[bot\]$/i.test(login);

function token() {
  if (process.env.GITHUB_TOKEN) return process.env.GITHUB_TOKEN;
  if (process.env.GH_TOKEN) return process.env.GH_TOKEN;
  try {
    return execSync("gh auth token", { stdio: ["ignore", "pipe", "ignore"] }).toString().trim();
  } catch {
    return null;
  }
}

async function gh(path, auth) {
  const out = [];
  let url = `https://api.github.com${path}`;
  while (url) {
    const res = await fetch(url, { headers: { Authorization: `Bearer ${auth}`, Accept: "application/vnd.github+json" } });
    if (!res.ok) throw new Error(`GET ${url} -> ${res.status}`);
    out.push(...(await res.json()));
    const next = /<([^>]+)>;\s*rel="next"/.exec(res.headers.get("link") || "");
    url = next ? next[1] : null;
  }
  return out;
}

async function graphql(query, variables, auth) {
  const res = await fetch("https://api.github.com/graphql", {
    method: "POST",
    headers: { Authorization: `Bearer ${auth}`, "Content-Type": "application/json" },
    body: JSON.stringify({ query, variables }),
  });
  const body = await res.json();
  if (!res.ok || body.errors) throw new Error(`graphql -> ${res.status} ${JSON.stringify(body.errors || "")}`);
  return body.data;
}

async function discussionParticipants(auth) {
  const query = `query($owner:String!,$repo:String!,$after:String){
    repository(owner:$owner,name:$repo){
      discussions(first:50,after:$after){
        pageInfo{hasNextPage endCursor}
        nodes{
          author{login avatarUrl __typename}
          comments(first:100){nodes{author{login avatarUrl __typename}}}
        }
      }
    }
  }`;
  const people = [];
  let after = null;
  do {
    const d = (await graphql(query, { owner: OWNER, repo: REPO, after }, auth)).repository.discussions;
    for (const n of d.nodes) {
      for (const a of [n.author, ...n.comments.nodes.map((c) => c.author)]) {
        if (a?.login) people.push({ login: a.login, avatar_url: a.avatarUrl, type: a.__typename });
      }
    }
    after = d.pageInfo.hasNextPage ? d.pageInfo.endCursor : null;
  } while (after);
  return people;
}

async function main() {
  const auth = token();
  if (!auth) {
    console.warn("contributors: no GitHub token, keeping the committed snapshot");
    return;
  }

  const people = new Map();
  const person = (login, avatarUrl) => {
    const key = login.toLowerCase();
    if (!people.has(key)) {
      people.set(key, { login, avatar_url: avatarUrl, commits: 0, merged_prs: 0, open_or_closed_prs: 0, issues: 0, discussions: 0 });
    }
    return people.get(key);
  };
  const skip = (login, type) => !login || isBot(login, type) || EXCLUDE.has(login.toLowerCase());

  for (const c of await gh(`/repos/${OWNER}/${REPO}/contributors?per_page=100`, auth)) {
    if (skip(c.login, c.type)) continue;
    person(c.login, c.avatar_url).commits += c.contributions;
  }

  for (const item of await gh(`/repos/${OWNER}/${REPO}/issues?state=all&per_page=100`, auth)) {
    const u = item.user;
    if (skip(u?.login, u?.type)) continue;
    const p = person(u.login, u.avatar_url);
    if (!item.pull_request) p.issues += 1;
    else if (item.pull_request.merged_at) p.merged_prs += 1;
    else p.open_or_closed_prs += 1;
  }

  for (const a of await discussionParticipants(auth)) {
    if (skip(a.login, a.type === "Bot" ? "Bot" : "User")) continue;
    person(a.login, a.avatar_url).discussions += 1;
  }

  const list = [...people.values()].map((p) => ({
    ...p,
    role: p.commits || p.merged_prs ? "code" : p.open_or_closed_prs ? "pr" : p.issues ? "issue" : "discussion",
  }));
  const rank = { code: 0, pr: 1, issue: 2, discussion: 3 };
  const weight = (p) => p.commits + p.merged_prs * 3 + p.open_or_closed_prs + p.issues + p.discussions;
  list.sort((a, b) => rank[a.role] - rank[b.role] || weight(b) - weight(a) || a.login.localeCompare(b.login));

  // Download every avatar before touching the snapshot, so a failed run
  // leaves the previous data and images intact.
  const images = [];
  for (const p of list) {
    const sep = p.avatar_url.includes("?") ? "&" : "?";
    const res = await fetch(`${p.avatar_url}${sep}s=${AVATAR_PX}`);
    if (!res.ok) throw new Error(`avatar ${p.login} -> ${res.status}`);
    const ext = (res.headers.get("content-type") || "").includes("png") ? "png" : "jpg";
    images.push({ file: `${p.login.toLowerCase()}.${ext}`, bytes: Buffer.from(await res.arrayBuffer()) });
  }

  mkdirSync(AVATAR_DIR, { recursive: true });
  for (const f of readdirSync(AVATAR_DIR)) rmSync(join(AVATAR_DIR, f));
  const contributors = list.map((p, i) => {
    writeFileSync(join(AVATAR_DIR, images[i].file), images[i].bytes);
    const { avatar_url: _drop, ...rest } = p;
    return { ...rest, avatar: `/contributors/${images[i].file}` };
  });

  const counts = contributors.reduce((acc, p) => ({ ...acc, [p.role]: (acc[p.role] || 0) + 1 }), {});
  writeFileSync(
    DATA_FILE,
    JSON.stringify({ generated_at: new Date().toISOString(), total: contributors.length, counts, contributors }, null, 2) + "\n",
  );
  console.log(`contributors: ${contributors.length} people`, counts);
}

main().catch((err) => {
  console.warn(`contributors: ${err.message}; keeping the committed snapshot`);
});
