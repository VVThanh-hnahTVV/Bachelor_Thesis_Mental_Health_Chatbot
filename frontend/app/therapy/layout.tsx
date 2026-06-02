import type { Metadata } from "next";
import { pageMetadata } from "@/lib/page-metadata";

export const metadata: Metadata = pageMetadata("Therapy Chat");

export default function TherapyLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="therapy-shell fixed inset-x-0 bottom-0 top-[var(--header-height)] z-0 overflow-hidden bg-brand-stone">
      {children}
    </div>
  );
}
