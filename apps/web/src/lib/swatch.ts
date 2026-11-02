// Base colours as fills for the product drawings (ProductArt); the catalog has no photos yet.
export const SWATCH: Record<string, string> = {
  black: "#222", white: "#e9e8e2", gray: "#9a9a96", brown: "#7a5232", beige: "#d9c7a3", red: "#c8312f", pink: "#e98cb2",
  orange: "#ec7a26", yellow: "#efc63a", green: "#3f8f4e", blue: "#2f6fd0", navy: "#1f2f5c", purple: "#7c4bb3",
  gold: "#c9a227", silver: "#c3c7cc", multicolor: "linear-gradient(135deg,#e54,#fc3,#4b7,#38d)",
};
export const swatch = (color?: string | null) => (color && SWATCH[color]) || "#b9b7ae";
