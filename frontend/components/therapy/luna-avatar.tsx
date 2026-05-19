"use client";

import { LunaLogo } from "@/components/luna-logo";
import { cn } from "@/lib/utils";

interface LunaAvatarProps {
  className?: string;
  size?: "sm" | "md";
}

export function LunaAvatar({ className, size = "sm" }: LunaAvatarProps) {
  const sizeClass = size === "md" ? "h-9 w-9" : "h-8 w-8";
  return (
    <LunaLogo
      className={cn(sizeClass, "shadow-none ring-brand/20", className)}
    />
  );
}
