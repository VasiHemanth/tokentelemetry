"use client";

import { profileHue } from "@/lib/profileColor";

/**
 * A generated mark for one spawned subagent.
 *
 * Subagents have no branding to borrow — they are anonymous children of one
 * session, often a dozen of them, and a list of a dozen identical generic
 * icons is a list you stop reading. So the mark is derived from the agent
 * itself and is stable: the same agent draws the same sigil on every render,
 * on every machine, with nothing stored.
 *
 * Shape family, element count and hue all come from the SAME seed — the task
 * the agent was given — read through three different salts so they vary
 * independently. Seeding the family off the agent TYPE instead was tried and
 * is worse in practice: a fan-out is usually a dozen children of one type, so
 * the family collapses to one silhouette repeated a dozen times, and the type
 * is already printed as text on the row. Identity is the thing the text can't
 * carry at a glance, so identity is what the mark encodes.
 *
 * Hashing is `profileHue` from lib/profileColor — the app already has one
 * name-to-hue hash and a second would drift from it.
 */

const FAMILIES = 8;

/** Evenly spaced copies of one shape around the centre, alternating tone. */
function ring(n: number, a: string, b: string, draw: (fill: string) => React.ReactNode) {
  return Array.from({ length: n }, (_, i) => (
    <g key={i} transform={`rotate(${(360 / n) * i} 12 12)`}>{draw(i % 2 ? b : a)}</g>
  ));
}

/** Rotationally symmetric marks, all drawn in a 24x24 box centred on 12,12. */
function glyph(family: number, step: number, a: string, b: string) {
  switch (family) {
    case 0: // pinwheel, 3-5 blades
      return ring(3 + step, a, b, (f) => <path d="M12 12 L12 2.5 L20 6.5 Z" fill={f} />);
    case 1: // segmented disc, 4/6/8 wedges
      return ring(4 + step * 2, a, b, (f) => (
        <path d={`M12 12 L12 2.5 A9.5 9.5 0 0 1 ${12 + 9.5 * Math.sin((2 * Math.PI) / (4 + step * 2))} ${12 - 9.5 * Math.cos((2 * Math.PI) / (4 + step * 2))} Z`} fill={f} />
      ));
    case 2: // lattice bars, 2 or 3 per axis
      return [
        ...Array.from({ length: 2 + (step % 2) }, (_, i) => (
          <rect key={`v${i}`} x={5.4 + i * (13.2 / (1 + (step % 2) + 0.35))} y="1.5"
                width="2.6" height="21" rx="1.3" fill={a} />
        )),
        <rect key="h1" x="1.5" y="7.2" width="21" height="2.6" rx="1.3" fill={b} />,
        <rect key="h2" x="1.5" y="14.2" width="21" height="2.6" rx="1.3" fill={b} />,
      ];
    case 3: // petals, 5-7 around a core
      return [
        ...ring(5 + step, a, b, (f) => <circle cx="12" cy="4.4" r="2.7" fill={f} />),
        <circle key="c" cx="12" cy="12" r="2.7" fill={b} />,
      ];
    case 4: // burst, 6/8/10 spikes
      return [
        ...ring(6 + step * 2, a, b, (f) => <path d="M12 12 L10.2 2 L13.8 2 Z" fill={f} />),
        <circle key="c" cx="12" cy="12" r="3" fill={b} />,
      ];
    case 5: // rings, 2-4 deep
      return Array.from({ length: 2 + step }, (_, i) => (
        <circle key={i} cx="12" cy="12" r={10 - i * (8 / (2 + step))} fill="none"
                stroke={i % 2 ? b : a} strokeWidth="2.6" />
      ));
    case 6: // nested diamonds, 2-4 deep
      // A square rotated 45 degrees needs side <= 24/sqrt(2) or its corners
      // clip on the viewBox and it reads as a plain rounded square.
      return Array.from({ length: 2 + step }, (_, i) => {
        const side = 16.5 - i * (12 / (2 + step));
        return (
          <rect key={i} x={12 - side / 2} y={12 - side / 2} width={side} height={side}
                rx="1.8" fill={i % 2 ? b : a} />
        );
      });
    default: { // checker, 3x3 or 4x4
      const n = 3 + (step % 2);
      const cell = 20 / n;
      return Array.from({ length: n * n }, (_, i) => {
        const row = Math.floor(i / n), col = i % n;
        return (
          <rect key={i} x={2 + col * cell} y={2 + row * cell} width={cell - 1} height={cell - 1}
                rx="1.4" fill={(row + col) % 2 ? b : a} />
        );
      });
    }
  }
}

export default function AgentSigil({
  seed, size = 26, running = false, className,
}: {
  /** Whatever identifies this agent: its task, else its phase label, else its id. */
  seed: string;
  size?: number;
  running?: boolean;
  className?: string;
}) {
  const key = seed || "agent";
  const family = profileHue(`shape:${key}`) % FAMILIES;
  const step = Math.floor(profileHue(`count:${key}`) / 120); // 0, 1 or 2
  const hue = profileHue(key);
  // Two stops, both mid-lightness: a single 58% fill (the profile-dot value)
  // washes out against a light background at this size, and the pair also
  // gives every mark the shading the shapes need to stay legible at 26px.
  const a = `hsl(${hue} 62% 58%)`;
  const b = `hsl(${(hue + 26) % 360} 58% 44%)`;

  return (
    <span
      className={className}
      style={{
        width: size, height: size, flex: "none", display: "grid", placeItems: "center",
        // No tinted plate behind the mark: at this size the plate reads as a
        // second, competing shape and its alpha shifts row to row with the hue.
        // A running child gets a ring, which is rare enough to stay a signal.
        borderRadius: running ? size * 0.3 : undefined,
        boxShadow: running ? `0 0 0 1.5px hsl(${hue} 62% 58% / 0.6)` : undefined,
      }}
    >
      <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden focusable="false">
        {/* A whole-mark rotation off the colour seed, so two agents that land on
            the same family, count and neighbouring hues still don't twin. Kept
            clear of 0 and 90: the four-fold families (diamonds, checker,
            lattice) are symmetric there and collapse into a plain square. */}
        <g transform={`rotate(${12 + (hue % 66)} 12 12)`}>{glyph(family, step, a, b)}</g>
      </svg>
    </span>
  );
}
