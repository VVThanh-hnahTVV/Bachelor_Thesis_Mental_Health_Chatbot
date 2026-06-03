import type { Metadata } from "next";
import { pageMetadata } from "@/lib/page-metadata";

export const metadata: Metadata = pageMetadata("About Luna & Helios");

export default function AboutLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
