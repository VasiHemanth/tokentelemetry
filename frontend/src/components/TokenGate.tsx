"use client";

import { useEffect, useState } from "react";
import { setToken, stripBootstrapTokenFromUrl } from "../lib/api";

// Modal that appears when the backend rejects a request for lack of a valid
// access token (remote/tailnet use). It listens for the `tt-auth-required`
// window event emitted by api() on a 401, lets the user paste the token the
// server printed once on startup, persists it (per-host, in localStorage), and
// reloads so every in-flight poller refetches with the credential attached.
//
// Local (loopback) use never triggers this: the backend exempts loopback and
// only enforces the token when one is configured for a remote bind.
export default function TokenGate() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");

  useEffect(() => {
    // Clean a consumed bootstrap token out of the address bar now that Next has
    // hydrated (doing it at module load gets overwritten by the router).
    stripBootstrapTokenFromUrl();

    // Just open — do NOT touch `value` here. Background pollers keep firing
    // requests, so this event repeats every poll interval while the modal is
    // open; resetting `value` would wipe whatever the user is mid-typing.
    const onAuthRequired = () => setOpen(true);
    window.addEventListener("tt-auth-required", onAuthRequired);
    return () => window.removeEventListener("tt-auth-required", onAuthRequired);
  }, []);

  if (!open) return null;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = value.trim();
    if (!t) return;
    setToken(t);
    // Reload so all pollers (useResource) and any raw fetches re-run with the
    // Authorization header now that the token is stored.
    window.location.reload();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="tt-tokengate-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
    >
      <form
        onSubmit={submit}
        className="w-[min(28rem,90vw)] rounded-xl border border-[var(--tt-border)] bg-[var(--tt-panel)] p-6 shadow-2xl"
      >
        <h2 id="tt-tokengate-title" className="text-lg font-semibold text-[var(--tt-fg)]">
          Access token required
        </h2>
        <p className="mt-2 text-sm text-[var(--tt-fg-muted)]">
          This TokenTelemetry instance is being accessed remotely. Paste the
          access token printed in the server&apos;s console when it started, then
          continue.
        </p>
        <input
          type="password"
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Paste access token"
          className="mt-4 w-full rounded-lg border border-[var(--tt-border)] bg-[var(--tt-canvas)] px-3 py-2 text-sm text-[var(--tt-fg)] outline-none focus:border-[var(--tt-border-focus)]"
        />
        <button
          type="submit"
          disabled={!value.trim()}
          className="mt-4 w-full rounded-lg bg-[var(--tt-brand)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Continue
        </button>
      </form>
    </div>
  );
}
