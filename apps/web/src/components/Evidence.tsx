import { segments, type Span } from "@/lib/evidence";

/** Text with the words attributes were read from highlighted. */
export function Evidence({ text, spans }: { text: string; spans: Span[] }) {
  return <>{segments(text, spans).map((s, n) => (s.marked ? <mark key={n}>{s.text}</mark> : <span key={n}>{s.text}</span>))}</>;
}
