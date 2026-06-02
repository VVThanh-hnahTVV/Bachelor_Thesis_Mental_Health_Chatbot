import type { Metadata } from "next";
import { pageMetadata } from "@/lib/page-metadata";

export const metadata: Metadata = pageMetadata("Dashboard");

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
