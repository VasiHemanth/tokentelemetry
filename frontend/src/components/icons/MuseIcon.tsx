import { forwardRef } from "react";
import type { LucideIcon, LucideProps } from "lucide-react";

// A compact starburst mark for Muse Code. It uses currentColor so every
// dashboard surface can apply the shared agent accent without an image asset.
const MuseIcon = forwardRef<SVGSVGElement, LucideProps>((props, ref) => (
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
    <path d="m12 2 1.5 6.5L20 10l-6.5 1.5L12 18l-1.5-6.5L4 10l6.5-1.5L12 2Z" />
    <path d="m18.5 16 .6 2.4 2.4.6-2.4.6-.6 2.4-.6-2.4-2.4-.6 2.4-.6.6-2.4Z" />
  </svg>
));
MuseIcon.displayName = "MuseIcon";

export default MuseIcon as LucideIcon;
