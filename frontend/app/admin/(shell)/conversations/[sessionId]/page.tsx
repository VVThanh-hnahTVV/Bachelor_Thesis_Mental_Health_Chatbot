"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, LogOut, UserCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { ChatMessageMarkdown } from "@/components/therapy/chat-message-markdown";
import {
  ChatSystemNotice,
  isChatSystemNotice,
} from "@/components/chat/system-notice";
import type { SupportMode } from "@/lib/api/handoff";
import {
  getSupportQueue,
  joinSupportSession,
  leaveSupportSession,
  type AdminConversationMessage,
} from "@/lib/api/admin-conversations";
import {
  adminKeys,
  useAdminConversationDetail,
  useAdminConversationMessages,
} from "@/lib/hooks/admin-queries";
import { useSupportChatWs } from "@/lib/hooks/use-support-chat-ws";
import { useSession } from "@/lib/contexts/session-context";
import { SupportQueueSidebar, filterVisibleQueue } from "@/components/admin/support-queue-sidebar";
import { cn } from "@/lib/utils";

function senderLabel(msg: AdminConversationMessage) {
  if (msg.sender_name) return msg.sender_name;
  if (msg.role === "user") return "Người dùng";
  if (msg.role === "support") return "Support";
  if (msg.role === "assistant") return "Helios";
  return msg.role;
}

function sortByCreatedAt(messages: AdminConversationMessage[]) {
  return [...messages].sort(
    (a, b) =>
      new Date(a.created_at || 0).getTime() -
      new Date(b.created_at || 0).getTime()
  );
}

function isHandoffBrief(msg: AdminConversationMessage) {
  return msg.metadata?.message_type === "handoff_brief";
}

function AdminChatMessage({
  msg,
}: {
  msg: AdminConversationMessage;
}) {
  if (isHandoffBrief(msg)) {
    return (
      <div className="mb-4 w-full max-w-3xl">
        <p className="mb-1 text-xs font-medium text-amber-800">
          Tóm tắt chuyển giao · chỉ bạn thấy
        </p>
        <div className="rounded-xl border border-amber-200/80 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          <ChatMessageMarkdown content={msg.content} />
        </div>
      </div>
    );
  }

  if (isChatSystemNotice(msg)) {
    return <ChatSystemNotice content={msg.content} className="mb-2" />;
  }

  return (
    <div
      className={cn(
        "mb-4 max-w-3xl",
        msg.role === "user" ? "ml-auto text-right" : ""
      )}
    >
      <p className="mb-1 text-xs font-medium text-muted-foreground">
        {senderLabel(msg)}
      </p>
      <div
        className={cn(
          "inline-block rounded-xl px-4 py-3 text-sm",
          msg.role === "user"
            ? "bg-brand text-white"
            : "border border-border/40 bg-white"
        )}
      >
        <ChatMessageMarkdown
          content={msg.content}
          className={
            msg.role === "user"
              ? "text-white [&_a]:text-white [&_p]:text-white"
              : undefined
          }
        />
      </div>
    </div>
  );
}

export default function AdminSupportChatPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-[50vh] items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-serene-accent" />
        </div>
      }
    >
      <AdminSupportChatPageInner />
    </Suspense>
  );
}

