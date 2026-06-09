"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { HeliosAvatar } from "@/components/therapy/helios-avatar";

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

export function HeliosTypingIndicator({
  statusMessage,
}: {
  /** Current processing step; animated ellipsis is appended automatically. */
  statusMessage?: string | null;
}) {
  const displayStatus = statusMessage?.trim() || "Helios đang xử lý";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-4 px-6 py-4"
    >
      <div className="mr-auto flex min-w-0 max-w-3/4 gap-4">
        <div className="mt-1 shrink-0">
          <HeliosAvatar />
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <p className="text-sm font-medium text-gray-800">Helios</p>
          <div
            className="chat-status-pulse text-sm text-gray-600"
            aria-live="polite"
            aria-busy="true"
          >
            <motion.span
              key={displayStatus}
              initial={{ opacity: 0.4 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.22, ease: "easeOut" }}
              className="inline"
            >
              {displayStatus}
            </motion.span>
            <AnimatedEllipsis />
          </div>
        </div>
      </div>
    </motion.div>
  );
}
