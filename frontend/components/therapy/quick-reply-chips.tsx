"use client";

import { Button } from "@/components/ui/button";

export interface QuickReply {
  id: string;
  label: string;
  message: string;
}

interface QuickReplyChipsProps {
  replies: QuickReply[];
  onSelect: (message: string) => void;
  disabled?: boolean;
}

export function QuickReplyChips({
  replies,
  onSelect,
  disabled,
}: QuickReplyChipsProps) {
  if (!replies.length) return null;

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {replies.map((r) => (
          <Button
            key={r.id}
            type="button"
            size="sm"
            variant="secondary"
            disabled={disabled}
            className="rounded-full"
            onClick={() => onSelect(r.message)}
          >
            {r.label}
          </Button>
      ))}
    </div>
  );
}
