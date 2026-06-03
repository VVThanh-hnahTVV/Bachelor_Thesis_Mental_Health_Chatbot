"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface VoiceRecordingVisualizerProps {
  level: number;
  className?: string;
}

const BAR_COUNT = 16;

export function VoiceRecordingVisualizer({
  level,
  className,
}: VoiceRecordingVisualizerProps) {
  const boosted = Math.min(1, level * 2.2);

  return (
    <div
      className={cn(
        "flex items-center gap-3 border-b border-red-100/80 bg-red-50/60 px-4 py-2",
        className
      )}
    >
      <span className="relative flex h-2.5 w-2.5 shrink-0">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-60" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-red-500" />
      </span>
      <span className="shrink-0 text-xs font-medium text-red-600">
        Listening...
      </span>
      <div className="flex flex-1 items-center justify-center gap-[3px] h-7">
        {Array.from({ length: BAR_COUNT }).map((_, i) => {
          const centerWeight = 1 - Math.abs(i - (BAR_COUNT - 1) / 2) / (BAR_COUNT / 2);
          const barLevel = boosted * (0.35 + centerWeight * 0.65);
          const height = 4 + barLevel * 22;

          return (
            <motion.span
              key={i}
              className="w-[3px] rounded-full bg-gradient-to-t from-red-400 to-red-500"
              animate={{ height }}
              transition={{ duration: 0.08, ease: "easeOut" }}
              style={{ display: "block" }}
            />
          );
        })}
      </div>
    </div>
  );
}
