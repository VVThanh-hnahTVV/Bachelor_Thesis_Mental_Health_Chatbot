"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { submitMessageFeedback } from "@/lib/api/chat";
import { cn } from "@/lib/utils";

type FeedbackValue = "yes" | "a_bit" | "no";

const LABELS_VI: Record<FeedbackValue, string> = {
  yes: "Có",
  a_bit: "Một chút",
  no: "Chưa",
};

const LABELS_EN: Record<FeedbackValue, string> = {
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
  lang = "vi",
  className,
}: MessageFeedbackProps) {
  const [submitted, setSubmitted] = useState<FeedbackValue | null>(null);
  const [loading, setLoading] = useState(false);
  const labels = lang === "en" ? LABELS_EN : LABELS_VI;
  const prompt =
    lang === "en"
      ? "Did this help you feel a little lighter?"
      : "Luna có giúp bạn cảm thấy nhẹ hơn chút không?";

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
        {lang === "en" ? "Thanks for your feedback." : "Cảm ơn bạn đã phản hồi."}
      </p>
    );
  }

  return (
    <div className={cn("mt-3 space-y-2", className)}>
      <p className="text-xs text-gray-600">{prompt}</p>
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
            {labels[v]}
          </Button>
        ))}
      </div>
    </div>
  );
}
