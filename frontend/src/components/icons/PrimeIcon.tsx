import { forwardRef } from "react";
import type { LucideIcon, LucideProps } from "lucide-react";

// Prime Agent's mark: a decisive upward path ending in a four-point signal.
// Like the other local agent icons, it inherits currentColor from the UI.
const PrimeIcon = forwardRef<SVGSVGElement, LucideProps>((props, ref) => (
  <svg
    ref={ref}
    xmlns="http://www.w3.org/2000/svg"
    width={props.size ?? 24}
    height={props.size ?? 24}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={props.strokeWidth ?? 2}
    strokeLinecap="round"
    strokeLinejoin="round"
    {...props}
  >
    <path d="M4 18 10 12l3 3 7-8" />
    <path d="M16 7h4v4" />
    <path d="m7 4 .7 2.3L10 7l-2.3.7L7 10l-.7-2.3L4 7l2.3-.7L7 4Z" />
  </svg>
));
PrimeIcon.displayName = "PrimeIcon";

export default PrimeIcon as LucideIcon;
