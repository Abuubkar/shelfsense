import { swatch } from "@/lib/swatch";

// The catalog has no photographs, so a product is drawn: a flat picture of its kind (read from the title, or the
// category when it has one) in its own base colour. Honest about being a drawing, never a fake product shot.

type Kind = keyof typeof SHAPES;

const KINDS: [RegExp, Kind][] = [
  [/\bboots?\b/, "boot"], [/\b(shoes?|sneakers?|trainers?)\b/, "shoe"], [/\bsocks?\b/, "socks"],
  [/\b(tee|t-shirt|shirt|tops?)\b/, "tee"], [/\bparka\b/, "parka"], [/\b(jackets?|coats?|outerwear)\b/, "jacket"],
  [/\b(pants|trousers)\b/, "pants"], [/\bshorts\b/, "shorts"], [/\b(hats?|caps?|beanie)\b/, "hat"],
  [/\b(bottles?|flask)\b/, "bottle"], [/\b(skillets?|pans?|cookware)\b/, "skillet"], [/\bmats?\b/, "mat"],
  [/\b(daypack|backpacks?|bags?)\b/, "daypack"], [/\b(headphones|headsets?)\b/, "headphones"],
  [/\b(chargers?|adapters?)\b/, "charger"], [/\bwallets?\b/, "wallet"], [/\b(collars?|harness(es)?)\b/, "collar"],
  [/\b(pillows?|cushions?)\b/, "pillow"],
];

export function kindOf(title: string, categoryPath?: string | null): Kind {
  for (const text of [title.toLowerCase(), (categoryPath ?? "").toLowerCase()]) {
    for (const [pattern, kind] of KINDS) if (pattern.test(text)) return kind;
  }
  return "tag";
}

const line = { fill: "none", stroke: "rgba(0,0,0,.32)", strokeWidth: 1.6, strokeLinecap: "round" as const };
const shade = "rgba(0,0,0,.18)", dark = "rgba(0,0,0,.62)", light = "rgba(255,255,255,.4)";

