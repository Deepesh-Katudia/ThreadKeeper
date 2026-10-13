import { Button } from "@/components/ui";
import { EpisodeBrief, RippleBrief } from "@/lib/api";

const GATE_LABELS: Record<string, string> = {
  confirm_memory: "Step 1 of 3: confirm what changes in memory",
  scanning: "Checking later episodes…",
  reviewing: "Step 2 of 3: review the later episodes",
  replan_review: "Step 3 of 3: approve the new upcoming beats",
};

/** The banner across the Episodes page while a ripple is open. */
export function RippleBanner({ ripple, onReview }: { ripple: RippleBrief; onReview: () => void }) {
  const { counts } = ripple;
  const checked = counts.unaffected + counts.minor + counts.major + counts.recheck;
  const needsYou = counts.waiting - counts.minor;
  const parts = [
    needsYou > 0 && `${needsYou} need${needsYou === 1 ? "s" : ""} your decision`,
    counts.minor > 0 && `${counts.minor} minor`,
    counts.unaffected > 0 && `${counts.unaffected} unaffected`,
    counts.decided > 0 && `${counts.decided} decided`,
  ].filter(Boolean);
  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-xs text-amber-200">
      <span className="min-w-0 flex-1 break-words">
        ⚠ Episode {ripple.source_episode} was changed (v{ripple.from_version} → v{ripple.to_version}).
        {ripple.status !== "confirm_memory" && ` ${checked} later episode${checked === 1 ? "" : "s"} checked${parts.length ? `: ${parts.join(" · ")}` : ""}.`}
        {" "}Writing is paused until you finish. <b className="font-medium">{GATE_LABELS[ripple.status]}</b>
        {ripple.summary && <span className="block text-amber-300/80">{ripple.summary}</span>}
      </span>
      <Button variant="primary" onClick={onReview}>Review changes</Button>
    </div>
  );
}

/** The ripple outcome for one episode in the list, as a short coloured label. */
export function ContinuityBadge({ episode, openRipple }: { episode: EpisodeBrief; openRipple: RippleBrief | null }) {
  const label = continuityLabel(episode, openRipple);
  if (!label) return null;
  return <span className={`text-[11px] ${label.tone}`}>{label.text}</span>;
}

function continuityLabel(episode: EpisodeBrief, openRipple: RippleBrief | null): { text: string; tone: string } | null {
  if (openRipple && openRipple.source_episode === episode.number) {
    return { text: `edited · v${openRipple.to_version}`, tone: "text-violet-400" };
  }
  const c = episode.continuity;
  if (!c) {
    return episode.current_version && episode.current_version > 1
      ? { text: `edited · v${episode.current_version}`, tone: "text-violet-400" }
      : null;
  }
  const version = c.resulting_version ? ` · v${c.resulting_version}` : "";
  if (c.decision === "accept") return { text: `${c.fix_kind === "rewrite" ? "rewritten" : "fixed"}${version}`, tone: "text-emerald-400" };
  if (c.decision === "edit") return { text: `edited${version}`, tone: "text-emerald-400" };
  if (c.decision === "keep") return { text: "kept as is", tone: "text-muted" };
  const isCurrentRipple = openRipple?.id === c.ripple_id;
  switch (c.check_status) {
    case "major":
    case "recheck":
      return { text: "🔴 needs review", tone: "text-red-400" };
    case "minor":
      return { text: "🟡 minor · fix suggested", tone: "text-amber-400" };
    case "unaffected":
      return { text: "🟢 checked · unaffected", tone: "text-emerald-400" };
    default:
      return isCurrentRipple && openRipple?.status === "scanning"
        ? { text: "⏳ checking", tone: "text-sky-400" }
        : { text: "⏳ pending (cost cap)", tone: "text-faint" };
  }
}
