"use client";

import { useEffect, useMemo, useState } from "react";
import { X, Calendar, ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui";
import {
  BuilderState, CreateCronJobBody, CronJob, CronScript, DELIVERY_TARGETS,
  EditCronJobBody, Frequency, HermesSkill,
  createCronJob, editCronJob, encodeSchedule, initialBuilder,
  listCronScripts, listHermesSkills,
} from "@/lib/hermesCron";

interface Props {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  /** If set, the modal opens in edit mode prefilled from this job. */
  editingJob?: CronJob | null;
}

const DAYS = [
  { value: "0", label: "Sun" }, { value: "1", label: "Mon" }, { value: "2", label: "Tue" },
  { value: "3", label: "Wed" }, { value: "4", label: "Thu" }, { value: "5", label: "Fri" },
  { value: "6", label: "Sat" },
];

const FREQS: { value: Frequency; label: string }[] = [
  { value: "minutes", label: "Every N minutes" },
  { value: "hourly",  label: "Every N hours" },
  { value: "daily",   label: "Daily" },
  { value: "weekly",  label: "Weekly" },
  { value: "custom",  label: "Custom cron" },
];

// Map a job's schedule_display back to a builder state on best effort. If we
// can't recognize it, fall back to custom-cron mode preloaded with the raw
// display string so the user can edit it as text.
function builderFromJob(j: CronJob): BuilderState {
  const disp = (j.schedule_display || "").trim();
  // "30m", "120m"
  let m = disp.match(/^(\d+)m$/);
  if (m) return { ...initialBuilder, frequency: "minutes", minutesInterval: m[1] };
  // "every 2h" / "every 60m"
  m = disp.match(/^every (\d+)h$/);
  if (m) return { ...initialBuilder, frequency: "hourly", hourlyInterval: m[1] };
  m = disp.match(/^every (\d+)m$/);
  if (m) return { ...initialBuilder, frequency: "minutes", minutesInterval: m[1] };
  // "daily 09:00"
  m = disp.match(/^daily (\d{2}:\d{2})$/);
  if (m) return { ...initialBuilder, frequency: "daily", dailyTime: m[1] };
  // Anything else: hand to custom cron mode.
  return { ...initialBuilder, frequency: "custom", customCron: disp };
}

export default function CreateScheduleModal({ open, onClose, onSaved, editingJob }: Props) {
  const isEdit = !!editingJob;

  const [b, setB] = useState<BuilderState>(initialBuilder);
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [deliver, setDeliver] = useState<string>("local");
  const [customDeliver, setCustomDeliver] = useState("");

  // Advanced section.
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [skills, setSkills] = useState<string[]>([]);
  const [script, setScript] = useState<string>("");           // "" = no script
  const [noAgent, setNoAgent] = useState<boolean>(false);
  const [repeat, setRepeat] = useState<string>("");           // "" = forever
  const [workdir, setWorkdir] = useState<string>("");

  // Catalogs loaded on first open.
  const [scriptCatalog, setScriptCatalog] = useState<CronScript[]>([]);
  const [skillCatalog, setSkillCatalog] = useState<HermesSkill[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Esc to close — match the desktop's UX.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Prefill on open: from `editingJob` in edit mode, otherwise reset.
  /* eslint-disable react-hooks/set-state-in-effect -- Opening the modal intentionally resets its draft state from props. */
  useEffect(() => {
    if (!open) return;
    setError(null); setSubmitting(false);
    if (editingJob) {
      setB(builderFromJob(editingJob));
      setName(editingJob.name === "(unnamed)" ? "" : editingJob.name);
      setPrompt(editingJob.prompt || "");
      const d = editingJob.deliver?.[0] || "local";
      const known = DELIVERY_TARGETS.some((t) => t.value === d);
      setDeliver(known ? d : "__custom");
      setCustomDeliver(known ? "" : d);
      setSkills(editingJob.skills || []);
      setScript(editingJob.script || "");
      setRepeat(editingJob.repeat?.times != null ? String(editingJob.repeat.times) : "");
      // We don't currently surface `no_agent` or `workdir` from the read
      // payload — leave at defaults; an edit that doesn't change them won't
      // send those flags (None on the wire = leave alone).
      setNoAgent(false);
      setWorkdir("");
      // Show advanced if any advanced field is non-default for edit clarity.
      setShowAdvanced(
        (editingJob.skills?.length ?? 0) > 0
          || !!editingJob.script
          || editingJob.repeat?.times != null,
      );
    } else {
      setB(initialBuilder); setName(""); setPrompt(""); setDeliver("local");
      setCustomDeliver(""); setSkills([]); setScript(""); setNoAgent(false);
      setRepeat(""); setWorkdir(""); setShowAdvanced(false);
    }
  }, [open, editingJob]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // Lazy-load script + skill catalogs the first time the modal opens.
  useEffect(() => {
    if (!open) return;
    if (scriptCatalog.length === 0) listCronScripts().then(setScriptCatalog).catch(() => {});
    if (skillCatalog.length === 0) listHermesSkills().then(setSkillCatalog).catch(() => {});
    // We only want to fire this once per open, not on every state change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const skillByCategory = useMemo(() => {
    const m = new Map<string, HermesSkill[]>();
    for (const s of skillCatalog) {
      const cat = s.category || "(uncategorized)";
      const arr = m.get(cat) || [];
      arr.push(s); m.set(cat, arr);
    }
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [skillCatalog]);

  if (!open) return null;

  const schedulePreview = encodeSchedule(b);
  const deliverValue = deliver === "__custom" ? customDeliver.trim() : deliver;
  // In edit mode the prompt may be empty if the user is only changing other
  // fields. In create mode it's still required.
  const canSubmit =
    !!schedulePreview
    && (isEdit || !!prompt.trim())
    && !!deliverValue
    && !submitting;

  function toggleSkill(name: string) {
    setSkills((prev) => prev.includes(name) ? prev.filter((s) => s !== name) : [...prev, name]);
  }

  async function submit() {
    if (!schedulePreview) { setError("Pick a frequency first."); return; }
    setSubmitting(true); setError(null);
    try {
      const repeatN = repeat.trim() ? parseInt(repeat, 10) : undefined;
      if (repeatN !== undefined && (!Number.isFinite(repeatN) || repeatN < 1)) {
        setError("Repeat must be a positive number, or empty for forever.");
        setSubmitting(false); return;
      }
      const advanced = {
        skills: skills.length ? skills : undefined,
        script: script ? script : undefined,
        no_agent: noAgent || undefined,
        repeat: repeatN,
        workdir: workdir.trim() ? workdir.trim() : undefined,
      };
      if (isEdit && editingJob) {
        const body: EditCronJobBody = {
          schedule: schedulePreview,
          prompt: prompt.trim() || undefined,
          name: name.trim() || undefined,
          deliver: deliverValue || undefined,
          // Replacing skills set; if user cleared them all, signal it explicitly.
          skills: skills.length ? skills : undefined,
          clear_skills: skills.length === 0 && (editingJob.skills?.length ?? 0) > 0 ? true : undefined,
          script: script !== (editingJob.script || "") ? script : undefined,
          no_agent: noAgent ? true : undefined,
          repeat: advanced.repeat,
          workdir: advanced.workdir,
        };
        await editCronJob(editingJob.id, body);
      } else {
        const body: CreateCronJobBody = {
          schedule: schedulePreview,
          prompt: prompt.trim(),
          name: name.trim() || undefined,
          deliver: deliverValue || undefined,
          ...advanced,
        };
        await createCronJob(body);
      }
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="schedule-modal-title"
      className="fixed inset-0 z-50 grid place-items-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[620px] max-h-[92vh] overflow-y-auto rounded-[var(--tt-radius-lg)] border border-[var(--tt-border-strong)] bg-[var(--tt-panel)] shadow-[0_24px_80px_-20px_rgba(0,0,0,0.85)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--tt-border)]">
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 grid place-items-center rounded-md bg-indigo-500/15 text-indigo-400">
              <Calendar size={15} />
            </div>
            <h2 id="schedule-modal-title" className="text-[15px] font-semibold tracking-[-0.01em] text-[var(--tt-fg)]">
              {isEdit ? "Edit schedule" : "New schedule"}
            </h2>
          </div>
          <button
            type="button" onClick={onClose} aria-label="Close"
            className="h-8 w-8 grid place-items-center rounded-md text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:tt-tint-2 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-5">
          <Field label="Name (optional)">
            <input
              type="text" value={name} onChange={(e) => setName(e.target.value)}
              placeholder="e.g. daily digest"
              className={inputCls}
            />
          </Field>

          <Field label="Frequency">
            <select
              value={b.frequency}
              onChange={(e) => setB({ ...b, frequency: e.target.value as Frequency })}
              className={inputCls}
            >
              {FREQS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
            </select>

            <div className="mt-2.5">
              {b.frequency === "minutes" && (
                <NumberInput
                  label="Every (minutes)" value={b.minutesInterval}
                  onChange={(v) => setB({ ...b, minutesInterval: v })} min={1}
                />
              )}
              {b.frequency === "hourly" && (
                <NumberInput
                  label="Every (hours)" value={b.hourlyInterval}
                  onChange={(v) => setB({ ...b, hourlyInterval: v })} min={1}
                />
              )}
              {b.frequency === "daily" && (
                <TimeInput
                  label="At" value={b.dailyTime}
                  onChange={(v) => setB({ ...b, dailyTime: v })}
                />
              )}
              {b.frequency === "weekly" && (
                <div className="grid grid-cols-2 gap-2.5">
                  <Field label="Day">
                    <select
                      value={b.weeklyDay} onChange={(e) => setB({ ...b, weeklyDay: e.target.value })}
                      className={inputCls}
                    >
                      {DAYS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                    </select>
                  </Field>
                  <TimeInput
                    label="At" value={b.weeklyTime}
                    onChange={(v) => setB({ ...b, weeklyTime: v })}
                  />
                </div>
              )}
              {b.frequency === "custom" && (
                <Field label="Cron expression or shorthand">
                  <input
                    type="text" value={b.customCron}
                    onChange={(e) => setB({ ...b, customCron: e.target.value })}
                    placeholder="0 9 * * *"
                    className={`${inputCls} font-mono`}
                  />
                  <p className="text-[11px] text-[var(--tt-fg-dim)] mt-1.5">
                    Hermes accepts cron exprs, <code className="font-mono">30m</code>, <code className="font-mono">every 2h</code>, <code className="font-mono">daily 09:00</code>, ISO timestamps.
                  </p>
                </Field>
              )}
            </div>

            {schedulePreview && (
              <p className="mt-2 text-[11.5px] text-[var(--tt-fg-muted)]">
                Will be sent as: <code className="font-mono text-[var(--tt-fg)]">{schedulePreview}</code>
              </p>
            )}
          </Field>

          <Field label={noAgent ? "Prompt (ignored in no-agent mode)" : "Prompt"}>
            <textarea
              value={prompt} onChange={(e) => setPrompt(e.target.value)}
              placeholder={noAgent ? "Script stdout will be delivered verbatim — prompt is unused." : "What should the agent do at each run?"}
              rows={4}
              disabled={noAgent}
              className={`${inputCls} resize-y min-h-[88px] ${noAgent ? "opacity-50" : ""}`}
            />
          </Field>

          <Field label="Deliver to">
            <select
              value={deliver} onChange={(e) => setDeliver(e.target.value)}
              className={inputCls}
            >
              {DELIVERY_TARGETS.map((d) => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
              <option value="__custom">Custom (platform:chat_id)…</option>
            </select>
            {deliver === "__custom" && (
              <input
                type="text" value={customDeliver}
                onChange={(e) => setCustomDeliver(e.target.value)}
                placeholder="e.g. telegram:123456789"
                className={`${inputCls} mt-2 font-mono`}
              />
            )}
          </Field>

          {/* ---- Advanced ---- */}
          <div className="border-t border-[var(--tt-border)] pt-4">
            <button
              type="button"
              onClick={() => setShowAdvanced((v) => !v)}
              className="flex items-center gap-1.5 text-[12px] font-medium uppercase tracking-[0.08em] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
            >
              {showAdvanced ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              Advanced
            </button>

            {showAdvanced && (
              <div className="mt-4 space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Repeat (runs)">
                    <input
                      type="number" inputMode="numeric" min={1}
                      value={repeat} onChange={(e) => setRepeat(e.target.value)}
                      placeholder="forever"
                      className={inputCls}
                    />
                  </Field>
                  <Field label="Working directory">
                    <input
                      type="text" value={workdir}
                      onChange={(e) => setWorkdir(e.target.value)}
                      placeholder="/abs/path/to/project"
                      className={`${inputCls} font-mono`}
                    />
                  </Field>
                </div>

                <Field label="Script (optional)">
                  <select
                    value={script} onChange={(e) => setScript(e.target.value)}
                    className={inputCls}
                  >
                    <option value="">— none —</option>
                    {scriptCatalog.map((s) => (
                      <option key={s.name} value={s.name}>{s.name} ({s.kind})</option>
                    ))}
                  </select>
                  <p className="text-[11px] text-[var(--tt-fg-dim)] mt-1.5">
                    Scripts under <code className="font-mono">~/.hermes/scripts/</code>. Default: script stdout is injected into each prompt run.
                  </p>
                  {script && (
                    <label className="mt-2 flex items-center gap-2 text-[12.5px] text-[var(--tt-fg)] cursor-pointer">
                      <input
                        type="checkbox" checked={noAgent}
                        onChange={(e) => setNoAgent(e.target.checked)}
                        className="h-3.5 w-3.5 rounded-sm accent-[var(--tt-brand)]"
                      />
                      <span>No-agent mode — script <em>is</em> the job, deliver stdout verbatim</span>
                    </label>
                  )}
                </Field>

                <Field label={`Skills (${skills.length} selected)`}>
                  {skillCatalog.length === 0 ? (
                    <div className="text-[12px] text-[var(--tt-fg-dim)] italic">Loading skills…</div>
                  ) : (
                    <div className="max-h-[180px] overflow-y-auto rounded-md border border-[var(--tt-border)] bg-[var(--tt-sunken)] p-2 space-y-2">
                      {skills.length > 0 && (
                        <div className="flex flex-wrap gap-1 pb-2 border-b border-[var(--tt-border)]">
                          {skills.map((s) => (
                            <span key={s} className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-md bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                              {s}
                              <button type="button" onClick={() => toggleSkill(s)} aria-label={`Remove ${s}`}>
                                <Trash2 size={10} />
                              </button>
                            </span>
                          ))}
                        </div>
                      )}
                      {skillByCategory.map(([cat, items]) => (
                        <div key={cat}>
                          <div className="text-[10px] font-mono uppercase tracking-[0.12em] text-[var(--tt-fg-dim)] mb-1">{cat}</div>
                          <div className="flex flex-wrap gap-1">
                            {items.map((s) => {
                              const on = skills.includes(s.name);
                              return (
                                <button
                                  key={s.name}
                                  type="button"
                                  onClick={() => toggleSkill(s.name)}
                                  title={s.description}
                                  className={
                                    "inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-md border transition-colors " +
                                    (on
                                      ? "bg-indigo-500/20 text-indigo-200 border-indigo-500/40"
                                      : "bg-[var(--tt-panel)] text-[var(--tt-fg-muted)] border-[var(--tt-border)] hover:text-[var(--tt-fg)] hover:border-[var(--tt-border-strong)]")
                                  }
                                >
                                  {on ? "✓" : <Plus size={10} />} {s.name}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </Field>
              </div>
            )}
          </div>

          {error && (
            <div className="rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[12.5px] text-rose-300 whitespace-pre-wrap">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3.5 border-t border-[var(--tt-border)]">
          <Button variant="ghost" onClick={onClose} disabled={submitting}>Cancel</Button>
          <Button variant="primary" onClick={submit} disabled={!canSubmit}>
            {submitting ? (isEdit ? "Saving…" : "Creating…") : (isEdit ? "Save changes" : "Create schedule")}
          </Button>
        </div>
      </div>
    </div>
  );
}

const inputCls =
  "w-full h-9 px-3 rounded-md bg-[var(--tt-sunken)] border border-[var(--tt-border-strong)] text-[13px] text-[var(--tt-fg)] placeholder:text-[var(--tt-fg-dim)] focus:outline-none focus:border-[var(--tt-border-focus)] transition-colors";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--tt-fg-muted)] mb-1.5">
        {label}
      </span>
      {children}
    </label>
  );
}

function NumberInput({ label, value, onChange, min = 1 }: {
  label: string; value: string; onChange: (v: string) => void; min?: number;
}) {
  return (
    <Field label={label}>
      <input
        type="number" inputMode="numeric" min={min}
        value={value} onChange={(e) => onChange(e.target.value)}
        className={inputCls}
      />
    </Field>
  );
}

function TimeInput({ label, value, onChange }: {
  label: string; value: string; onChange: (v: string) => void;
}) {
  return (
    <Field label={label}>
      <input
        type="time" value={value} onChange={(e) => onChange(e.target.value)}
        className={inputCls}
      />
    </Field>
  );
}
