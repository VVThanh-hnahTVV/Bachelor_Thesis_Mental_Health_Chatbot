"use client";

import { Loader2, Mic, Square } from "lucide-react";
import { cn } from "@/lib/utils";

interface VoiceMicButtonProps {
  toggle: () => void;
  isRecording: boolean;
  isTranscribing: boolean;
  disabled?: boolean;
  className?: string;
}

export function VoiceMicButton({
  toggle,
  isRecording,
  isTranscribing,
  disabled = false,
  className,
}: VoiceMicButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || isTranscribing}
      onClick={toggle}
      className={cn(
        "relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-brand-border/60 bg-white text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-50",
        isRecording && "border-red-300 bg-red-50 text-red-600",
        className
      )}
      aria-label={
        isTranscribing
          ? "Converting speech to text"
          : isRecording
            ? "Stop recording"
            : "Record voice"
      }
      title={
        isRecording
          ? "Tap to stop and convert to text"
          : "Record voice"
      }
    >
      {isRecording && (
        <span className="absolute inset-0 animate-ping rounded-full bg-red-300/40" />
      )}
      {isTranscribing ? (
        <Loader2 className="relative h-4 w-4 animate-spin" />
      ) : isRecording ? (
        <Square className="relative h-3.5 w-3.5 fill-current" />
      ) : (
        <Mic className="relative h-4 w-4" />
      )}
    </button>
  );
}