function AdminSupportChatPageInner() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { user } = useSession();
  const sessionId = String(params.sessionId || "");
  const autoJoin = searchParams.get("join") === "1";

  const [draft, setDraft] = useState("");
  const [joining, setJoining] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [joinError, setJoinError] = useState<string | null>(null);
  const [leaveDialogOpen, setLeaveDialogOpen] = useState(false);
  const [localSupportName, setLocalSupportName] = useState<string | null>(null);
  const [liveMessages, setLiveMessages] = useState<AdminConversationMessage[]>(
    []
  );
  const autoJoinAttempted = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const {
    data: detail,
    isSuccess: detailLoaded,
    refetch: refetchDetail,
  } = useAdminConversationDetail(sessionId);
  const { data: messages = [], refetch: refetchMessages } =
    useAdminConversationMessages(sessionId);

  const assignedToMe = Boolean(
    detail?.support_mode === "human" &&
      detail.assigned_support_id &&
      user?.id &&
      detail.assigned_support_id === user.id
  );
  const assignedToOther = Boolean(
    detail?.support_mode === "human" &&
      detail.assigned_support_id &&
      user?.id &&
      detail.assigned_support_id !== user.id
  );
  const canChat = assignedToMe;
  const canJoin =
    detailLoaded &&
    !joining &&
    (detail?.support_mode === "ai" || detail?.support_mode === "awaiting_support");

  useEffect(() => {
    if (detail?.assigned_support_name) {
      setLocalSupportName(detail.assigned_support_name);
    }
  }, [detail?.assigned_support_name]);

  const appendLive = useCallback((msg: AdminConversationMessage) => {
    setLiveMessages((prev) => {
      if (msg.id && prev.some((m) => m.id === msg.id)) return prev;
      return [...prev, msg];
    });
  }, []);

  const { sendMessage, connected } = useSupportChatWs({
    sessionId,
    enabled: canChat,
    onMessage: (msg) => {
      appendLive({
        id: msg.id || `${Date.now()}`,
        role: msg.role,
        content: msg.content,
        created_at: msg.created_at || new Date().toISOString(),
        sender_name: msg.sender_name,
        metadata: msg.metadata,
      });
    },
    onSupportModeChange: () => {
      void refetchDetail();
      void refetchMessages();
    },
  });

  const mergedMessages = [...messages];
  for (const m of liveMessages) {
    if (!mergedMessages.some((x) => x.id === m.id)) mergedMessages.push(m);
  }

  const displayMessages = sortByCreatedAt(mergedMessages);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [displayMessages.length]);

  const clearJoinParam = useCallback(() => {
    if (searchParams.get("join") === "1") {
      router.replace(`/admin/conversations/${sessionId}`);
    }
  }, [router, searchParams, sessionId]);

  const handleJoin = useCallback(async () => {
    setJoining(true);
    setJoinError(null);
    try {
      const res = await joinSupportSession(sessionId);
      setLocalSupportName(res.assigned_support_name);
      queryClient.setQueryData(adminKeys.conversations.detail(sessionId), {
        ...(detail || {}),
        support_mode: "human",
        assigned_support_id: user?.id ?? detail?.assigned_support_id ?? null,
        assigned_support_name: res.assigned_support_name,
      });
      await refetchDetail();
      await refetchMessages();
      await queryClient.invalidateQueries({
        queryKey: adminKeys.conversations.queue(),
      });
      clearJoinParam();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Không thể tham gia phiên";
      setJoinError(message);
      console.error(err);
    } finally {
      setJoining(false);
    }
  }, [
    sessionId,
    detail,
    user?.id,
    queryClient,
    refetchDetail,
    refetchMessages,
    clearJoinParam,
  ]);

  useEffect(() => {
    if (!autoJoin || autoJoinAttempted.current || !sessionId || !detailLoaded) {
      return;
    }
    autoJoinAttempted.current = true;

    if (detail?.support_mode === "human") {
      clearJoinParam();
      return;
    }

    if (canJoin) {
      void handleJoin();
    }
  }, [
    autoJoin,
    sessionId,
    detailLoaded,
    detail?.support_mode,
    canJoin,
    handleJoin,
    clearJoinParam,
  ]);

  const handleConfirmLeave = async () => {
    setLeaveDialogOpen(false);
    setLeaving(true);
    const currentSession = sessionId;

    setLiveMessages([]);
    setDraft("");

    void leaveSupportSession(currentSession)
      .then(() => {
        void queryClient.invalidateQueries({
          queryKey: adminKeys.conversations.queue(),
        });
        void queryClient.removeQueries({
          queryKey: adminKeys.conversations.detail(currentSession),
        });
        void queryClient.removeQueries({
          queryKey: adminKeys.conversations.messages(currentSession),
        });
      })
      .catch((err) => {
        console.error(err);
      });

    try {
      const queueRes = await queryClient.fetchQuery({
        queryKey: adminKeys.conversations.queue(),
        queryFn: getSupportQueue,
      });
      const remaining = filterVisibleQueue(
        queueRes?.conversations ?? [],
        user?.id
      ).filter((conv) => conv.session_id !== currentSession);

      if (remaining.length === 0) {
        router.push("/admin/conversations");
      } else {
        router.replace("/admin/conversations/support");
      }
    } catch (err) {
      console.error(err);
      router.push("/admin/conversations");
    } finally {
      setLeaving(false);
    }
  };

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || !canChat) return;
    sendMessage(text);
    setDraft("");
  };

  const supportMode = (detail?.support_mode as SupportMode) || "ai";

  return (
    <div className="flex h-[calc(100vh-0px)] flex-col">
      <header className="flex shrink-0 items-center justify-between border-b border-border/40 bg-white px-6 py-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" asChild>
            <Link href="/admin/conversations">
              <ArrowLeft className="mr-1 h-4 w-4" />
              Quay lại
            </Link>
          </Button>
          <div>
            <h1 className="font-serif text-xl italic">
              {detail?.title || "Phiên hỗ trợ"}
            </h1>
            <p className="text-xs text-muted-foreground">
              {sessionId.slice(0, 8)}… · {supportMode}
              {canChat && (
                <span className="ml-2">
                  {connected ? "· WS connected" : "· WS connecting…"}
                </span>
              )}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          {canJoin && (
            <Button onClick={() => void handleJoin()} disabled={joining}>
              {joining ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <UserCheck className="mr-2 h-4 w-4" />
              )}
              Tham gia
            </Button>
          )}
        </div>
      </header>

      {joinError && (
        <div className="shrink-0 border-b border-red-200 bg-red-50 px-6 py-2 text-sm text-red-800">
          {joinError}
        </div>
      )}

      {assignedToOther && (
        <div className="shrink-0 border-b border-amber-200 bg-amber-50 px-6 py-2 text-sm text-amber-900">
          Phiên này đang được hỗ trợ bởi{" "}
          <span className="font-medium">
            {detail?.assigned_support_name || "chuyên viên khác"}
          </span>
          . Chỉ một chuyên viên có thể tham gia mỗi phiên.
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <SupportQueueSidebar activeSessionId={sessionId} />

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="admin-scrollbar min-h-0 flex-1 overflow-y-auto px-6 py-4">
            {detail?.summary && (
              <div className="mb-4 w-full max-w-3xl">
                <p className="mb-1 text-xs font-medium text-muted-foreground">
                  Tóm tắt cuộc trò chuyện
                </p>
                <div className="rounded-xl border border-border/40 bg-[#f4f4ef] px-4 py-3 text-sm">
                  <ChatMessageMarkdown content={detail.summary} />
                </div>
              </div>
            )}
            {displayMessages.map((msg) => (
              <AdminChatMessage key={msg.id} msg={msg} />
            ))}
            <div ref={bottomRef} />
          </div>

          <form
            onSubmit={handleSend}
            className="flex shrink-0 items-center gap-2 border-t border-border/40 bg-white px-6 py-4"
          >
            {canChat && (
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="shrink-0 text-muted-foreground hover:text-red-600"
                onClick={() => setLeaveDialogOpen(true)}
                disabled={leaving}
                title="Rời khỏi cuộc trò chuyện"
                aria-label="Rời khỏi cuộc trò chuyện"
              >
                {leaving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <LogOut className="h-4 w-4" />
                )}
              </Button>
            )}
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="min-w-0 flex-1"
              placeholder={
                canChat
                  ? `Nhắn tin cho người dùng${localSupportName ? ` (${localSupportName})` : ""}...`
                  : assignedToOther
                    ? "Phiên đang được chuyên viên khác phụ trách"
                    : "Bấm Tham gia để bắt đầu trò chuyện"
              }
              disabled={!canChat || leaving}
            />
            <Button type="submit" disabled={!canChat || !draft.trim() || leaving}>
              Gửi
            </Button>
          </form>
        </div>
      </div>

      <AlertDialog open={leaveDialogOpen} onOpenChange={setLeaveDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Rời khỏi cuộc trò chuyện?</AlertDialogTitle>
            <AlertDialogDescription>
              Phiên hỗ trợ sẽ kết thúc. Hệ thống sẽ tóm tắt cuộc trò chuyện với
              người dùng ở chế độ nền. Bạn có chắc muốn rời không?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={leaving}>Hủy</AlertDialogCancel>
            <AlertDialogAction
              disabled={leaving}
              onClick={(e) => {
                e.preventDefault();
                void handleConfirmLeave();
              }}
              className="bg-red-600 hover:bg-red-700"
            >
              {leaving ? "Đang rời…" : "Rời phiên"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
