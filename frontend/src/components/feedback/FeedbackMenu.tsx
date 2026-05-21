"use client";

import { Lightbulb, Bug, Sparkles, MessageSquare } from "lucide-react";
import { GithubMark, XMark, LinkedinMark } from "./BrandIcons";
import { usePathname } from "next/navigation";
import { discussionUrl, issueUrl, SOCIALS } from "./links";
import { cn } from "@/lib/cn";

type Props = {
  align?: "left" | "right";
  onSelect?: () => void;
};

export default function FeedbackMenu({ align = "left", onSelect }: Props) {
  const pathname = usePathname();
  const ctx = `\n\n---\n_Sent from TokenTelemetry · ${pathname}_`;

  const items = [
    {
      icon: Lightbulb,
      label: "Share an idea",
      sub: "A feature, a tweak, a wild thought",
      href: discussionUrl("ideas"),
    },
    {
      icon: Bug,
      label: "Report a bug",
      sub: "Something acting weird?",
      href: issueUrl({ labels: "bug", body: ctx }),
    },
    {
      icon: Sparkles,
      label: "Show & tell",
      sub: "Tell me how you're using it",
      href: discussionUrl("show-and-tell"),
    },
  ];

  return (
    <div
      className={cn(
        "w-[280px] rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)]/95 backdrop-blur-md shadow-2xl p-2",
        align === "right" && "origin-bottom-right",
      )}
    >
      <div className="px-2.5 pt-1.5 pb-2">
        <div className="text-[11px] font-semibold text-[var(--tt-fg)]">What&apos;s on your mind?</div>
        <div className="text-[10px] text-[var(--tt-fg-dim)] mt-0.5">
          Every signal helps me make this better.
        </div>
      </div>

      <div className="space-y-0.5">
        {items.map(({ icon: Icon, label, sub, href }) => (
          <a
            key={label}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            onClick={onSelect}
            className="flex items-start gap-3 rounded-[var(--tt-radius)] px-2.5 py-2 hover:tt-tint-1 transition-colors group"
          >
            <Icon size={14} className="mt-0.5 text-[var(--tt-fg-dim)] group-hover:text-[var(--tt-brand)]" />
            <div className="min-w-0">
              <div className="text-[12px] font-medium text-[var(--tt-fg)]">{label}</div>
              <div className="text-[10.5px] text-[var(--tt-fg-dim)]">{sub}</div>
            </div>
          </a>
        ))}
      </div>

      <div className="border-t border-[var(--tt-border)] mt-2 pt-2 pb-1 px-2.5 flex items-center gap-3">
        <span className="text-[10px] uppercase tracking-[0.16em] text-[var(--tt-fg-dim)]">Reach me</span>
        <div className="ml-auto flex items-center gap-2">
          <a href={SOCIALS.discussions} target="_blank" rel="noopener noreferrer" title="GitHub Discussions" className="text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]">
            <MessageSquare size={13} />
          </a>
          <a href={SOCIALS.github} target="_blank" rel="noopener noreferrer" title="GitHub" className="text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]">
            <GithubMark size={13} />
          </a>
          <a href={SOCIALS.twitter} target="_blank" rel="noopener noreferrer" title="X / Twitter" className="text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]">
            <XMark size={13} />
          </a>
          <a href={SOCIALS.linkedin} target="_blank" rel="noopener noreferrer" title="LinkedIn" className="text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]">
            <LinkedinMark size={13} />
          </a>
        </div>
      </div>
    </div>
  );
}
