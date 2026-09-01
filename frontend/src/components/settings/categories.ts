"use client";

/**
 * Settings category model. Each top-level category groups related options; a
 * category's `items` are the actual settings it contains, so one category can
 * hold several related controls. The Settings page wraps each category's content
 * in a `<section id="cat-<id>">` and the sidebar nav links to those anchors.
 */

export interface SettingItem {
  id: string;
  label: string;
  description: string;
}

export interface SettingCategory {
  id: string;
  label: string;
  items: SettingItem[];
}

export const SETTINGS_CATEGORIES: SettingCategory[] = [
  {
    id: "general",
    label: "General",
    items: [
      {
        id: "theme",
        label: "Theme",
        description: "Light, dark, or follow your system.",
      },
      {
        id: "dash-prefs",
        label: "Dashboard preferences",
        description: "What appears on the main dashboard.",
      },
    ],
  },
  {
    id: "agents",
    label: "Agents & AI",
    items: [
      {
        id: "summarizer",
        label: "AI trace summaries",
        description: "Which coding agent writes narrative summaries.",
      },
      {
        id: "feature-flags",
        label: "Agent feature flags",
        description: "Read-only experimental features per agent.",
      },
    ],
  },
  {
    id: "billing",
    label: "Billing & cost",
    items: [
      {
        id: "billing-mode",
        label: "Billing mode",
        description: "How each agent's cost figure is framed.",
      },
    ],
  },
  {
    id: "data",
    label: "Data & retention",
    items: [
      {
        id: "retention",
        label: "History & retention",
        description: "Archive full transcripts per agent.",
      },
    ],
  },
  {
    id: "privacy",
    label: "Privacy",
    items: [
      {
        id: "usage-stats",
        label: "Anonymous usage stats",
        description: "Content-free product telemetry.",
      },
      {
        id: "update-check",
        label: "Update checks",
        description: "Hourly release check against GitHub.",
      },
    ],
  },
  {
    id: "access",
    label: "Access",
    items: [
      {
        id: "connect-device",
        label: "Connect a device",
        description: "Remote access from another device.",
      },
    ],
  },
  {
    id: "shortcuts",
    label: "Keyboard shortcuts",
    items: [
      {
        id: "shortcut-reference",
        label: "Shortcut reference",
        description: "View and rebind navigation shortcuts.",
      },
    ],
  },
];

export function categoryAnchor(id: string): string {
  return `cat-${id}`;
}
