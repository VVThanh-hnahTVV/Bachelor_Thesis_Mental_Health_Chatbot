import type { Metadata } from "next";

/** Per-route tab title (root layout applies the "| Luna & Helios" template). */
export function pageMetadata(title: string): Metadata {
  return { title };
}
