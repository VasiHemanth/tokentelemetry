import { forwardRef } from "react";
import type { LucideIcon, LucideProps } from "lucide-react";

// Oh My Pi (OMP) brand mark — the geometric "P"-style glyph from
// paseo.sh/omp (viewBox 4 4 56 56). Rendered as a FILLED monochrome glyph
// (fill="currentColor") so it inherits the agent's accent colour and stays
// solid on the dark theme, matching PiIcon.
const OmpIcon = forwardRef<SVGSVGElement, LucideProps>(({ size, ...props }, ref) => (
  <svg
    ref={ref}
    xmlns="http://www.w3.org/2000/svg"
    width={size ?? 24}
    height={size ?? 24}
    viewBox="4 4 56 56"
    fill="currentColor"
    stroke="none"
    {...props}
  >
    <path d="M10 14h44v9H43v33h-9V23h-9v22h-9V23H10z" />
  </svg>
));
OmpIcon.displayName = "OmpIcon";

export default OmpIcon as LucideIcon;
