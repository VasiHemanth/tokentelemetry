/**
 * Skill calls, marked once for every harness.
 *
 * Each harness loads a skill through an ordinary tool call with its own name
 * (Claude and Qoder `Skill`, Gemini `activate_skill`, Hermes `skill_view`,
 * OpenCode `skill`). Adapters build those as tool spans; this pass turns them
 * into skill spans so the tree, swimlanes and filters can treat them like
 * subagents instead of burying them among Bash and Read calls.
 */
import type { TraceSpan } from "./types";

const SKILL_TOOLS = new Set(["skill", "activate_skill", "skill_view", "load_skill", "use_skill"]);

function nameOf(input: unknown): string | undefined {
  if (!input || typeof input !== "object") return undefined;
  const o = input as Record<string, unknown>;
  for (const k of ["skill", "name", "skill_name", "command"]) {
    const v = o[k];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return undefined;
}

function argsOf(input: unknown): unknown {
  if (!input || typeof input !== "object") return input;
  const o = input as Record<string, unknown>;
  return o.args ?? o.arguments ?? o.prompt ?? input;
}

export function isSkillTool(title: string): boolean {
  return SKILL_TOOLS.has(title.toLowerCase());
}

/** Returns a new tree; spans that are not skill calls keep their identity. */
export function markSkills(spans: TraceSpan[]): TraceSpan[] {
  return spans.map(function mark(s: TraceSpan): TraceSpan {
    const mapped = s.children.map(mark);
    const children = mapped.every((c, i) => c === s.children[i]) ? s.children : mapped;
    if (s.kind === "tool" && isSkillTool(s.title)) {
      const name = nameOf(s.content?.input) ?? s.label ?? s.title;
      const args = argsOf(s.content?.input);
      return {
        ...s,
        kind: "skill",
        title: name,
        label: typeof args === "string" && args !== name ? args.replace(/\s+/g, " ").slice(0, 120) : undefined,
        content: { ...s.content, input: args },
        skill: { name, via: "tool" },
        children,
      };
    }
    return children === s.children ? s : { ...s, children };
  });
}
