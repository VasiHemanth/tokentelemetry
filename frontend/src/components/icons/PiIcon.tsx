import { forwardRef } from "react";
import type { LucideIcon, LucideProps } from "lucide-react";

// Pi Coding Agent brand mark — the blocky geometric "pi" glyph from
// pi.dev/favicon.svg (viewBox 0 0 800 800). Rendered as a FILLED glyph
// (fill="currentColor") so it inherits the agent's accent color and stays solid
// on the dark theme, matching GrokIcon. The brand's rounded #09090b container
// square is intentionally dropped so it reads as an icon like the others.
const PiIcon = forwardRef<SVGSVGElement, LucideProps>(({ size, strokeWidth, ...props }, ref) => (
  <svg
    ref={ref}
    xmlns="http://www.w3.org/2000/svg"
    width={size ?? 24}
    height={size ?? 24}
    viewBox="0 0 800 800"
    fill="currentColor"
    stroke="none"
    {...props}
  >
    <path
      fillRule="evenodd"
      d="M165.29 165.29H517.36V400H400V517.36H282.65V634.72H165.29ZM282.65 282.65V400H400V282.65Z"
    />
    <path d="M517.36 400H634.72V634.72H517.36Z" />
  </svg>
));
PiIcon.displayName = "PiIcon";

export default PiIcon as LucideIcon;
