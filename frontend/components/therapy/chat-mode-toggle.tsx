"use client";

import { cn } from "@/lib/utils";
import type { ChatMode } from "@/lib/api/chat";

export interface ChatModeToggleProps {
  value: ChatMode;
  onChange: (mode: ChatMode) => void;
  disabled?: boolean;
  className?: string;
}

export function ChatModeToggle({
  value,
  onChange,
  disabled = false,
  className,
}: ChatModeToggleProps) {
  return (
    <div
      className={cn(
        "flex shrink-0 rounded-full border border-brand-border/80 bg-white p-0.5 text-xs font-medium",
        disabled && "pointer-events-none opacity-50",
        className
      )}
      role="group"
      aria-label="Chat mode"
    >
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange("psychologist")}
        className={cn(
          "rounded-full px-3 py-2 transition-colors",
          value === "psychologist"
            ? "bg-brand text-white"
            : "text-gray-600 hover:bg-brand-light"
        )}
      >
        Psychologist
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange("medical")}
        className={cn(
          "rounded-full px-3 py-2 transition-colors",
          value === "medical"
            ? "bg-slate-700 text-white"
            : "text-gray-600 hover:bg-gray-100"
        )}
      >
        Helios
      </button>
    </div>
  );
}
