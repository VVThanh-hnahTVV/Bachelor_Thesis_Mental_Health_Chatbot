"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { format, parseISO } from "date-fns";
import {
  ChevronLeft,
  ChevronRight,
  Clock,
  Loader2,
  MessageSquare,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { AdminConversation } from "@/lib/api/admin-conversations";
import { useSession } from "@/lib/contexts/session-context";
import { useSupportQueue } from "@/lib/hooks/admin-queries";
import { cn } from "@/lib/utils";

const SIDEBAR_STORAGE_KEY = "admin-support-queue-sidebar-open";

function formatQueueTime(iso: string | null | undefined) {
  if (!iso) return "—";
  try {
    return format(parseISO(iso), "HH:mm dd/MM");
  } catch {
    return "—";
  }
}

function userLabel(conv: AdminConversation) {
  if (conv.user?.name) return conv.user.name;
  if (conv.user?.email) return conv.user.email;
  return "Khách";
}

export function filterAwaitingSupportQueue(
  conversations: AdminConversation[]
) {
  return conversations.filter((conv) => conv.support_mode === "awaiting_support");
}

export function filterVisibleQueue(
  conversations: AdminConversation[],
  currentUserId?: string
) {
  return conversations.filter((conv) => {
    if (conv.support_mode === "awaiting_support") return true;
    if (conv.support_mode === "human") {
      return Boolean(
        currentUserId && conv.assigned_support_id === currentUserId
      );
    }
    return false;
  });
}

export function SupportQueueSidebar({
  activeSessionId,
}: {
  activeSessionId: string;
}) {
  const { user } = useSession();
  const { data, isLoading } = useSupportQueue();
  const queue = filterVisibleQueue(data?.conversations ?? [], user?.id);
  const [open, setOpen] = useState(true);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(SIDEBAR_STORAGE_KEY);
      if (stored !== null) setOpen(stored === "true");
    } catch {
      /* ignore */
    }
  }, []);

  const toggle = () => {
    setOpen((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(SIDEBAR_STORAGE_KEY, String(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  if (!open) {
    return (
      <div className="flex w-11 shrink-0 flex-col items-center border-r border-border/40 bg-[#f4f4ef]/60 py-3">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          onClick={toggle}
          title="Hiện danh sách phiên"
          aria-label="Hiện danh sách phiên"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
        {queue.length > 0 && (
          <span
            className="mt-2 flex h-5 min-w-5 items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-semibold text-white"
            title={`${queue.length} phiên`}
          >
            {queue.length}
          </span>
        )}
        <MessageSquare className="mt-3 h-4 w-4 text-muted-foreground" />
      </div>
    );
  }

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-border/40 bg-[#f4f4ef]/60">
      <div className="flex shrink-0 items-start justify-between gap-2 border-b border-border/40 px-4 py-4">
        <div className="min-w-0">
          <h2 className="font-serif text-lg italic text-foreground">
            Phiên cần hỗ trợ
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {queue.length} phiên · cập nhật mỗi 10 giây
          </p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          onClick={toggle}
          title="Ẩn danh sách phiên"
          aria-label="Ẩn danh sách phiên"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
      </div>

      <div className="admin-scrollbar min-h-0 flex-1 overflow-y-auto p-3">
        {isLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : queue.length === 0 ? (
          <p className="px-2 py-6 text-center text-sm text-muted-foreground">
            Không có phiên chờ hỗ trợ
          </p>
        ) : (
          <ul className="space-y-2">
            {queue.map((conv) => {
              const isActive = conv.session_id === activeSessionId;
              const isMine =
                conv.support_mode === "human" &&
                conv.assigned_support_id === user?.id;
              const href = isMine
                ? `/admin/conversations/${conv.session_id}`
                : `/admin/conversations/${conv.session_id}?join=1`;

              return (
                <li key={conv.session_id}>
                  <Link
                    href={href}
                    className={cn(
                      "block rounded-lg border px-3 py-3 transition-colors",
                      isActive
                        ? "border-serene-accent/50 bg-white shadow-sm"
                        : "border-border/30 bg-white/80 hover:border-serene-accent/30 hover:bg-white"
                    )}
                  >
                    <div className="flex items-start gap-2">
                      <MessageSquare
                        className={cn(
                          "mt-0.5 h-4 w-4 shrink-0",
                          conv.support_mode === "awaiting_support"
                            ? "text-amber-600"
                            : "text-serene-accent"
                        )}
                      />
                      <div className="min-w-0 flex-1">
                        <p
                          className={cn(
                            "truncate text-sm font-medium",
                            isActive && "text-serene-accent"
                          )}
                        >
                          {conv.title || "Cuộc trò chuyện"}
                        </p>
                        <p className="mt-0.5 truncate text-xs text-muted-foreground">
                          {userLabel(conv)}
                        </p>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <span
                            className={cn(
                              "rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide",
                              conv.support_mode === "awaiting_support"
                                ? "bg-amber-100 text-amber-800"
                                : "bg-emerald-100 text-emerald-800"
                            )}
                          >
                            {conv.support_mode === "awaiting_support"
                              ? "Chờ tham gia"
                              : "Đang hỗ trợ"}
                          </span>
                          <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                            <Clock className="h-3 w-3" />
                            {formatQueueTime(conv.handoff_requested_at)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
