import type { Metadata } from "next";
import { pageMetadata } from "@/lib/page-metadata";

export const metadata: Metadata = pageMetadata("Sign Up");

export default function SignupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
