import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AlphaCrafter",
  description: "Local control console for the AlphaCrafter multi-agent trading framework.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
