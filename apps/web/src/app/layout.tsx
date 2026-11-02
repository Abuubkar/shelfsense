import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

export const metadata: Metadata = { title: "Shelfsense", description: "Marketplace catalog search" };

// Downloaded at build time and served from this app (next/font); nothing calls Google at runtime (ADR 0017).
const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={geist.variable}>
      <body>{children}</body>
    </html>
  );
}
