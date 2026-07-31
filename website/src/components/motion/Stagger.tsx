"use client";
/**
 * Stagger — once-only in-view container that staggers its `Stagger.Item`
 * children. Container owns the trigger + gap; items own the per-child motion.
 * Never stagger more than 8 items individually; group the rest.
 * Reduced motion: items collapse to a 200ms opacity fade, no gap.
 *
 * Uses the same visibility safety nets as Reveal (see useRevealed): after an
 * instant jump (hash link, End key) or 1200ms of unrevealed intersection,
 * the container snaps to "show" and items render with no transition or gap.
 */
import { createContext, useContext, type ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import { useRevealed } from "./Reveal";
import { DUR, SPRING } from "./vocab";

const StaggerCtx = createContext<{ y: number; snapped: boolean }>({
  y: 16,
  snapped: false,
});

export type StaggerProps = {
  children: ReactNode;
  /** Gap between siblings in ms: 40 (dense grids), 60 (chips), 80 (rows, default). */
  gap?: 40 | 60 | 80;
  /** Rise distance for items (default 16); an Item's own `y` prop overrides. */
  y?: number;
  /** In-view threshold (default 0.15). */
  amount?: number;
  /** Delay in seconds before the first child starts. */
  delay?: number;
  className?: string;
};

function Stagger({
  children,
  gap = 80,
  y = 16,
  amount = 0.15,
  delay = 0,
  className,
}: StaggerProps) {
  const reduced = useReducedMotion();
  const { setRef, revealed, snapped } = useRevealed(amount);
  return (
    <StaggerCtx.Provider value={{ y, snapped }}>
      <motion.div
        ref={setRef}
        initial="hidden"
        animate={revealed ? "show" : "hidden"}
        variants={{
          hidden: {},
          show: {
            transition: snapped
              ? { staggerChildren: 0, delayChildren: 0 }
              : {
                  staggerChildren: reduced ? 0 : gap / 1000,
                  delayChildren: delay,
                },
          },
        }}
        className={className}
      >
        {children}
      </motion.div>
    </StaggerCtx.Provider>
  );
}

export type StaggerItemProps = {
  children: ReactNode;
  /** Overrides the container's `y` for this item. */
  y?: number;
  className?: string;
};

function Item({ children, y, className }: StaggerItemProps) {
  const reduced = useReducedMotion();
  const ctx = useContext(StaggerCtx);
  const rise = y ?? ctx.y;

  const variants = reduced
    ? {
        hidden: { opacity: 0 },
        show: {
          opacity: 1,
          transition: ctx.snapped ? { duration: 0 } : { duration: DUR.fade },
        },
      }
    : {
        hidden: { opacity: 0, y: rise },
        show: {
          opacity: 1,
          y: 0,
          transition: ctx.snapped ? { duration: 0 } : SPRING.reveal,
        },
      };

  return (
    <motion.div variants={variants} className={className}>
      {children}
    </motion.div>
  );
}

Stagger.Item = Item;
/**
 * Named export for SERVER components: the RSC client-reference proxy for the
 * default export does not carry attached properties, so `Stagger.Item` is
 * undefined across the server/client boundary. Client files may use either.
 */
export { Item as StaggerItem };
export default Stagger;
