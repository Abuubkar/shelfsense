// Which words of a result's title the search's words match, so a card can show why it's there. A word matches
// when its stem equals a search word's stem ("boot" and "boots", "jacket" and "jackets").

export type Part = { text: string; hit: boolean };

const stem = (word: string) => word.toLowerCase().replace(/(es|s)$/, "");

export function highlight(title: string, terms: string): Part[] {
  const wanted = new Set(terms.split(/[^\p{L}\p{N}]+/u).filter((w) => w.length > 1).map(stem));
  return title.split(/([\p{L}\p{N}]+)/u).filter(Boolean)
    .map((text) => ({ text, hit: /[\p{L}\p{N}]/u.test(text) && wanted.has(stem(text)) }));
}
