import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn(
        "rounded-md bg-[linear-gradient(90deg,var(--tt-sunken),var(--tt-raised),var(--tt-sunken))] bg-[length:400%_100%] animate-[tt-shimmer_1.4s_infinite]",
        className,
      )}
      style={{ animationName: "tt-shimmer" }}
    />
  );
}

/* Inject keyframes once. Tailwind 4 / arbitrary keyframes via inline style fallback. */
if (typeof document !== "undefined" && !document.getElementById("tt-shimmer-kf")) {
  const style = document.createElement("style");
  style.id = "tt-shimmer-kf";
  style.textContent = `@keyframes tt-shimmer { 0% { background-position: 100% 0 } 100% { background-position: -100% 0 } }`;
  document.head.appendChild(style);
}
