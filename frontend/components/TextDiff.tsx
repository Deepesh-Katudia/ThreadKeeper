import { wordDiff } from "@/lib/diff";

/** Two texts as one, with removed words struck through in red and added words in green. */
export function TextDiff({ before, after }: { before: string; after: string }) {
  const parts = wordDiff(before, after);
  if (parts.every((p) => p.kind === "same")) {
    return <p className="text-xs text-faint">No differences.</p>;
  }
  return (
    <div className="prose-episode text-sm">
      {parts.map((part, i) =>
        part.kind === "same" ? (
          <span key={i}>{part.text}</span>
        ) : part.kind === "removed" ? (
          <del key={i} className="bg-red-500/15 text-red-300 decoration-red-400/60">{part.text}</del>
        ) : (
          <ins key={i} className="bg-emerald-500/15 text-emerald-300 no-underline">{part.text}</ins>
        ),
      )}
    </div>
  );
}

/** A find/replace patch as a two-column before/after table. */
export function PatchEdits({ edits }: { edits: { find: string; replace: string }[] }) {
  return (
    <ul className="divide-y divide-line rounded-lg border border-line text-sm">
      {edits.map((edit, i) => (
        <li key={i} className="grid gap-2 px-3 py-2 md:grid-cols-2 md:gap-4">
          <span className="break-words text-red-300 line-through decoration-red-400/60">{edit.find}</span>
          <span className="break-words text-emerald-300">{edit.replace}</span>
        </li>
      ))}
    </ul>
  );
}

/** A passage of the episode with the conflicting quote highlighted, plus a little text either side. */
export function QuoteInContext({ text, quote }: { text: string; quote: string }) {
  const at = text.indexOf(quote);
  if (at === -1) return <mark className="bg-amber-500/20 text-fg">{quote}</mark>;
  const start = Math.max(0, at - CONTEXT_CHARS);
  const end = Math.min(text.length, at + quote.length + CONTEXT_CHARS);
  return (
    <span className="text-muted">
      {start > 0 && "…"}
      {text.slice(start, at)}
      <mark className="rounded-sm bg-amber-500/25 px-0.5 text-fg">{quote}</mark>
      {text.slice(at + quote.length, end)}
      {end < text.length && "…"}
    </span>
  );
}

const CONTEXT_CHARS = 140;
