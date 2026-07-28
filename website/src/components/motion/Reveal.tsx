"use client";
/**
 * Reveal — the workhorse once-only in-view entrance.
 * opacity 0→1, y→0 on spring 300/34, `viewport={{ once: true, amount }}`.
 * Reduced motion: 200ms opacity fade, no translate.
 */
import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import { DUR, SPRING } from "./vocab";

const TAGS = {
  div: motion.div,
  section: motion.section,
  header: motion.header,
  span: motion.span,
  p: motion.p,
  ul: motion.ul,
  li: motion.li,
} as const;

export type RevealProps = {
  children: ReactNode;
  /** Rise distance: 8 (chips), 16 (text blocks, default), 24 (cards/media). */
  y?: 8 | 16 | 24;
  /** Delay in seconds. */
  delay?: number;
  /** In-view threshold (default 0.3). */
  amount?: number;
  /** Rendered element (default "div"). */
  as?: keyof typeof TAGS;
  className?: string;
};

export default function Reveal({
  children,
  y = 16,
  delay = 0,
  amount = 0.3,
  as = "div",
  className,
}: RevealProps) {
  const reduced = useReducedMotion();
  const Tag = TAGS[as];

  if (reduced) {
    return (
      <Tag
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true, amount }}
        transition={{ duration: DUR.fade, delay }}
        className={className}
      >
        {children}
      </Tag>
    );
  }

  return (
    <Tag
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount }}
      transition={{ ...SPRING.reveal, delay }}
      className={className}
    >
      {children}
    </Tag>
  );
}
