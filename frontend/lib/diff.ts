// A word-level diff between two texts, for showing what a version or a proposed fix changes.
// Plain longest-common-subsequence: episodes are under 1,000 words, so the table stays small.

export interface DiffPart {
  kind: "same" | "added" | "removed";
  text: string;
}

export function wordDiff(before: string, after: string): DiffPart[] {
  const a = tokens(before);
  const b = tokens(after);
  const table = lcsTable(a, b);
  const parts: DiffPart[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      push(parts, "same", a[i]);
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      push(parts, "removed", a[i]);
      i += 1;
    } else {
      push(parts, "added", b[j]);
      j += 1;
    }
  }
  a.slice(i).forEach((word) => push(parts, "removed", word));
  b.slice(j).forEach((word) => push(parts, "added", word));
  return parts;
}

/** Words with the whitespace after them, so joining the parts gives the text back. */
function tokens(text: string): string[] {
  return text.match(/\S+\s*/g) ?? [];
}

function lcsTable(a: string[], b: string[]): number[][] {
  const table = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  return table;
}

function push(parts: DiffPart[], kind: DiffPart["kind"], text: string) {
  const last = parts[parts.length - 1];
  if (last && last.kind === kind) last.text += text;
  else parts.push({ kind, text });
}
