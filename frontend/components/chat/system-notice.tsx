import { cn } from "@/lib/utils";

export function ChatSystemNotice({
  content,
  className,
}: {
  content: string;
  className?: string;
}) {
  return (
    <div className={cn("flex justify-center py-2", className)}>
      <p className="max-w-md text-center text-xs leading-relaxed text-muted-foreground">
        {content}
      </p>
    </div>
  );
}

export function isSupportOnlyMessage(msg: {
  role?: string;
  metadata?: Record<string, unknown> | null;
}) {
  const meta = msg.metadata;
  if (!meta) return false;
  return (
    meta.visibility === "support_only" || meta.message_type === "handoff_brief"
  );
}

export function isChatSystemNotice(msg: {
  role: string;
  metadata?: Record<string, unknown> | null;
}) {
  if (msg.role !== "system") return false;
  if (isSupportOnlyMessage(msg)) return false;
  const type = msg.metadata?.message_type;
  return type === "system_notice" || type == null;
}
