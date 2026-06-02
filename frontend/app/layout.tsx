import type { Metadata } from "next";
import { Inter, Noto_Serif } from "next/font/google";

import "./globals.css";
import { ConditionalFooter } from "@/components/conditional-footer";
import { Header } from "@/components/header";
import { Toaster } from "@/components/ui/toaster";
import { Providers } from "@/components/providers";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const notoSerif = Noto_Serif({
  subsets: ["latin"],
  weight: ["400", "700"],
  style: ["normal", "italic"],
  variable: "--font-noto-serif",
});

export const metadata: Metadata = {
  title: {
    default: "Find Peace of Mind | Luna & Helios",
    template: "%s | Luna & Helios",
  },
  description:
    "Luna for emotional wellness and Helios for medical information — your AI companions for support and guidance.",
  icons: {
    icon: [{ url: "/logo.png", type: "image/png" }],
    apple: [{ url: "/logo.png", type: "image/png" }],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${notoSerif.variable} font-serif antialiased bg-serene-bg text-[#2D3436]`}
      >
        <Providers>
          <Header />
          <main>{children}</main>
          <ConditionalFooter />
          <Toaster />
        </Providers>
      </body>
    </html>
  );
}
