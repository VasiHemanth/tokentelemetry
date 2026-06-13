"use client";

import { useEffect, useState } from "react";
import { Zap, Check, Loader2, Gauge } from "lucide-react";
import { Card, CardHeader, CardTitle, Button, Badge, Skeleton } from "@/components/ui";
import {
  getPowerConfig, putPowerConfig, getPowerMeter, calibratePower,
  type PowerConfig, type PowerMeter,
} from "@/lib/power";

const linesToList = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

export function PowerSettings() {
  const [cfg, setCfg] = useState<PowerConfig | null>(null);
  const [meter, setMeter] = useState<PowerMeter | null>(null);
  const [watts, setWatts] = useState("");
  const [kwh, setKwh] = useState("");
  const [gci, setGci] = useState("");
  const [subs, setSubs] = useState("");
  const [locals, setLocals] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [calibrating, setCalibrating] = useState(false);
  const [calibMsg, setCalibMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hydrate = (c: PowerConfig) => {
    setCfg(c);
    setWatts(String(c.loadWatts));
    setKwh(String(c.costPerKwh));
    setGci(String(c.gridCarbonIntensity));
    setSubs((c.subscriptionEndpoints ?? []).join("\n"));
    setLocals((c.localEndpoints ?? []).join("\n"));
  };

  useEffect(() => {
    let cancelled = false;
    Promise.all([getPowerConfig(), getPowerMeter().catch(() => null)])
      .then(([c, m]) => { if (!cancelled) { hydrate(c); setMeter(m); setLoading(false); } })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load power config.");
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const save = async () => {
    setSaving(true); setError(null); setSaved(false);
    try {
      const next = await putPowerConfig({
        loadWatts: Number(watts) || 0,
        costPerKwh: Number(kwh) || 0,
        gridCarbonIntensity: Number(gci) || 0,
        subscriptionEndpoints: linesToList(subs),
        localEndpoints: linesToList(locals),
      });
      hydrate(next);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save.");
    } finally {
      setSaving(false);
    }
  };

  const calibrate = async () => {
    setCalibrating(true); setCalibMsg(null); setError(null);
    try {
      const r = await calibratePower();
      if (r.measured != null) {
        setWatts(String(Math.round(r.measured)));
        setCalibMsg(`✓ Measured ${r.measured} W via ${r.source} — review and click Save.`);
      } else if (r.estimated != null) {
        // No root-free measurement (e.g. Apple Silicon on AC), but we derived a
        // chip-aware estimate. Prefill it as a starting point to override.
        setWatts(String(Math.round(r.estimated)));
        const from = r.detail ? ` from ${r.detail}` : "";
        setCalibMsg(`≈ Estimated ${r.estimated} W${from} — this is a rough default; override with your real draw if you know it, then Save.`);
      } else {
        const why = r.reason ? ` (${r.reason})` : "";
        setCalibMsg(`Couldn't read power automatically on this machine — type your watts in “Load watts” above and Save.${why}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Calibration failed.");
    } finally {
      setCalibrating(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <Zap size={14} className="text-[var(--tt-brand)]" />
          Local power & electricity cost
        </CardTitle>
        {cfg && (
          <Badge variant={cfg.configured ? "success" : "neutral"} size="sm">
            {cfg.configured ? "Configured" : "Defaults"}
          </Badge>
        )}
      </CardHeader>

      {loading ? (
        <div className="space-y-2"><Skeleton className="h-12 w-full" /><Skeleton className="h-12 w-full" /></div>
      ) : (
        <div className="space-y-4">
          <p className="text-[12px] leading-relaxed text-[var(--tt-fg-dim)]">
            Models you run locally (Ollama, llama.cpp, vLLM) have no API bill — their cost is electricity.
            TokenTelemetry estimates it from your machine&apos;s draw under load and your kWh rate.
          </p>

          <div className="grid grid-cols-3 gap-4">
            <label className="block">
              <span className="text-[11px] uppercase tracking-wide text-[var(--tt-fg-muted)]">Load watts</span>
              <input
                type="number" inputMode="decimal" value={watts} onChange={(e) => setWatts(e.target.value)}
                className="mt-1 w-full rounded-md border border-[var(--tt-border)] bg-[var(--tt-bg-elev)] px-2.5 py-1.5 text-[13px] text-[var(--tt-fg)] outline-none focus:border-[var(--tt-brand)]"
              />
              {cfg?.deviceDefault && (
                cfg.deviceDefault.detected ? (
                  <button
                    type="button"
                    onClick={() => setWatts(String(cfg.deviceDefault!.watts))}
                    className="mt-1 text-[11px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-brand)] transition-colors"
                    title="Use the detected default for this machine"
                  >
                    Default for {cfg.deviceDefault.detail ?? "this machine"}: {cfg.deviceDefault.watts} W (estimated)
                  </button>
                ) : (
                  <span className="mt-1 block text-[11px] text-[var(--tt-fg-muted)]">
                    Couldn&apos;t auto-detect your hardware — enter your machine&apos;s draw under load
                    (or click Measure). Using a generic {cfg.deviceDefault.watts} W until you do.
                  </span>
                )
              )}
            </label>
            <label className="block">
              <span className="text-[11px] uppercase tracking-wide text-[var(--tt-fg-muted)]">Cost per kWh ($)</span>
              <input
                type="number" inputMode="decimal" step="0.01" value={kwh} onChange={(e) => setKwh(e.target.value)}
                className="mt-1 w-full rounded-md border border-[var(--tt-border)] bg-[var(--tt-bg-elev)] px-2.5 py-1.5 text-[13px] text-[var(--tt-fg)] outline-none focus:border-[var(--tt-brand)]"
              />
            </label>
            <label className="block">
              <span className="text-[11px] uppercase tracking-wide text-[var(--tt-fg-muted)]">Grid CO₂ (g/kWh)</span>
              <input
                type="number" inputMode="decimal" value={gci} onChange={(e) => setGci(e.target.value)}
                className="mt-1 w-full rounded-md border border-[var(--tt-border)] bg-[var(--tt-bg-elev)] px-2.5 py-1.5 text-[13px] text-[var(--tt-fg)] outline-none focus:border-[var(--tt-brand)]"
              />
            </label>
          </div>

          {/* Measure / calibrate */}
          <div className="flex items-center gap-3 rounded-md border border-[var(--tt-border)] bg-[var(--tt-bg-elev)]/40 px-3 py-2.5">
            <Gauge size={15} className="shrink-0 text-[var(--tt-fg-muted)]" />
            <div className="min-w-0 flex-1">
              <div className="text-[12px] text-[var(--tt-fg-dim)]">
                {calibMsg ?? meter?.capability.reason ?? "Measure your machine's real draw under load."}
              </div>
            </div>
            <Button variant="secondary" onClick={calibrate} disabled={calibrating}>
              {calibrating ? <><Loader2 size={13} className="animate-spin" /> Measuring…</> : "Measure"}
            </Button>
          </div>

          <label className="block">
            <span className="text-[11px] uppercase tracking-wide text-[var(--tt-fg-muted)]">Local endpoints (one per line)</span>
            <textarea
              rows={2} value={locals} onChange={(e) => setLocals(e.target.value)}
              placeholder="http://192.168.1.50:11434"
              className="mt-1 w-full rounded-md border border-[var(--tt-border)] bg-[var(--tt-bg-elev)] px-2.5 py-1.5 text-[12px] font-mono text-[var(--tt-fg)] outline-none focus:border-[var(--tt-brand)]"
            />
            <span className="text-[11px] text-[var(--tt-fg-muted)]">Loopback (localhost) is always treated as local. Add LAN boxes here.</span>
          </label>

          <label className="block">
            <span className="text-[11px] uppercase tracking-wide text-[var(--tt-fg-muted)]">Subscription endpoints — $0 per call (one per line)</span>
            <textarea
              rows={2} value={subs} onChange={(e) => setSubs(e.target.value)}
              placeholder="https://ollama.com"
              className="mt-1 w-full rounded-md border border-[var(--tt-border)] bg-[var(--tt-bg-elev)] px-2.5 py-1.5 text-[12px] font-mono text-[var(--tt-fg)] outline-none focus:border-[var(--tt-brand)]"
            />
          </label>

          {error && <p className="text-[12px] text-[var(--tt-danger-fg)]">{error}</p>}

          <div className="flex items-center justify-end gap-3 pt-1">
            {saved && <span className="flex items-center gap-1.5 text-[12px] text-[var(--tt-success-fg)]"><Check size={13} /> Saved</span>}
            <Button variant="primary" onClick={save} disabled={saving}>
              {saving ? <><Loader2 size={13} className="animate-spin" /> Saving…</> : "Save changes"}
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
