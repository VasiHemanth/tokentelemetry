"use client";

import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Copy, Check } from "lucide-react";
import { getRemoteAccess, type RemoteAccess } from "@/lib/api";
import { Section, Card, CardHeader, CardTitle } from "@/components/ui";

// "Connect a device" panel: shows a QR that encodes a scan-to-open link
// (host + frontend port + one-time bootstrap token). Only rendered when remote
// access is enabled — the backend serves /remote-access loopback-only, so on a
// remote device the fetch 403s and this renders nothing. On a normal local run
// (no --host) the backend reports {enabled:false}, so it's hidden there too.
export function ConnectDevice() {
  const [info, setInfo] = useState<RemoteAccess | null>(null);
  const [copied, setCopied] = useState<"" | "link" | "token">("");

  useEffect(() => {
    let cancelled = false;
    getRemoteAccess()
      .then((d) => { if (!cancelled) setInfo(d.enabled ? d : null); })
      .catch(() => { if (!cancelled) setInfo(null); });
    return () => { cancelled = true; };
  }, []);

  if (!info?.enabled || !info.url) return null;

  const copy = (what: "link" | "token", text: string) => {
    navigator.clipboard?.writeText(text)
      .then(() => { setCopied(what); setTimeout(() => setCopied(""), 1500); })
      .catch(() => {});
  };

  const btn =
    "inline-flex items-center gap-1.5 rounded-lg border border-[var(--tt-border)] " +
    "px-3 py-1.5 text-[12px] text-[var(--tt-fg)] hover:border-[var(--tt-border-focus)] " +
    "transition-colors cursor-pointer";

  return (
    <Section
      title="Connect a device"
      description="Scan to open the dashboard on a phone or tablet on your network — no IP or token to type."
    >
      <Card>
        <CardHeader>
          <CardTitle>Scan to connect</CardTitle>
        </CardHeader>
        <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-start">
          {/* QR needs a light quiet-zone to scan reliably in any theme. */}
          <div className="shrink-0 rounded-xl bg-white p-3">
            <QRCodeSVG value={info.url} size={160} />
          </div>
          <div className="min-w-0 flex-1 space-y-3">
            <p className="text-[12px] text-[var(--tt-fg-muted)]">
              The QR carries a one-time access token. The device stores it and
              clears it from the address bar automatically, so it stays signed in
              without exposing the token in its history.
            </p>
            <div className="flex flex-wrap gap-2">
              <button type="button" className={btn} onClick={() => copy("link", info.url!)}>
                {copied === "link" ? <Check size={13} /> : <Copy size={13} />} Copy link
              </button>
              {info.token && (
                <button type="button" className={btn} onClick={() => copy("token", info.token!)}>
                  {copied === "token" ? <Check size={13} /> : <Copy size={13} />} Copy token
                </button>
              )}
            </div>
          </div>
        </div>
      </Card>
    </Section>
  );
}
