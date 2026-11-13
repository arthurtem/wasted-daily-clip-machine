import type { Metadata } from "next";

import Footer from "@/components/footer";

import "./globals.css";

export const metadata: Metadata = {
  title: "Wasted Daily — Review",
  description: "Review and approve Wasted Daily YouTube Shorts.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-zinc-950 text-zinc-100 antialiased">
        <div className="flex min-h-screen flex-col">
          <div className="flex-1">{children}</div>
          <Footer />
        </div>
      </body>
    </html>
  );
}
