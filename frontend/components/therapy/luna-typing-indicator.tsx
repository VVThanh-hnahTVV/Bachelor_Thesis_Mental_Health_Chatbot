"use client";

import { motion } from "framer-motion";
import { HeliosAvatar } from "@/components/therapy/helios-avatar";
import { LunaAvatar } from "@/components/therapy/luna-avatar";

export function LunaTypingIndicator({
  label = "Luna AI",
  variant = "luna",
}: {
  label?: string;
  variant?: "luna" | "helios";
}) {
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
        <motion.div className="flex items-end gap-1" aria-label="Đang soạn">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="inline-block h-1.5 w-1.5 rounded-full bg-brand"
              animate={{ y: [0, -5, 0] }}
              transition={{
                duration: 0.55,
                repeat: Infinity,
                delay: i * 0.14,
                ease: "easeInOut",
              }}
            />
          ))}
        </motion.div>
      </motion.div>
      </motion.div>
    </motion.div>
  );
}
