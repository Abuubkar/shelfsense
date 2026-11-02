// Highlighting the words an attribute was read from. The API's offsets count Unicode code points, so the text is
// split with Array.from (code points), not indexed directly (UTF-16 units): an emoji before the quote would
// otherwise shift every highlight.

export type Span = { start: number; end: number };
export type Segment = { text: string; marked: boolean };

export function segments(text: string, spans: Span[]): Segment[] {
  const chars = Array.from(text);
  const out: Segment[] = [];
  let at = 0;
  for (const { start, end } of [...spans].sort((a, b) => a.start - b.start)) {
    if (start < at || end > chars.length) continue; // overlapping or out of range: leave unmarked
    if (start > at) out.push({ text: chars.slice(at, start).join(""), marked: false });
    out.push({ text: chars.slice(start, end).join(""), marked: true });
    at = end;
  }
  if (at < chars.length) out.push({ text: chars.slice(at).join(""), marked: false });
  return out;
}
