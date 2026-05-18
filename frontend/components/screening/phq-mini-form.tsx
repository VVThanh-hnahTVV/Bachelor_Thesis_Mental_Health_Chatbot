"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  fetchScreeningQuestions,
  submitScreening,
  type ScreeningResult,
} from "@/lib/api/screening";
import { getOrCreateSessionId } from "@/lib/session";

interface PhqMiniFormProps {
  instrument?: "phq2" | "phq4";
  onComplete?: (result: ScreeningResult) => void;
  onDismiss?: () => void;
}

export function PhqMiniForm({
  instrument = "phq2",
  onComplete,
  onDismiss,
}: PhqMiniFormProps) {
  const [questions, setQuestions] = useState<string[]>([]);
  const [options, setOptions] = useState<string[]>([]);
  const [disclaimer, setDisclaimer] = useState("");
  const [answers, setAnswers] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ScreeningResult | null>(null);

  useEffect(() => {
    void fetchScreeningQuestions(instrument).then((data) => {
      setQuestions(data.questions);
      setOptions(data.options);
      setDisclaimer(data.disclaimer);
      setAnswers(data.questions.map(() => -1));
      setLoading(false);
    });
  }, [instrument]);

  const allAnswered = answers.every((a) => a >= 0);

  const handleSubmit = async () => {
    if (!allAnswered) return;
    setSubmitting(true);
    try {
      const sessionId = getOrCreateSessionId();
      const res = await submitScreening(sessionId, instrument, answers);
      setResult(res);
      onComplete?.(res);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-gray-500">Đang tải khảo sát...</p>;
  }

  if (result) {
    return (
      <div className="space-y-3">
        <p className="text-sm font-medium text-gray-800">
          Điểm sàng lọc: {result.score}
        </p>
        <p className="text-sm text-gray-600">{result.interpretation}</p>
        <p className="text-xs text-gray-500">{result.disclaimer}</p>
        {onDismiss && (
          <Button type="button" onClick={onDismiss} className="mt-2">
            Đóng
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">{disclaimer}</p>
      {questions.map((q, qi) => (
        <div key={qi} className="space-y-2 rounded-lg border border-gray-200 p-3">
          <p className="text-sm font-medium text-gray-800">
            {qi + 1}. {q}
          </p>
          <RadioGroup
            value={answers[qi] >= 0 ? String(answers[qi]) : ""}
            onValueChange={(v) => {
              const next = [...answers];
              next[qi] = parseInt(v, 10);
              setAnswers(next);
            }}
          >
            {options.map((opt, oi) => (
              <div key={oi} className="flex items-center space-x-2">
                <RadioGroupItem value={String(oi)} id={`q${qi}-o${oi}`} />
                <Label htmlFor={`q${qi}-o${oi}`} className="text-sm font-normal">
                  {opt}
                </Label>
              </div>
            ))}
          </RadioGroup>
        </div>
      ))}
      <div className="flex gap-2">
        <Button
          type="button"
          onClick={() => void handleSubmit()}
          disabled={!allAnswered || submitting}
        >
          Gửi khảo sát
        </Button>
        {onDismiss && (
          <Button type="button" variant="ghost" onClick={onDismiss}>
            Để sau
          </Button>
        )}
      </div>
    </div>
  );
}
