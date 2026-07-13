"use client";

import { useEffect, useState } from "react";
import { HeliosAvatar } from "@/components/therapy/helios-avatar";

export type HeliosTypingStep = {
  id: string;
  label: string;
  status: "completed" | "active";
  detail?: string;
};

function AnimatedEllipsis() {
  const [dots, setDots] = useState(".");

  useEffect(() => {
    const id = window.setInterval(() => {
      setDots((prev) => (prev.length >= 3 ? "." : `${prev}.`));
    }, 400);
    return () => window.clearInterval(id);
  }, []);

  return (
    <span className="inline-block w-[1.25em] text-left tabular-nums" aria-hidden>
      {dots}
    </span>
  );
}

function ElapsedSeconds() {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => {
      setSeconds((prev) => prev + 1);
    }, 1000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <span className="shrink-0 tabular-nums text-xs text-gray-400" aria-hidden>
      {seconds}s
    </span>
  );
}

/** Single-line status: the newest event replaces the previous one. */
export function HeliosTypingIndicator({
  steps,
  statusMessage,
}: {
  steps?: HeliosTypingStep[];
  /** @deprecated Use `steps` instead — kept for legacy single-step usage. */
  statusMessage?: string | null;
}) {
  const current: HeliosTypingStep = steps?.length
    ? steps[steps.length - 1]
    : {
        id: "default",
        label: statusMessage?.trim() || "Helios đang xử lý",
        status: "active",
      };

  return (
    <div className="flex gap-4 px-6 py-4">
      <div className="mr-auto flex min-w-0 max-w-3/4 gap-4">
        <div className="mt-1 shrink-0">
          <HeliosAvatar />
        </div>
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium text-gray-800">Helios</p>
            <ElapsedSeconds />
          </div>
          <div aria-live="polite" aria-busy="true" className="min-w-0">
            <div
              key={`${current.id}-${current.detail ?? ""}`}
              className="flex min-w-0 items-baseline gap-2 text-sm text-gray-700 animate-in fade-in slide-in-from-bottom-1 duration-300"
            >
              <span className="font-medium">
                {current.label}
                <AnimatedEllipsis />
              </span>
              {current.detail && (
                <span className="min-w-0 truncate text-xs text-gray-400">
                  {current.detail}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
