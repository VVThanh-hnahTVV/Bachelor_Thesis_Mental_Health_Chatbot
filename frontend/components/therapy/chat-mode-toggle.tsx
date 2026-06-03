"use client";

import { cn } from "@/lib/utils";
import type { ChatMode } from "@/lib/api/chat";
import { HeliosAvatar } from "@/components/therapy/helios-avatar";
import { LunaAvatar } from "@/components/therapy/luna-avatar";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";

export interface ChatModeToggleProps {
  value: ChatMode;
  onChange: (mode: ChatMode) => void;
  disabled?: boolean;
  className?: string;
}

const MODE_LABELS: Record<ChatMode, string> = {
  psychologist: "Luna",
  medical: "Helios",
};

export function ChatModeToggle({
  value,
  onChange,
  disabled = false,
  className,
}: ChatModeToggleProps) {
  return (
    <Select
      value={value}
      onValueChange={(v) => onChange(v as ChatMode)}
      disabled={disabled}
    >
      <SelectTrigger
        className={cn(
          "h-8 w-auto gap-1.5 rounded-full border border-brand-border/60 bg-white px-2 py-0 text-xs font-medium shadow-none focus:ring-0 [&>svg]:h-3 [&>svg]:w-3",
          className
        )}
        aria-label="Select chat mode"
      >
        {value === "medical" ? (
          <HeliosAvatar size="sm" className="!h-5 !w-5" />
        ) : (
          <LunaAvatar size="sm" className="!h-5 !w-5" />
        )}
        <span>{MODE_LABELS[value]}</span>
      </SelectTrigger>
      <SelectContent align="start" side="top" className="min-w-[9rem]">
        <SelectItem value="psychologist" className="text-xs">
          <span className="flex items-center gap-2">
            <LunaAvatar size="sm" className="!h-5 !w-5" />
            Luna
          </span>
        </SelectItem>
        <SelectItem value="medical" className="text-xs">
          <span className="flex items-center gap-2">
            <HeliosAvatar size="sm" className="!h-5 !w-5" />
            Helios
          </span>
        </SelectItem>
      </SelectContent>
    </Select>
  );
}
