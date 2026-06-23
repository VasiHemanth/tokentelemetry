"use client";

import {
  createContext, useContext, useCallback, useEffect, useRef, useState,
} from "react";

import {
  getNotifications, markToasted, markRead, clearNotifications,
  type AppNotification, type NotificationFeed,
} from "@/lib/notifications";

/**
 * Single source of truth for the notification feed, shared by the sidebar bell
 * and the one-time banner. Polls every 60s. Owns the "surface once" rule:
 * whenever the backend reports `to_toast` rows, they're handed to the banner
 * (via `toToast`) exactly once and immediately marked toasted server-side so
 * they never re-surface actively — they just persist in the bell.
 */
interface NotifCtx {
  feed: NotificationFeed;
  /** Rows to banner right now (cleared once acknowledged). */
  toToast: AppNotification[];
  acknowledgeToasts: () => void;
  markAllRead: () => void;
  clearAll: () => void;
  clearOne: (id: number) => void;
  refresh: () => void;
}

const EMPTY: NotificationFeed = { notifications: [], unread_count: 0, to_toast: [] };
const Ctx = createContext<NotifCtx | null>(null);

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [feed, setFeed] = useState<NotificationFeed>(EMPTY);
  const [toToast, setToToast] = useState<AppNotification[]>([]);
  const seenToToast = useRef<Set<number>>(new Set());

  const refresh = useCallback(() => {
    getNotifications()
      .then((f) => {
        setFeed(f);
        // Hand any not-yet-seen toast rows to the banner, once.
        const fresh = f.to_toast.filter((n) => !seenToToast.current.has(n.id));
        if (fresh.length) {
          fresh.forEach((n) => seenToToast.current.add(n.id));
          setToToast((prev) => [...prev, ...fresh]);
          // Flip them server-side so a reload won't re-banner the same events.
          markToasted(fresh.map((n) => n.id)).catch(() => { /* best effort */ });
        }
      })
      .catch(() => { /* backend down — keep last good feed */ });
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 60_000);
    return () => clearInterval(id);
  }, [refresh]);

  const acknowledgeToasts = useCallback(() => setToToast([]), []);

  const markAllRead = useCallback(() => {
    setFeed((f) => ({
      ...f,
      unread_count: 0,
      notifications: f.notifications.map((n) => ({ ...n, read: true })),
    }));
    markRead().then(refresh).catch(() => { /* best effort */ });
  }, [refresh]);

  const clearAll = useCallback(() => {
    setFeed((f) => ({ ...f, notifications: [], unread_count: 0 }));
    clearNotifications().then(refresh).catch(() => { /* best effort */ });
  }, [refresh]);

  const clearOne = useCallback((id: number) => {
    setFeed((f) => {
      const target = f.notifications.find((n) => n.id === id);
      return {
        ...f,
        notifications: f.notifications.filter((n) => n.id !== id),
        unread_count: Math.max(0, f.unread_count - (target && !target.read ? 1 : 0)),
      };
    });
    clearNotifications([id]).then(refresh).catch(() => { /* best effort */ });
  }, [refresh]);

  return (
    <Ctx.Provider value={{
      feed, toToast, acknowledgeToasts, markAllRead, clearAll, clearOne, refresh,
    }}>
      {children}
    </Ctx.Provider>
  );
}

export function useNotifications(): NotifCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useNotifications must be used inside <NotificationProvider>");
  return v;
}
