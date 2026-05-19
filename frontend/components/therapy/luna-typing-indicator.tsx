"use client";

import { motion } from "framer-motion";
import { LunaAvatar } from "@/components/therapy/luna-avatar";

export function LunaTypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-4 bg-brand-light/40 px-6 py-6"
    >
      <motion.div className="mt-1 shrink-0">
        <LunaAvatar />
      </motion.div>
      <motion.div
        className="flex items-center gap-2"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
      >
        <p className="text-sm font-medium text-gray-800">Luna AI</p>
        <motion.div className="flex items-end gap-1 pb-0.5" aria-label="Đang soạn">
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
  );
}
