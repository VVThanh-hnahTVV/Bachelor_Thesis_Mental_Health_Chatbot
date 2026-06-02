"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { HeliosAvatar } from "@/components/therapy/helios-avatar";
import { LunaAvatar } from "@/components/therapy/luna-avatar";

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

export function LunaTypingIndicator({
  label = "Luna AI",
  variant = "luna",
  statusMessage,
}: {
  label?: string;
  variant?: "luna" | "helios";
  /** Current processing step; animated ellipsis is appended automatically. */
  statusMessage?: string | null;
}) {
  const displayStatus = statusMessage?.trim() || "Đang xử lý";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-4 bg-brand-light/40 px-6 py-6"
    >
      <motion.div className="mr-auto flex min-w-0 max-w-3/4 gap-4">
        <motion.div className="mt-1 shrink-0">
          {variant === "helios" ? <HeliosAvatar /> : <LunaAvatar />}
        </motion.div>
        <motion.div
          className="flex flex-col gap-1"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
        >
          <p className="text-sm font-medium text-gray-800">{label}</p>
          <div className="chat-status-pulse text-sm text-gray-600" aria-live="polite" aria-busy="true">
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
        </motion.div>
      </motion.div>
    </motion.div>
  );
}
