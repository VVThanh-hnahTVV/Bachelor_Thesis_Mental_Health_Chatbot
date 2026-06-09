"use client";

import { useState } from "react";
import { Star } from "lucide-react";
import { cn } from "@/lib/utils";
import { rateActivity } from "@/lib/api/wellness";

interface ActivityStarRatingProps {
  sessionId: string;
  activityId: string;
  completionId: string;
  messageId?: string;
  lang?: "vi" | "en";
  className?: string;
  initialRating?: number;
  initialThanks?: string;
  readOnly?: boolean;
  onRated?: (rating: number, message: string) => void;
}

export function ActivityStarRating({
  sessionId,
  activityId,
  completionId,
  messageId,
  lang = "vi",
  className,
  initialRating,
  initialThanks,
  readOnly = false,
  onRated,
}: ActivityStarRatingProps) {
  const [hover, setHover] = useState(0);
  const [submitted, setSubmitted] = useState<number | null>(initialRating ?? null);
  const [loading, setLoading] = useState(false);
  const defaultThanks =
    lang === "vi"
      ? "Cảm ơn bạn đã đánh giá! Phản hồi của bạn giúp Helios gợi ý bài tập phù hợp hơn."
      : "Thanks for your rating! Your feedback helps Helios suggest better activities.";

  const [thanks, setThanks] = useState<string | null>(
    readOnly && initialRating ? initialThanks ?? defaultThanks : null
  );

  const displayRating = submitted ?? hover;
  const isLocked = readOnly || submitted !== null;

  const prompt =
    lang === "vi"
      ? "Bạn đánh giá bài tập này mấy sao?"
      : "How many stars would you give this activity?";

  const handleRate = async (value: number) => {
    if (isLocked || loading) return;
    setLoading(true);
    try {
      const res = await rateActivity(
        sessionId,
        activityId,
        completionId,
        value,
        messageId
      );
      setSubmitted(value);
      setThanks(res.message);
      onRated?.(value, res.message);
    } catch {
      setThanks(
        lang === "vi"
          ? "Không gửi được đánh giá. Bạn có thể thử lại sau."
          : "Could not submit rating. Please try again later."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={cn("mt-3 space-y-2", className)}>
      {!isLocked ? (
        <p className="text-xs text-gray-600">{prompt}</p>
      ) : null}
      <div className="flex items-center gap-1">
        {[1, 2, 3, 4, 5].map((value) => (
          <button
            key={value}
            type="button"
            disabled={loading || isLocked}
            className={cn(
              "rounded p-0.5 transition",
              isLocked ? "cursor-default" : "hover:scale-110 disabled:opacity-50"
            )}
            onMouseEnter={() => {
              if (!isLocked) setHover(value);
            }}
            onMouseLeave={() => {
              if (!isLocked) setHover(0);
            }}
            onClick={() => void handleRate(value)}
            aria-label={`${value} stars`}
          >
            <Star
              className={cn(
                "h-6 w-6",
                displayRating >= value
                  ? "fill-amber-400 text-amber-400"
                  : "text-gray-300"
              )}
            />
          </button>
        ))}
      </div>
      {thanks ? (
        <p className="text-xs text-gray-600">{thanks}</p>
      ) : null}
    </div>
  );
}
