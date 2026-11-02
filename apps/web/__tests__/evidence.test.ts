import { segments } from "@/lib/evidence";

describe("evidence highlighting", () => {
  it("counts code points, so an emoji before the quote doesn't shift the highlight", () => {
    // The API's offsets for "Blk/Gry" are 14..21 in code points; in UTF-16 units they would be 17..24.
    const text = "🔥🔥 HOT DEAL 🔥 Blk/Gry trail runner";
    expect(segments(text, [{ start: 14, end: 21 }]).filter((s) => s.marked).map((s) => s.text)).toEqual(["Blk/Gry"]);
  });

  it("keeps combining accents with their letter", () => {
    const text = "Café au lait mug";
    expect(segments(text, [{ start: 0, end: 5 }])[0]).toEqual({ text: "Café", marked: true });
  });

  it("orders several spans and leaves the rest unmarked", () => {
    expect(segments("Mens Merino Tee", [{ start: 5, end: 11 }, { start: 0, end: 4 }])).toEqual([
      { text: "Mens", marked: true }, { text: " ", marked: false }, { text: "Merino", marked: true }, { text: " Tee", marked: false },
    ]);
  });
});
