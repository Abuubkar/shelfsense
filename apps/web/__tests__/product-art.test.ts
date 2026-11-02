import { kindOf } from "@/components/ProductArt";
import { highlight } from "@/lib/highlight";

test("the drawing's kind comes from the title, then the category, else a plain tag", () => {
  expect(kindOf("EVERYDAY HIKING BOOT")).toBe("boot");
  expect(kindOf("Ridgeway Packable Parka, M")).toBe("parka");
  expect(kindOf("CLASSIC THROW PILLOW COVER")).toBe("pillow");
  expect(kindOf("Trail 2", "Apparel & Accessories > Clothing > Shorts")).toBe("shorts");
  expect(kindOf("Gift card")).toBe("tag");
});

test("search words are marked in the title by stem, case-insensitively", () => {
  const hits = (title: string, terms: string) => highlight(title, terms).filter((p) => p.hit).map((p) => p.text);
  expect(hits("Merrell Moab 3 Hiking Boot", "merrell hiking boots")).toEqual(["Merrell", "Hiking", "Boot"]);
  expect(hits("PACKABLE JACKET", "jackets")).toEqual(["JACKET"]);
  expect(hits("Wool Socks", "x")).toEqual([]); // one-letter words never match
  expect(highlight("A-B", "b").map((p) => p.text).join("")).toBe("A-B"); // nothing lost
});
