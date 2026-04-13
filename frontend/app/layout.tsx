import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cutline — Daily MLB Grid Trivia",
  description:
    "Spot the imposters. One category, 9 names, 2–4 traps. A new puzzle every day.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0f1f3b",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-navy-900 text-navy-50">{children}</body>
    </html>
  );
}
