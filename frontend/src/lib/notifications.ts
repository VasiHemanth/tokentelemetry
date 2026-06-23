"use client";

import { api } from "./api";

// ---- Notification center contract (see backend notifications.py) ----
//
// A notification is a persisted event the app surfaces to the user. It's shown
// actively ONCE (a one-time top banner, gated on `toasted`), then lives in the
// sidebar bell until read/cleared. Budget alerts are the first `kind`; the
// table is generic so other kinds can post later.

export type NotificationKind = "budget_alert" | string;
export type NotificationSeverity = "info" | "warn" | "over";

export interface AppNotification {
  id: number;
  kind: NotificationKind;
  dedup_key: string;
  severity: NotificationSeverity;
  title: string;
  body: string | null;
  href: string | null;
  created_at: string;
  toasted: boolean;
  read: boolean;
  cleared: boolean;
}

export interface NotificationFeed {
  notifications: AppNotification[];
  unread_count: number;
  /** Subset not yet actively surfaced — the banner shows these once. */
  to_toast: AppNotification[];
}

export const getNotifications = () => api<NotificationFeed>("/notifications");

/** Mark notifications as actively surfaced (so they never re-banner). Omit ids → all. */
export const markToasted = (ids?: number[]) =>
  api<{ ok: boolean; updated: number }>("/notifications/toasted", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(ids ? { ids } : {}),
  });

/** Mark notifications read (clears the unread badge). Omit ids → all. */
export const markRead = (ids?: number[]) =>
  api<{ ok: boolean; updated: number }>("/notifications/read", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(ids ? { ids } : {}),
  });

/** Clear notifications (hide from bell). Omit ids → all ("Clear all"). */
export const clearNotifications = (ids?: number[]) =>
  api<{ ok: boolean; updated: number }>("/notifications/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(ids ? { ids } : {}),
  });

/** Compact relative time, e.g. "just now", "5m", "3h", "2d". */
export function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return "";
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 45) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
