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
    default: "Tra cứu & tư vấn sức khỏe tâm thần | Helios",
    template: "%s | Helios",
  },
  description:
    "Helios — nền tảng hỗ trợ tra cứu và tư vấn sức khỏe tâm thần với AI, bài tập thư giãn và thông tin tham khảo dễ hiểu.",
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
    <html lang="vi" suppressHydrationWarning>
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