// Each shape draws on a 100×80 box with `fill` as the product's colour.
const SHAPES = {
  boot: (fill: string) => <>
    <path d="M31 12Q31 8 35 8H48Q52 8 52 12V41L71 47Q83 51 83 60V65H27V30Q27 20 31 12Z" fill={fill} />
    <path d="M31 12Q31 8 35 8H48Q52 8 52 12V15H31Z" fill={shade} />
    <path d="M67 47.5Q83 51 83 60V65H63Q60 54 67 47.5Z" fill={shade} />
    <rect x="24" y="65" width="62" height="8" rx="2.5" fill={dark} />
    <path d="M37 21H46M37 27H46M37 33H46M37 39H46" {...line} />
    <path d="M32 69H36M42 69H46M52 69H56M62 69H66M72 69H76" stroke="rgba(255,255,255,.25)" strokeWidth={1.4} />
  </>,
  shoe: (fill: string) => <>
    <path d="M16 46Q17 34 30 34L45 36Q54 45 69 47Q85 49 85 58V63H16Z" fill={fill} />
    <path d="M68 47Q85 49 85 58V63H64Q62 53 68 47Z" fill={shade} />
    <rect x="13" y="63" width="75" height="7" rx="2.5" fill={dark} />
    <path d="M36 39L41 44M42 38L47 44M48 41L52 46" {...line} />
  </>,
  socks: (fill: string) => <>
    <path d="M36 8H56V42Q56 49 62 53L75 60Q83 66 77 72Q72 77 63 72L41 60Q34 56 36 47Z" fill={fill} />
    <path d="M36 8H56V17H36Z" fill={shade} />
    <path d="M65 73Q72 77 77 72Q80 68 76 63L68 58Z" fill={shade} />
  </>,
  tee: (fill: string) => <>
    <path d="M34 13L44 9Q50 15 56 9L66 13L83 25L75 36L67 31V71H33V31L25 36L17 25Z" fill={fill} />
    <path d="M44 9Q50 17 56 9" {...line} />
  </>,
  jacket: (fill: string) => <>
    <path d="M34 11L44 8Q50 13 56 8L66 11L80 21L85 66H74L70 34V72H30V34L26 66H15L20 21Z" fill={fill} />
    <path d="M50 12V72M37 52H45M55 52H63" {...line} />
  </>,
  parka: (fill: string) => <>
    <path d="M37 13Q37 2 50 2Q63 2 63 13" fill={fill} stroke="rgba(0,0,0,.32)" strokeWidth={1.6} />
    <path d="M34 12L44 9Q50 14 56 9L66 12L80 22L85 70H74L70 36V77H30V36L26 70H15L20 22Z" fill={fill} />
    <path d="M50 13V77M35 56H45V64H35ZM55 56H65V64H55Z" {...line} />
  </>,
  pants: (fill: string) => <>
    <path d="M32 9H68L73 73H56L50 30L44 73H27Z" fill={fill} />
    <path d="M32 16H68M50 16V28" {...line} />
  </>,
  shorts: (fill: string) => <>
    <path d="M27 18H73L78 56H57L50 35L43 56H22Z" fill={fill} />
    <path d="M27 25H73M50 25V33" {...line} />
  </>,
  hat: (fill: string) => <>
    <path d="M24 52Q24 20 51 20Q77 20 77 52Z" fill={fill} />
    <path d="M58 52H78Q94 53 96 60H58Z" fill={fill} />
    <path d="M58 52H78Q94 53 96 60H58Z" fill={shade} />
    <path d="M51 21V52M37 25Q42 38 41 52M65 25Q60 38 61 52" {...line} />
    <circle cx="51" cy="20" r="2.5" fill={dark} />
  </>,
  bottle: (fill: string) => <>
    <rect x="43" y="13" width="14" height="11" fill={fill} />
    <rect x="40" y="5" width="20" height="9" rx="2" fill={dark} />
    <rect x="37" y="22" width="26" height="53" rx="8" fill={fill} />
    <rect x="37" y="40" width="26" height="15" fill={light} />
  </>,
  skillet: (fill: string) => <>
    <rect x="60" y="39" width="36" height="9" rx="4.5" fill={dark} />
    <circle cx="38" cy="44" r="26" fill={fill} />
    <circle cx="38" cy="44" r="19" fill={shade} />
  </>,
  mat: (fill: string) => <>
    <path d="M14 30H72V58H14Q8 58 8 44Q8 30 14 30Z" fill={fill} />
    <ellipse cx="72" cy="44" rx="9" ry="14" fill={fill} stroke="rgba(0,0,0,.32)" strokeWidth={1.6} />
    <path d="M72 44m-3 0a3 4 0 1 0 6 0a6 8 0 1 0-12 0" {...line} />
    <path d="M30 30V58M54 30V58" stroke={dark} strokeWidth={3} />
  </>,
  daypack: (fill: string) => <>
    <path d="M44 10Q50 2 56 10" fill="none" stroke={dark} strokeWidth={3} />
    <path d="M29 22Q29 10 50 10Q71 10 71 22V70Q71 75 66 75H34Q29 75 29 70Z" fill={fill} />
    <rect x="35" y="44" width="30" height="23" rx="5" fill={shade} />
    <path d="M35 50H65" {...line} />
  </>,
  headphones: (fill: string) => <>
    <path d="M24 52V40Q24 14 50 14Q76 14 76 40V52" fill="none" stroke={fill} strokeWidth={7} strokeLinecap="round" />
    <path d="M24 52V40Q24 14 50 14Q76 14 76 40V52" {...line} />
    <rect x="15" y="44" width="17" height="26" rx="7" fill={fill} />
    <rect x="68" y="44" width="17" height="26" rx="7" fill={fill} />
    <rect x="15" y="44" width="17" height="26" rx="7" fill={shade} />
    <rect x="68" y="44" width="17" height="26" rx="7" fill={shade} />
  </>,
  charger: (fill: string) => <>
    <rect x="38" y="12" width="5" height="12" rx="1" fill={dark} />
    <rect x="53" y="12" width="5" height="12" rx="1" fill={dark} />
    <rect x="30" y="23" width="36" height="40" rx="7" fill={fill} />
    <path d="M48 63Q48 76 70 74" fill="none" stroke={dark} strokeWidth={3} strokeLinecap="round" />
    <circle cx="48" cy="43" r="4" fill={shade} />
  </>,
  wallet: (fill: string) => <>
    <rect x="18" y="22" width="64" height="42" rx="6" fill={fill} />
    <path d="M18 34H82" {...line} />
    <rect x="60" y="34" width="24" height="14" rx="4" fill={fill} />
    <rect x="60" y="34" width="24" height="14" rx="4" fill={shade} />
    <circle cx="74" cy="41" r="2.5" fill={dark} />
  </>,
  collar: (fill: string) => <>
    <ellipse cx="50" cy="42" rx="31" ry="19" fill="none" stroke="rgba(0,0,0,.32)" strokeWidth={11} />
    <ellipse cx="50" cy="42" rx="31" ry="19" fill="none" stroke={fill} strokeWidth={8} />
    <rect x="41" y="55" width="18" height="10" rx="2" fill="none" stroke="#9a9a96" strokeWidth={3} />
    <circle cx="50" cy="72" r="5" fill="#c9a227" />
  </>,
  pillow: (fill: string) => <>
    <path d="M20 18Q50 12 80 18Q87 41 80 64Q50 70 20 64Q13 41 20 18Z" fill={fill} />
    <path d="M27 25Q50 21 73 25Q78 41 73 57Q50 61 27 57Q22 41 27 25Z" fill="none" stroke="rgba(0,0,0,.2)" strokeWidth={1.4} strokeDasharray="3 3" />
  </>,
  tag: (fill: string) => <>
    <path d="M30 16H62L80 40L62 64H30Z" fill={fill} />
    <circle cx="64" cy="40" r="4" fill="rgba(255,255,255,.7)" />
  </>,
};

/** A drawing of the product. `id` keeps the multicolour gradient's SVG id unique on the page. */
export function ProductArt({ id, title, color, categoryPath, className }: {
  id: string; title: string; color?: string | null; categoryPath?: string | null; className?: string;
}) {
  const kind = kindOf(title, categoryPath);
  const multi = color === "multicolor";
  const gid = `g-${id.replace(/[^\w-]/g, "_")}`;
  const fill = multi ? `url(#${gid})` : swatch(color);
  return (
    <svg className={className} viewBox="0 0 100 80" role="img" aria-label={`Drawing of a ${color ? color + " " : ""}${kind === "tag" ? "product" : kind}`}>
      {multi && (
        <defs><linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#e5484d" /><stop offset=".35" stopColor="#efc63a" />
          <stop offset=".65" stopColor="#3f8f4e" /><stop offset="1" stopColor="#2f6fd0" />
        </linearGradient></defs>
      )}
      {/* The CSS gives this group a hairline edge, so white and silver products still read on a pale tile. */}
      <g strokeLinejoin="round">{SHAPES[kind](fill)}</g>
    </svg>
  );
}
