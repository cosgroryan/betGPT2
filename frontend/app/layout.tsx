import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Shell from "@/components/Shell";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "VAL-TRACK Terminal",
  description: "ML-powered horse racing value finder — AU & NZ thoroughbreds",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} h-full`}>
      <body className="h-full flex flex-col bg-[#111316] text-[#e2e2e6]">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
