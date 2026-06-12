"use client";

import { Headphones, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface HandoffButtonProps {
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
  className?: string;
}

export function HandoffButton({
  onClick,
  disabled = false,
  loading = false,
  className,
}: HandoffButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      onClick={onClick}
      className={cn(
        "relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-brand-border/60 bg-white text-gray-600 transition-colors hover:bg-brand-light hover:text-brand disabled:opacity-50",
        className
      )}
      aria-label="Liên hệ chuyên viên"
      title="Liên hệ chuyên viên"
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <Headphones className="h-4 w-4" />
      )}
    </button>
  );
}
