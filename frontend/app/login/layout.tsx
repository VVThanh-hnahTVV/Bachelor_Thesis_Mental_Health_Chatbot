import type { Metadata } from "next";
import { pageMetadata } from "@/lib/page-metadata";

export const metadata: Metadata = pageMetadata("Sign In");

export default function LoginLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
