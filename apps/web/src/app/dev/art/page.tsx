import { notFound } from "next/navigation";
import { ProductArt } from "@/components/ProductArt";

// PROTOTYPE (dev only): every product drawing, for review.
const SAMPLES: [string, string][] = [
  ["Hiking Boot", "brown"], ["Trail Shoe", "blue"], ["Wool Socks", "gray"], ["Classic Tee", "white"], ["Rain Jacket", "red"],
  ["Insulated Parka", "navy"], ["Trail Pants", "beige"], ["Running Shorts", "black"], ["Sun Hat", "green"], ["Water Bottle", "silver"],
  ["Cast Skillet", "black"], ["Yoga Mat", "purple"], ["Daypack", "orange"], ["Headphones", "pink"], ["USB Charger", "white"],
  ["Leather Wallet", "brown"], ["Dog Collar", "multicolor"], ["Throw Pillow Cover", "yellow"], ["Gift card", "gold"],
];

export default function ArtPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return (
    <main style={{ padding: 24, display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(150px,1fr))", gap: 12 }}>
      {SAMPLES.map(([title, color]) => (
        <figure key={title} style={{ margin: 0 }}>
          <div className="art-tile" style={{ borderRadius: 8 }}><ProductArt id={title} title={title} color={color} className="art" /></div>
          <figcaption style={{ fontSize: 13, marginTop: 4 }}>{title} · {color}</figcaption>
        </figure>
      ))}
    </main>
  );
}
