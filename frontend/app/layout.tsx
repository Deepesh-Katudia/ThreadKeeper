import type { Metadata } from "next";
import { Inter_Tight, Source_Serif_4 } from "next/font/google";

import { AppShell } from "@/components/AppShell";
import "./globals.css";

const ui = Inter_Tight({ subsets: ["latin"], variable: "--font-ui" });
const prose = Source_Serif_4({ subsets: ["latin"], variable: "--font-prose" });

export const metadata: Metadata = {
  title: "Threadkeeper",
  description: "An agentic serial story writer with a human in the loop",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" data-theme="dark" className={`${ui.variable} ${prose.variable} h-full`} suppressHydrationWarning>
      <body className="h-full overflow-hidden">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
