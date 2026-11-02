import type { Metadata } from "next";
import { DM_Sans, Geist, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { cookies } from "next/headers";
import { LookSwitcher } from "@/components/LookSwitcher";
import "./globals.css";

export const metadata: Metadata = { title: "Shelfsense", description: "Marketplace catalog search" };

// PROTOTYPE: one typeface per look, downloaded at build time and served from this app (next/font).
const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });
const plex = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-plex" });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-plex-mono" });
const dm = DM_Sans({ subsets: ["latin"], variable: "--font-dm" });

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const look = (await cookies()).get("look")?.value ?? "ledger";
  return (
    <html lang="en" data-look={look === "current" ? undefined : look}
          className={[geist.variable, plex.variable, plexMono.variable, dm.variable].join(" ")}>
      <body>
        {children}
        {process.env.NODE_ENV !== "production" && <LookSwitcher initial={look} />}
      </body>
    </html>
  );
}
