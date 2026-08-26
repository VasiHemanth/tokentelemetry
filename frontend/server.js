/* eslint-disable @typescript-eslint/no-require-imports */
// Small Next launcher that records the actual TCP peer before Next normalizes
// x-forwarded-for. Proxy.ts can then safely distinguish a local SSH tunnel from
// a network caller; trusting a client-supplied forwarding header would let a
// remote caller forge loopback and bypass backend auth.
const http = require("http");
const https = require("https");
const fs = require("fs");
const path = require("path");
const next = require("next");

const dev = process.env.NODE_ENV !== "production";
// next() is normally the source-server entrypoint. Reuse the compiled build's
// resolved config so this wrapper can safely add TCP-peer normalization.
if (!dev) {
  const required = path.join(process.cwd(), ".next", "required-server-files.json");
  process.env.__NEXT_PRIVATE_STANDALONE_CONFIG = JSON.stringify(JSON.parse(fs.readFileSync(required, "utf8")).config);
}
const app = next({ dev });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  http.createServer((req, res) => {
    delete req.headers["x-forwarded-for"];
    delete req.headers["x-real-ip"];
    delete req.headers["x-tt-proxied"];
    const peer = req.socket.remoteAddress || "";
    req.headers["x-forwarded-for"] = peer;

    // External Next rewrites intentionally strip Authorization. Stream this
    // narrow API prefix at the TCP edge instead so bearer auth, query tokens,
    // client IP, and large artifact responses all pass through unchanged.
    if (process.env.TT_SINGLE_PORT_PROXY === "1" && req.url.startsWith("/_tt-api")) {
      const target = new URL(process.env.TT_PROXY_API_URL || "http://127.0.0.1:8000");
      const loopback = peer === "127.0.0.1" || peer === "::1" || peer === "::ffff:127.0.0.1";
      if (!loopback) req.headers["x-tt-proxied"] = "1";
      const upstream = (target.protocol === "https:" ? https : http).request({
        protocol: target.protocol,
        hostname: target.hostname,
        port: target.port,
        method: req.method,
        path: (req.url.slice("/_tt-api".length) || "/"),
        headers: {
          ...req.headers,
          host: target.host,
          authorization: req.headers.authorization || "",
        },
      }, (upstreamRes) => {
        res.writeHead(upstreamRes.statusCode || 502, upstreamRes.headers);
        upstreamRes.pipe(res);
      });
      upstream.on("error", () => { if (!res.headersSent) res.writeHead(502); res.end(); });
      req.pipe(upstream);
      return;
    }
    if (req.url.startsWith("/_tt-api")) { res.writeHead(404); res.end(); return; }
    handle(req, res);
  }).listen(Number(process.env.PORT || 3000), process.env.HOSTNAME || "0.0.0.0");
});