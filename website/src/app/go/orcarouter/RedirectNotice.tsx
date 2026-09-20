"use client";

import { useEffect } from "react";

/**
 * Holds the page still long enough for the analytics beacon (loaded
 * afterInteractive by the root layout) to register the pageview, then leaves.
 * `location.replace` keeps this hop out of the back-button history, so Back
 * returns to the docs page rather than bouncing the reader forward again.
 */
export default function RedirectNotice({ target }: { target: string }) {
  useEffect(() => {
    const t = setTimeout(() => window.location.replace(target), 1200);
    return () => clearTimeout(t);
  }, [target]);

  return (
    <main className="mx-auto flex min-h-[60vh] max-w-xl flex-col justify-center gap-3 px-4 py-16">
      <h1 className="text-lg font-semibold">Opening OrcaRouter</h1>
      <p className="text-sm opacity-80">
        Taking you to OrcaRouter, where one key reaches many models for session
        summaries. If nothing happens,{" "}
        <a href={target} rel="noopener noreferrer" className="underline">
          follow this link
        </a>
        .
      </p>
      <p className="text-xs opacity-60">
        This is a referral link. TokenTelemetry earns a share of what referred
        workspaces spend. It costs you nothing, and the OrcaRouter preset in the app
        works the same whether you arrive this way or sign up directly.
      </p>
    </main>
  );
}
