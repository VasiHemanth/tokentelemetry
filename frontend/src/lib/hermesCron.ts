"use client";

import { api } from "./api";

// Mirrors the backend payload shape returned by /hermes/overview's cron_jobs[].
export interface CronJob {
  id: string;
  name: string;
  schedule: { kind?: string; value?: string; expr?: string } | null;
  schedule_display: string;
  prompt: string;
  deliver: string[];
  skills: string[];
  script: string | null;
  repeat: { times: number | null; completed: number } | null;
  state: "active" | "paused" | "completed" | string;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
  at_risk: boolean;
}

export interface CreateCronJobBody {
  schedule: string;
  prompt?: string;
  name?: string;
  deliver?: string;
  // Advanced
  skills?: string[];
  script?: string;       // file under ~/.hermes/scripts/
  no_agent?: boolean;    // watchdog mode (requires script)
  repeat?: number;       // null/undefined = forever
  workdir?: string;      // absolute path
}

export interface EditCronJobBody {
  schedule?: string;
  prompt?: string;
  name?: string;
  deliver?: string;
  skills?: string[];     // replaces the current set
  clear_skills?: boolean;
  script?: string;       // empty string clears
  no_agent?: boolean;    // true=enable, false=disable, undefined=leave
  repeat?: number;
  workdir?: string;      // empty string clears
}

export interface CronScript {
  name: string;
  size: number;
  kind: "bash" | "python";
}

export const createCronJob = (body: CreateCronJobBody) =>
  api<{ ok: true; output: string }>("/hermes/cron/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const editCronJob = (id: string, body: EditCronJobBody) =>
  api<{ ok: true; output: string }>(`/hermes/cron/jobs/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const listCronScripts = () =>
  api<{ scripts: CronScript[] }>("/hermes/cron/scripts").then((r) => r.scripts);

export interface HermesSkill {
  name: string;
  category?: string;
  description?: string;
}
export const listHermesSkills = () =>
  api<{ skills: HermesSkill[] }>("/hermes/skills").then((r) => r.skills || []);

const action = (id: string, verb: "pause" | "resume" | "run") =>
  api<{ ok: true; output: string }>(`/hermes/cron/jobs/${encodeURIComponent(id)}/${verb}`, {
    method: "POST",
  });

export const pauseCronJob = (id: string) => action(id, "pause");
export const resumeCronJob = (id: string) => action(id, "resume");
export const triggerCronJob = (id: string) => action(id, "run");

export const deleteCronJob = (id: string) =>
  api<{ ok: true; output: string }>(`/hermes/cron/jobs/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

// ---- Schedule builder ------------------------------------------------------
//
// Hermes accepts a wide DSL ("30m", "every 2h", "daily 09:00", cron exprs).
// We expose four guided forms + a "custom" cron expression escape hatch.
// Encoding rules are kept here so the modal stays presentational.

export type Frequency = "minutes" | "hourly" | "daily" | "weekly" | "custom";

export interface BuilderState {
  frequency: Frequency;
  minutesInterval: string;
  hourlyInterval: string;
  dailyTime: string; // "HH:MM"
  weeklyDay: string; // "0"-"6", Sunday = 0
  weeklyTime: string;
  customCron: string;
}

export const initialBuilder: BuilderState = {
  frequency: "daily",
  minutesInterval: "30",
  hourlyInterval: "1",
  dailyTime: "09:00",
  weeklyDay: "1",
  weeklyTime: "09:00",
  customCron: "",
};

/** Produce the schedule string for `hermes cron create`. Returns null on invalid input. */
export function encodeSchedule(b: BuilderState): string | null {
  switch (b.frequency) {
    case "minutes": {
      const n = parseInt(b.minutesInterval, 10);
      return n > 0 ? `${n}m` : null;
    }
    case "hourly": {
      const n = parseInt(b.hourlyInterval, 10);
      return n > 0 ? `every ${n}h` : null;
    }
    case "daily": {
      return /^\d{2}:\d{2}$/.test(b.dailyTime) ? `daily ${b.dailyTime}` : null;
    }
    case "weekly": {
      const [hh, mm] = b.weeklyTime.split(":");
      const day = parseInt(b.weeklyDay, 10);
      const hhN = parseInt(hh, 10);
      const mmN = parseInt(mm, 10);
      // parseInt("ab") is NaN — a falsy `!hh` check let malformed times like
      // "ab:cd" through and emitted "NaN NaN * * 1" (#53). Validate the parsed
      // numbers and their ranges instead.
      if (
        Number.isNaN(day) ||
        Number.isNaN(hhN) || hhN < 0 || hhN > 23 ||
        Number.isNaN(mmN) || mmN < 0 || mmN > 59
      ) {
        return null;
      }
      // Cron: minute hour * * day-of-week
      return `${mmN} ${hhN} * * ${day}`;
    }
    case "custom":
      return b.customCron.trim() || null;
  }
}

// Full delivery target catalog — matches hermes-desktop's `DELIVER_TARGETS`.
// The bare target name (e.g. "telegram") sends to the default configured
// destination for that platform; users can also enter `platform:chat_id`
// via the Custom option to override.
export const DELIVERY_TARGETS = [
  { value: "local",         label: "Local"         },
  { value: "origin",        label: "Origin"        },
  { value: "telegram",      label: "Telegram"      },
  { value: "discord",       label: "Discord"       },
  { value: "slack",         label: "Slack"         },
  { value: "whatsapp",      label: "WhatsApp"      },
  { value: "signal",        label: "Signal"        },
  { value: "matrix",        label: "Matrix"        },
  { value: "mattermost",    label: "Mattermost"    },
  { value: "email",         label: "Email"         },
  { value: "webhook",       label: "Webhook"       },
  { value: "sms",           label: "SMS"           },
  { value: "homeassistant", label: "Home Assistant"},
  { value: "dingtalk",      label: "DingTalk"      },
  { value: "feishu",        label: "Feishu"        },
  { value: "wecom",         label: "WeCom"         },
] as const;
