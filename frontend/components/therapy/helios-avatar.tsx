"use client";

import Image from "next/image";
import { cn } from "@/lib/utils";

interface HeliosAvatarProps {
  className?: string;
  size?: "sm" | "md" | "lg";
}

const sizeMap = {
  sm: "h-10 w-10",
  md: "h-11 w-11",
  lg: "h-20 w-20",
} as const;

const pixelMap = {
  sm: 40,
  md: 44,
  lg: 80,
} as const;

export function HeliosAvatar({ className, size = "sm" }: HeliosAvatarProps) {
  const px = pixelMap[size];
  return (
    <span
      className={cn(
        "relative inline-flex shrink-0 bg-transparent",
        sizeMap[size],
        className
      )}
    >
      <Image
        src="/helios.png"
        alt="Helios"
        width={px}
        height={px}
        className="h-full w-full object-contain"
      />
    </span>
  );
}
