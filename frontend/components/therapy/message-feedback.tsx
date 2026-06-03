"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { submitMessageFeedback } from "@/lib/api/chat";
import { cn } from "@/lib/utils";

type FeedbackValue = "yes" | "a_bit" | "no";

const LABELS: Record<FeedbackValue, string> = {
  yes: "Yes",
  a_bit: "A little",
  no: "Not yet",
};

interface MessageFeedbackProps {
  sessionId: string;
  assistantMessageId: string;
  lang?: "vi" | "en";
  className?: string;
}

export function MessageFeedback({
  sessionId,
  assistantMessageId,
  className,
}: MessageFeedbackProps) {
  const [submitted, setSubmitted] = useState<FeedbackValue | null>(null);
  const [loading, setLoading] = useState(false);

  const handle = async (value: FeedbackValue) => {
    if (submitted || loading) return;
    setLoading(true);
    try {
      await submitMessageFeedback(sessionId, assistantMessageId, value);
      setSubmitted(value);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  if (submitted) {
    return (
      <p className={cn("text-xs text-gray-500", className)}>
        Thanks for your feedback.
      </p>
    );
  }

  return (
    <div className={cn("mt-3 space-y-2", className)}>
      <p className="text-xs text-gray-600">
        Did this help you feel a little lighter?
      </p>
      <div className="flex flex-wrap gap-2">
        {(["yes", "a_bit", "no"] as FeedbackValue[]).map((v) => (
          <Button
            key={v}
            type="button"
            size="sm"
            variant="outline"
            disabled={loading}
            className="rounded-full text-xs"
            onClick={() => void handle(v)}
          >
            {LABELS[v]}
          </Button>
        ))}
      </div>
    </div>
  );
}
