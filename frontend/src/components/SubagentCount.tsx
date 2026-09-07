import { GitBranch } from "lucide-react";
import { Badge } from "@/components/ui";

export interface SubagentCountProps {
  /** Direct children of this session that are present in the same list. */
  count: number;
  /** Rendered as a plain chip when false — used where the row is already a link. */
  title?: string;
}

/**
 * "⑃ 158" chip marking a session that spawned children.
 *
 * Deliberately absent at count 0 rather than rendering a zero: most sessions
 * delegate nothing, and a column of `⑃ 0` would be noise on every ordinary row.
 * `GitBranch` rather than the `Users` icon used by the project header's
 * "Subagents" stat — that stat counts CONFIGURED agent definitions plus
 * in-transcript Task calls, which is a different number from the child
 * sessions counted here, and reusing its icon would imply they match.
 */
export function SubagentCount({ count, title }: SubagentCountProps) {
  if (count <= 0) return null;
  return (
    <Badge
      variant="brand"
      title={title ?? `Spawned ${count} subagent session${count === 1 ? "" : "s"}`}
      className="tabular-nums"
    >
      <GitBranch size={10} />
      {count}
    </Badge>
  );
}
