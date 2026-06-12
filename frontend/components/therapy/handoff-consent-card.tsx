"use client";

import { Headphones, Loader2, PlusCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface HandoffConsentCardProps {
  onConnect: () => void;
  onNewSession: () => void;
  disabled?: boolean;
  loading?: boolean;
  className?: string;
}

export function isHandoffConsentPrompt(metadata?: Record<string, unknown>): boolean {
  return Boolean(metadata?.handoff_consent_prompt) && !metadata?.handoff_consent_resolved;
}

export function HandoffConsentCard({
  onConnect,
  onNewSession,
  disabled = false,
  loading = false,
  className,
}: HandoffConsentCardProps) {
  return (
    <div className={cn("mt-3 flex flex-wrap gap-2", className)}>
      <Button
        type="button"
        size="sm"
        disabled={disabled || loading}
        className="rounded-full bg-brand hover:bg-brand/90"
        onClick={onConnect}
      >
        {loading ? (
          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
        ) : (
          <Headphones className="mr-1.5 h-3.5 w-3.5" />
        )}
        Kết nối với chuyên gia
      </Button>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={disabled || loading}
        className="rounded-full border-brand-border text-gray-700 hover:bg-brand-light"
        onClick={onNewSession}
      >
        <PlusCircle className="mr-1.5 h-3.5 w-3.5" />
        Phiên mới &amp; kết nối
      </Button>
    </div>
  );
}
