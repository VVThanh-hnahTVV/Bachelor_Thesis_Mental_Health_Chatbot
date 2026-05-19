"use client";

import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface QuickReply {
  id: string;
  label: string;
  message: string;
}

interface QuickReplyChipsProps {
  replies: QuickReply[];
  onSelect: (message: string) => void;
  disabled?: boolean;
  className?: string;
}

export function QuickReplyChips({
  replies,
  onSelect,
  disabled,
  className,
}: QuickReplyChipsProps) {
  if (!replies.length) return null;

  const shown = replies.slice(0, 3);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={cn("grid grid-cols-1 gap-2 sm:grid-cols-3", className)}
    >
      {shown.map((r) => (
        <Button
          key={r.id}
          type="button"
          size="sm"
          variant="secondary"
          disabled={disabled}
          className="h-auto min-h-9 w-full justify-center rounded-full px-3 py-2 text-xs sm:text-sm"
          onClick={() => onSelect(r.message)}
        >
          <span className="line-clamp-2 text-center">{r.label}</span>
        </Button>
      ))}
    </motion.div>
  );
}
