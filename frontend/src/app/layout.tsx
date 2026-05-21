import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trading Research Scanner",
  description: "Live movers, scoring, and AI research dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
