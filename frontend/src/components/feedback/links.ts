export const REPO = "VasiHemanth/tokentelemetry";

const base = `https://github.com/${REPO}`;

export function discussionUrl(category: "ideas" | "show-and-tell" | "q-a", title?: string) {
  const params = new URLSearchParams({ category });
  if (title) params.set("title", title);
  return `${base}/discussions/new?${params.toString()}`;
}

export function issueUrl(opts: { title?: string; labels?: string; body?: string } = {}) {
  const params = new URLSearchParams();
  if (opts.labels) params.set("labels", opts.labels);
  if (opts.title) params.set("title", opts.title);
  if (opts.body) params.set("body", opts.body);
  const qs = params.toString();
  return `${base}/issues/new${qs ? `?${qs}` : ""}`;
}

export const SOCIALS = {
  github: `https://github.com/VasiHemanth`,
  linkedin: `https://www.linkedin.com/in/vasi-hemanth/`,
  twitter: `https://twitter.com/VasiHemanth`,
  discussions: `${base}/discussions`,
};
