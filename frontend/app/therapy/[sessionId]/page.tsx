"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  Send,
  User,
  Loader2,
  MessageSquare,
  PlusCircle,
  BookOpenCheck,
  Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import {
  AssistantMessageBubble,
  ChatMessageMarkdown,
} from "@/components/therapy/chat-message-markdown";
import { Badge } from "@/components/ui/badge";
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
import {
  createChatSession,
  deleteChatSession,
  sendChatMessageWithStatus,
  getChatHistory,
  ChatMessage,
  getAllChatSessions,
  ChatSession,
  RateLimitError,
} from "@/lib/api/chat";
import { VoiceMicButton } from "@/components/therapy/voice-mic-button";
import { VoiceRecordingVisualizer } from "@/components/therapy/voice-recording-visualizer";
import { useSpeechToText } from "@/hooks/use-speech-to-text";
import { ScrollArea } from "@/components/ui/scroll-area";
import { HeliosAvatar } from "@/components/therapy/helios-avatar";
import {
  ChatSystemNotice,
  isChatSystemNotice,
  isSupportOnlyMessage,
} from "@/components/chat/system-notice";
import { HeliosTypingIndicator } from "@/components/therapy/helios-typing-indicator";
import { HandoffButton } from "@/components/therapy/handoff-button";
import {
  HandoffConsentCard,
  isHandoffConsentPrompt,
} from "@/components/therapy/handoff-consent-card";
import {
  confirmHandoff,
  getConversationStatus,
  requestHandoffConsent,
  type SupportMode,
} from "@/lib/api/handoff";
import { useChatWs } from "@/lib/hooks/use-chat-ws";
import {
  startWellnessSession,
  completeWellnessSession,
  getActivityCatalog,
  type WellnessActivity,
} from "@/lib/api/wellness";
import { ActivityPopupHost } from "@/components/activities/activity-popup-host";
import { ActivityStarRating } from "@/components/activities/activity-star-rating";
import { linkChatSession } from "@/lib/api/auth";
import { getDefaultMedicalGreeting } from "@/lib/helios-greeting";
import { registerChatSessionId, unregisterChatSessionId } from "@/lib/session";

const SUGGESTED_QUESTIONS = [
  { text: "Làm sao để quản lý lo âu và căng thẳng hàng ngày?" },
  { text: "Dấu hiệu trầm cảm thường gặp là gì?" },
  { text: "Tôi cảm thấy quá tải — nên làm gì để ổn định cảm xúc?" },
];

const DEFAULT_SESSION_TITLES = new Set([
  "New chat",
  "Chat",
  "New conversation",
  "Cuộc trò chuyện mới",
]);

function welcomeMessages(): ChatMessage[] {
  return [
    {
      role: "assistant",
      content: getDefaultMedicalGreeting(),
      timestamp: new Date(),
      metadata: { message_type: "medical" },
    },
  ];
}

function getSessionTitle(session: ChatSession): string {
  const storedTitle = session.title?.trim();
  if (storedTitle && !DEFAULT_SESSION_TITLES.has(storedTitle)) {
    if (storedTitle.length <= 40) return storedTitle;
    return `${storedTitle.slice(0, 40)}…`;
  }
  const first =
    session.messages.find((m) => m.role === "user")?.content ||
    session.messages[0]?.content;
  if (!first) return "New conversation";
  const trimmed = first.trim();
  if (trimmed.length <= 36) return trimmed;
  return `${trimmed.slice(0, 36)}…`;
}

export default function TherapyPage() {
  const params = useParams();
  const skipSessionInitRef = useRef(false);
  const [message, setMessage] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [typingStatus, setTypingStatus] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesScrollRef = useRef<HTMLDivElement>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [mounted, setMounted] = useState(false);
  const [isPageLoading, setIsPageLoading] = useState(true);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [activityCatalog, setActivityCatalog] = useState<WellnessActivity[]>([]);
  const [activeActivity, setActiveActivity] = useState<WellnessActivity | null>(null);
  const [activityPopupOpen, setActivityPopupOpen] = useState(false);
  const wellnessCompleteRef = useRef(false);
  const [sessionId, setSessionId] = useState<string | null>(
    params.sessionId as string
  );
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [speechError, setSpeechError] = useState<string | null>(null);
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null);
  const [isDeletingSession, setIsDeletingSession] = useState(false);
  const [supportMode, setSupportMode] = useState<SupportMode>("ai");
  const [assignedSupportName, setAssignedSupportName] = useState<string | null>(
    null
  );
  const [handoffLoading, setHandoffLoading] = useState(false);
  const [handoffConfirmLoading, setHandoffConfirmLoading] = useState(false);

  const hasPendingHandoffConsent = messages.some(
    (m) => m.role === "assistant" && isHandoffConsentPrompt(m.metadata)
  );

  const markHandoffConsentResolved = () => {
    setMessages((prev) =>
      prev.map((m) =>
        isHandoffConsentPrompt(m.metadata)
          ? {
              ...m,
              metadata: { ...m.metadata, handoff_consent_resolved: true },
            }
          : m
      )
    );
  };

  const appendWsMessage = (msg: {
    id?: string;
    role: string;
    content: string;
    sender_name?: string;
    metadata?: Record<string, unknown>;
  }) => {
    if (isSupportOnlyMessage(msg)) return;
    setMessages((prev) => {
      if (msg.id && prev.some((m) => m.id === msg.id)) return prev;
      return [
        ...prev,
        {
          id: msg.id,
          role: msg.role as ChatMessage["role"],
          content: msg.content,
          timestamp: new Date(),
          metadata: {
            ...(msg.metadata || {}),
            sender_name: msg.sender_name,
          },
        },
      ];
    });
  };

  const { sendMessage: sendWsMessage } = useChatWs({
    sessionId,
    role: "user",
    enabled: Boolean(sessionId),
    onMessage: appendWsMessage,
    onSupportJoined: (name) => {
      setAssignedSupportName(name);
      setSupportMode("human");
    },
    onSupportLeft: () => {
      setSupportMode("ai");
      setAssignedSupportName(null);
    },
    onHandoffPending: () => setSupportMode("awaiting_support"),
    onSupportModeChange: setSupportMode,
  });

  const messageSenderLabel = (msg: ChatMessage) => {
    if (msg.role === "user") return "You";
    if (msg.role === "support") {
      return (
        (msg.metadata?.sender_name as string | undefined) ||
        assignedSupportName ||
        "Support"
      );
    }
    if (msg.role === "system") {
      return (msg.metadata?.sender_name as string | undefined) || "System";
    }
    return (msg.metadata?.sender_name as string | undefined) || "Helios";
  };

  const isHumanChat = supportMode === "human";

  const hasUserMessages = messages.some((m) => m.role === "user");

  const handleSpeechTranscript = (text: string) => {
    setSpeechError(null);
    setMessage((prev) => (prev.trim() ? `${prev.trim()} ${text}` : text));
  };

  const voiceInput = useSpeechToText({
    onTranscript: handleSpeechTranscript,
    onError: setSpeechError,
    disabled: isTyping,
  });

  const getSuggestedActivities = (metadata: ChatMessage["metadata"]) => {
    if (!metadata || !Array.isArray((metadata as any).suggested_activities)) {
      return [] as string[];
    }
    return (metadata as any).suggested_activities
      .map((s: any) => String(s?.id ?? "").trim())
      .filter(Boolean);
  };

  const getRetrievalSummary = (metadata: ChatMessage["metadata"]) => {
    const chunks = metadata?.retrieved_chunks;
    if (!Array.isArray(chunks) || chunks.length === 0) return null;
    const mode = metadata?.retrieval_mode;
    if (!mode || mode === "none") return null;
    const topics = Array.from(
      new Set(
        chunks
          .map((chunk: any) => String(chunk?.topic ?? "").trim())
          .filter(Boolean)
      )
    ).slice(0, 2);
    return topics.length > 0
      ? `Based on knowledge: ${topics.join(", ")}`
      : "Based on selected knowledge";
  };

  const applyHistoryToChat = (mapped: ChatMessage[]) => {
    setMessages(mapped);
  };

  const loadSessionIntoState = async (activeSessionId: string) => {
    registerChatSessionId(activeSessionId);
    try {
      await linkChatSession(activeSessionId);
    } catch {
      /* optional */
    }
    try {
      const [history, status] = await Promise.all([
        getChatHistory(activeSessionId),
        getConversationStatus(activeSessionId),
      ]);
      setSupportMode(status.support_mode);
      setAssignedSupportName(status.assigned_support_name);
      if (Array.isArray(history) && history.length > 0) {
        const mapped = history
          .filter((msg) => !isSupportOnlyMessage(msg))
          .map((msg) => ({
            ...msg,
            timestamp: new Date(msg.timestamp),
          }));
        applyHistoryToChat(mapped);
        return;
      }
      setMessages(welcomeMessages());
    } catch {
      setMessages(welcomeMessages());
    }
  };

  const handleNewSession = async () => {
    try {
      setIsChatLoading(true);
      const newSessionId = await createChatSession();
      registerChatSessionId(newSessionId);
      const newSession: ChatSession = {
        sessionId: newSessionId,
        messages: [],
        createdAt: new Date(),
        updatedAt: new Date(),
        chatMode: "medical",
      };
      setSessions((prev) => [newSession, ...prev]);
      skipSessionInitRef.current = true;
      setSessionId(newSessionId);
      try {
        await linkChatSession(newSessionId);
      } catch {
        /* optional — chat still links on first message */
      }
      setMessages(welcomeMessages());
      window.history.pushState({}, "", `/therapy/${newSessionId}`);
    } catch (error) {
      console.error("Failed to create new session:", error);
    } finally {
      setIsChatLoading(false);
    }
  };

  useEffect(() => {
    if (skipSessionInitRef.current) {
      skipSessionInitRef.current = false;
      return;
    }
    const initChat = async () => {
      try {
        setIsPageLoading(true);
        let activeSessionId = sessionId;
        if (!activeSessionId || activeSessionId === "new") {
          activeSessionId = await createChatSession();
          setSessionId(activeSessionId);
          window.history.pushState({}, "", `/therapy/${activeSessionId}`);
        }
        await loadSessionIntoState(activeSessionId);
      } catch {
        setMessages([
          {
            role: "assistant",
            content:
              "Sorry, there was an error loading this chat session. Please try again.",
            timestamp: new Date(),
          },
        ]);
      } finally {
        setIsPageLoading(false);
      }
    };
    initChat();
  }, [sessionId]);

  useEffect(() => {
    const loadSessions = async () => {
      try {
        const allSessions = await getAllChatSessions();
        allSessions.forEach((s) => registerChatSessionId(s.sessionId));
        setSessions(allSessions);
      } catch (error) {
        console.error("Failed to load sessions:", error);
      }
    };
    loadSessions();
  }, [messages, sessionId]);

  const scrollToBottom = () => {
    requestAnimationFrame(() => {
      const container = messagesScrollRef.current;
      if (container) {
        container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
        return;
      }
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping, typingStatus]);

  useEffect(() => {
    setMounted(true);
  }, []);

  const sendUserMessage = async (text: string) => {
    const currentMessage = text.trim();
    if (!currentMessage || isTyping || !sessionId) return;

    if (isHumanChat) {
      scrollToBottom();
      const sent = sendWsMessage(currentMessage);
      if (!sent) {
        setMessages((prev) => [
          ...prev,
          {
            role: "system",
            content: "Không thể gửi tin nhắn. Đang thử kết nối lại...",
            timestamp: new Date(),
          },
        ]);
      }
      return;
    }

    setIsTyping(true);
    setTypingStatus("Đang phân tích yêu cầu");
    setMessages((prev) => [
      ...prev,
      { role: "user", content: currentMessage, timestamp: new Date() },
    ]);
    scrollToBottom();

    try {
      const response = await sendChatMessageWithStatus(
        sessionId,
        currentMessage,
        (label) => setTypingStatus(label)
      );

      setMessages((prev) => [
        ...prev,
        {
          id: response.assistant_message_id,
          role: "assistant",
          content:
            response.response ||
            response.message ||
            "I could not generate a response. Please try again.",
          timestamp: new Date(),
          metadata: {
            message_type: response.message_type,
            sender_name: "Helios",
            ...(response.metadata || {}),
          },
        },
      ]);
      if (response.support_mode) {
        setSupportMode(response.support_mode as SupportMode);
      }
      if (response.assigned_support_name !== undefined) {
        setAssignedSupportName(response.assigned_support_name);
      }
    } catch (err) {
      if (err instanceof RateLimitError) {
        let resetNote = "";
        if (err.resetsAt) {
          const resetDate = new Date(err.resetsAt);
          if (!Number.isNaN(resetDate.getTime())) {
            resetNote = ` Bạn có thể tiếp tục sau ${resetDate.toLocaleString("vi-VN")}.`;
          }
        }
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `${err.message}${resetNote}`,
            timestamp: new Date(),
            metadata: { sender_name: "Helios", message_type: "off_topic" },
          },
        ]);
      } else {
        console.error("Chat stream failed:", err);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "Sorry, I'm having connection issues. Please try again later.",
            timestamp: new Date(),
          },
        ]);
      }
    } finally {
      setIsTyping(false);
      setTypingStatus(null);
      scrollToBottom();
    }
  };

  const handleHandoffRequest = async () => {
    if (!sessionId || handoffLoading || supportMode !== "ai") return;
    if (hasPendingHandoffConsent) return;
    setHandoffLoading(true);
    try {
      const res = await requestHandoffConsent(sessionId);
      setMessages((prev) => [
        ...prev,
        {
          id: res.assistant_message_id ?? undefined,
          role: "assistant",
          content: res.reply,
          timestamp: new Date(),
          metadata: {
            sender_name: "Helios",
            ...(res.metadata || {}),
          },
        },
      ]);
    } catch (err) {
      console.error("Handoff consent failed:", err);
    } finally {
      setHandoffLoading(false);
    }
  };

  const handleHandoffConfirm = async () => {
    if (!sessionId || handoffConfirmLoading || supportMode !== "ai") return;
    setHandoffConfirmLoading(true);
    try {
      const res = await confirmHandoff(sessionId);
      markHandoffConsentResolved();
      setSupportMode(res.support_mode);
      setMessages((prev) => [
        ...prev,
        {
          id: res.assistant_message_id ?? undefined,
          role: "assistant",
          content: res.reply,
          timestamp: new Date(),
          metadata: {
            sender_name: "Helios",
            ...(res.metadata || {}),
          },
        },
      ]);
    } catch (err) {
      console.error("Handoff confirm failed:", err);
    } finally {
      setHandoffConfirmLoading(false);
    }
  };

  const handleHandoffNewSession = async () => {
    if (handoffConfirmLoading || isChatLoading) return;
    setHandoffConfirmLoading(true);
    try {
      markHandoffConsentResolved();
      setIsChatLoading(true);
      const newSessionId = await createChatSession();
      registerChatSessionId(newSessionId);
      const newSession: ChatSession = {
        sessionId: newSessionId,
        messages: [],
        createdAt: new Date(),
        updatedAt: new Date(),
        chatMode: "medical",
      };
      setSessions((prev) => [newSession, ...prev]);
      skipSessionInitRef.current = true;
      setSessionId(newSessionId);
      setSupportMode("ai");
      setAssignedSupportName(null);
      try {
        await linkChatSession(newSessionId);
      } catch {
        /* optional */
      }
      setMessages(welcomeMessages());
      window.history.pushState({}, "", `/therapy/${newSessionId}`);

      const res = await confirmHandoff(newSessionId);
      setSupportMode(res.support_mode);
      setMessages((prev) => [
        ...prev,
        {
          id: res.assistant_message_id ?? undefined,
          role: "assistant",
          content: res.reply,
          timestamp: new Date(),
          metadata: {
            sender_name: "Helios",
            ...(res.metadata || {}),
          },
        },
      ]);
    } catch (err) {
      console.error("Failed to start new session for handoff:", err);
    } finally {
      setIsChatLoading(false);
      setHandoffConfirmLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isTyping) return;

    const currentMessage = message.trim();
    if (!currentMessage) return;
    setMessage("");
    await sendUserMessage(currentMessage);
  };

  const handleSuggestedQuestion = (text: string) => {
    setMessage("");
    void sendUserMessage(text);
  };

  useEffect(() => {
    void getActivityCatalog("helios", "vi")
      .then(setActivityCatalog)
      .catch(() => setActivityCatalog([]));
  }, []);

  const resolveActivity = (activityId: string): WellnessActivity | null => {
    const fromCatalog = activityCatalog.find((a) => a.id === activityId);
    if (fromCatalog) return fromCatalog;
    return {
      id: activityId,
      title: activityId.replace(/_/g, " "),
      description: "",
      content_type: activityId.endsWith("_video") ? "video" : "interactive",
      activity_type: activityId.endsWith("_video") ? "video" : "exercise",
      ui_component: activityId,
      video_url: null,
      youtube_id: null,
      video_source: null,
      duration_min: 5,
      avg_rating: 0,
      rating_count: 0,
    };
  };

  const openActivity = async (activityId: string) => {
    if (!sessionId) return;
    const activity = resolveActivity(activityId);
    if (!activity) return;
    setActiveActivity(activity);
    setActivityPopupOpen(true);
    wellnessCompleteRef.current = false;
    try {
      await startWellnessSession(sessionId, activityId, {
        quiet: true,
        lang: "vi",
      });
    } catch {
      /* popup still opens */
    }
  };

  const handleWellnessComplete = async () => {
    if (!sessionId || !activeActivity || wellnessCompleteRef.current) return;
    wellnessCompleteRef.current = true;
    const activityId = activeActivity.id;
    try {
      const result = await completeWellnessSession(sessionId, {
        lang: "vi",
        activityId,
      });
      const ratingMeta =
        result.show_activity_rating &&
        result.completion_id &&
        result.activity_id
          ? {
              pending_activity_rating: {
                activity_id: result.activity_id,
                completion_id: result.completion_id,
                rated: false,
              },
            }
          : {};

      const assistantContent =
        result.checkin_message ||
        (result.show_activity_rating
          ? "Bạn vừa hoàn thành bài tập. Bạn đánh giá thế nào?"
          : "");

      if (assistantContent && (result.show_activity_rating || result.checkin_message)) {
        setMessages((prev) => [
          ...prev,
          {
            id: result.assistant_message_id ?? undefined,
            role: "assistant",
            content: assistantContent,
            timestamp: new Date(),
            metadata: ratingMeta,
          },
        ]);
      }
    } catch {
      // ignore
    } finally {
      wellnessCompleteRef.current = false;
      setActiveActivity(null);
      setActivityPopupOpen(false);
    }
  };

  const confirmDeleteSession = async () => {
    const targetId = sessionToDelete;
    if (!targetId || isDeletingSession) return;
    setIsDeletingSession(true);
    try {
      await deleteChatSession(targetId);
      unregisterChatSessionId(targetId);
      setSessions((prev) => prev.filter((s) => s.sessionId !== targetId));
      setSessionToDelete(null);
      if (sessionId === targetId) {
        await handleNewSession();
      }
    } catch (error) {
      console.error("Failed to delete session:", error);
    } finally {
      setIsDeletingSession(false);
    }
  };

  const handleSessionSelect = async (selectedSessionId: string) => {
    if (selectedSessionId === sessionId) return;
    try {
      setIsChatLoading(true);
      skipSessionInitRef.current = true;
      setSessionId(selectedSessionId);
      await loadSessionIntoState(selectedSessionId);
      window.history.pushState({}, "", `/therapy/${selectedSessionId}`);
    } catch (error) {
      console.error("Failed to load session:", error);
    } finally {
      setIsChatLoading(false);
    }
  };

  const sessionListBusy = isPageLoading || isChatLoading;

  if (!mounted || isPageLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-brand" />
      </div>
    );
  }

  const recentSessions = sessions.filter(
    (s) => !(s.sessionId === sessionId && !hasUserMessages)
  );

  return (
    <>
      <div className="relative mx-auto flex h-full max-w-7xl flex-col px-4 md:px-6">
        <div className="flex min-h-0 flex-1 overflow-hidden rounded-2xl border border-brand-border/30 bg-brand-light">
          {/* Sidebar */}
          <aside className="flex w-72 shrink-0 flex-col overflow-hidden border-r border-brand-border/40 bg-brand-light/80 p-6">
            <div className="mb-8 flex items-center justify-between px-2">
              <h2 className="text-lg font-bold text-gray-800">Chat Sessions</h2>
              <button
                type="button"
                onClick={handleNewSession}
                disabled={sessionListBusy}
                className="text-gray-500 transition-colors hover:text-brand disabled:opacity-50"
                aria-label="New session"
              >
                {sessionListBusy ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <PlusCircle className="h-5 w-5" />
                )}
              </button>
            </div>

            <button
              type="button"
              onClick={handleNewSession}
              disabled={sessionListBusy}
              className="mb-8 flex w-full items-center gap-3 rounded-full border border-brand-border/80 bg-brand-light px-4 py-3 text-left font-medium text-gray-600 transition-all hover:border-brand/40 disabled:opacity-50"
            >
              <MessageSquare className="h-5 w-5 shrink-0" />
              <span>New Session</span>
            </button>

            <ScrollArea className="flex-1">
              <div className="space-y-4">
                <p className="px-2 text-[11px] font-bold uppercase tracking-widest text-gray-400">
                  Recent
                </p>
                <div className="space-y-1">
                  {recentSessions.map((session) => (
                    <div
                      key={session.sessionId}
                      className="group relative flex items-center"
                    >
                      <button
                        type="button"
                        onClick={() => handleSessionSelect(session.sessionId)}
                        className={cn(
                          "w-full rounded-full px-4 py-3 pr-11 text-left text-sm transition-colors",
                          session.sessionId === sessionId
                            ? "bg-brand-light font-medium text-brand"
                            : "text-gray-700 hover:bg-brand-light/60"
                        )}
                      >
                        <span className="line-clamp-2">{getSessionTitle(session)}</span>
                      </button>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSessionToDelete(session.sessionId);
                        }}
                        disabled={isDeletingSession}
                        className="absolute right-2 flex h-8 w-8 items-center justify-center rounded-full text-gray-400 opacity-70 transition-all hover:bg-red-50 hover:text-red-600 sm:opacity-0 sm:group-hover:opacity-100 disabled:opacity-50"
                        aria-label={`Delete ${getSessionTitle(session)}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                  {recentSessions.length === 0 && (
                    <p className="px-4 py-3 text-sm italic text-gray-400">
                      No chat sessions yet
                    </p>
                  )}
                </div>
              </div>
            </ScrollArea>
          </aside>

          {/* Main chat area */}
          <section className="relative flex min-h-0 flex-1 flex-col bg-white/40">
            {isChatLoading && (
              <div
                className="absolute inset-0 z-20 flex items-center justify-center bg-white/70 backdrop-blur-[1px]"
                aria-busy="true"
                aria-label="Loading chat"
              >
                <Loader2 className="h-8 w-8 animate-spin text-brand" />
              </div>
            )}
            {messages.length === 0 && !isTyping ? (
              <div className="relative flex flex-1 flex-col items-center justify-center overflow-hidden p-8 pb-36">
                <div className="bg-arc-decorator opacity-50" aria-hidden />
                <div className="relative z-10 mb-20 w-full max-w-xl space-y-10 text-center">
                  <div className="space-y-4">
                    <div className="mb-2 flex justify-center">
                      <HeliosAvatar size="lg" />
                    </div>
                    <h3 className="text-4xl font-bold text-gray-800">Helios</h3>
                    <p className="text-lg text-gray-500">
                      Tra cứu hoặc trò chuyện về sức khỏe tâm thần — Helios sẽ lắng nghe và hỗ trợ bạn.
                    </p>
                  </div>
                  <div className="w-full space-y-3">
                    {SUGGESTED_QUESTIONS.map((q, index) => (
                      <motion.button
                        key={q.text}
                        type="button"
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.08 }}
                        onClick={() => handleSuggestedQuestion(q.text)}
                        disabled={isTyping}
                        className="prompt-chip w-full rounded-full border border-brand-border/80 bg-brand-light px-6 py-4 text-left text-gray-700 transition-all duration-300 hover:bg-white/80 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {q.text}
                      </motion.button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-3 border-b border-brand-border/50 px-6 py-4">
                  {isHumanChat ? (
                    <motion.div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-600 text-white">
                      <User className="h-5 w-5" />
                    </motion.div>
                  ) : (
                    <HeliosAvatar size="md" />
                  )}
                  <div>
                    <h2 className="font-bold text-gray-800">
                      {isHumanChat
                        ? assignedSupportName || "Chuyên viên"
                        : "Helios"}
                    </h2>
                    <p className="text-xs text-gray-500">
                      {supportMode === "awaiting_support"
                        ? "Đang chờ chuyên viên tham gia..."
                        : `${messages.length} messages`}
                    </p>
                  </div>
                </div>

                {(supportMode === "awaiting_support" || isHumanChat) && (
                  <div className="border-b border-amber-200/80 bg-amber-50 px-6 py-2 text-sm text-amber-900">
                    {isHumanChat
                      ? `Đang trò chuyện với ${assignedSupportName || "chuyên viên"}.`
                      : "Yêu cầu hỗ trợ đã được gửi. Một chuyên viên sẽ tham gia sớm."}
                  </div>
                )}

                <motion.div
                  ref={messagesScrollRef}
                  className="min-h-0 flex-1 overflow-y-auto scroll-smooth"
                >
                  <motion.div className="w-full">
                    <AnimatePresence initial={false}>
                      {messages.map((msg, i) => {
                        if (isSupportOnlyMessage(msg)) return null;

                        if (isChatSystemNotice(msg)) {
                          return (
                            <motion.div
                              key={`${msg.timestamp.toISOString()}-${i}`}
                              initial={{ opacity: 0, y: 8 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{ duration: 0.2 }}
                              className="px-6 py-1"
                            >
                              <ChatSystemNotice content={msg.content} />
                            </motion.div>
                          );
                        }

                        return (
                        <motion.div
                          key={`${msg.timestamp.toISOString()}-${i}`}
                          initial={{ opacity: 0, y: 12 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.25 }}
                          className={cn(
                            "px-6 py-4",
                            msg.role === "user" ? "flex justify-end" : ""
                          )}
                        >
                          <motion.div
                            className={cn(
                              "flex min-w-0 max-w-3/4 gap-4",
                              msg.role === "user"
                                ? "ml-auto flex-row-reverse"
                                : "mr-auto"
                            )}
                          >
                            <div className="mt-1 h-10 w-10 shrink-0">
                              {msg.role === "assistant" ? (
                                <HeliosAvatar />
                              ) : msg.role === "support" ? (
                                <motion.div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-600 text-white">
                                  <User className="h-5 w-5" />
                                </motion.div>
                              ) : msg.role === "user" ? (
                                <motion.div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand text-white">
                                  <User className="h-5 w-5" />
                                </motion.div>
                              ) : (
                                <HeliosAvatar />
                              )}
                            </div>
                            <motion.div
                              className={cn(
                                "min-h-[2rem] min-w-0 space-y-2",
                                msg.role === "user"
                                  ? "flex w-fit max-w-full flex-col items-end"
                                  : "flex-1 overflow-hidden"
                              )}
                            >
                              <div
                                className={cn(
                                  "flex items-center gap-2",
                                  msg.role === "user" && "justify-end"
                                )}
                              >
                                <p className="text-sm font-medium text-gray-800">
                                  {messageSenderLabel(msg)}
                                </p>
                                {msg.role === "assistant" &&
                                  !isHumanChat &&
                                  msg.metadata?.agent_name && (
                                    <Badge
                                      variant="outline"
                                      className="rounded-full text-xs text-gray-600"
                                    >
                                      {String(msg.metadata.agent_name)}
                                    </Badge>
                                  )}
                                {msg.role === "assistant" &&
                                  getRetrievalSummary(msg.metadata) && (
                                    <Badge
                                      variant="outline"
                                      className="gap-1 rounded-full border-brand-border bg-white text-xs text-gray-600"
                                      title={getRetrievalSummary(msg.metadata) ?? undefined}
                                    >
                                      <BookOpenCheck className="h-3 w-3" />
                                      Sourced
                                    </Badge>
                                  )}
                              </div>

                              {msg.role === "user" ? (
                                <motion.div className="inline-block w-fit max-w-full rounded-2xl bg-brand px-4 py-3 text-left text-white">
                                  {typeof msg.metadata?.image_url === "string" && (
                                    <img
                                      src={msg.metadata.image_url}
                                      alt="Uploaded medical image"
                                      className="mb-2 max-h-64 rounded-lg border border-white/20 object-contain"
                                    />
                                  )}
                                  <ChatMessageMarkdown
                                    content={msg.content}
                                    className="text-white [&_a]:text-white [&_p]:text-white [&_strong]:text-white"
                                  />
                                </motion.div>
                              ) : msg.role === "system" ? (
                                <motion.div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-600">
                                  <ChatMessageMarkdown content={msg.content} />
                                </motion.div>
                              ) : (
                                <AssistantMessageBubble variant="medical">
                                  <ChatMessageMarkdown content={msg.content} />
                                </AssistantMessageBubble>
                              )}

                              {msg.role === "assistant" &&
                                !isHumanChat &&
                                (() => {
                                  type ActivityEntry = { id: string; title: string };
                                  const activityIds = getSuggestedActivities(msg.metadata);
                                  const suggestedList = Array.isArray(
                                    msg.metadata?.suggested_activities
                                  )
                                    ? (msg.metadata.suggested_activities as Array<{
                                        id: string;
                                        title?: string;
                                      }>)
                                    : [];
                                  const entries: ActivityEntry[] =
                                    suggestedList.length > 0
                                      ? suggestedList.map((s) => ({
                                          id: s.id,
                                          title: s.title || s.id,
                                        }))
                                      : activityIds.map((id: string) => ({
                                          id,
                                          title: resolveActivity(id)?.title || id,
                                        }));
                                  if (!entries.length) return null;
                                  return (
                                    <div className="mt-3 flex flex-wrap gap-2">
                                      {entries.map((entry) => (
                                        <Button
                                          key={entry.id}
                                          size="sm"
                                          className="rounded-full bg-brand hover:bg-brand/90"
                                          onClick={() => void openActivity(entry.id)}
                                        >
                                          {`Mở: ${entry.title}`}
                                        </Button>
                                      ))}
                                    </div>
                                  );
                                })()}

                              {msg.role === "assistant" &&
                                isHandoffConsentPrompt(msg.metadata) && (
                                  <HandoffConsentCard
                                    onConnect={() => void handleHandoffConfirm()}
                                    onNewSession={() => void handleHandoffNewSession()}
                                    disabled={supportMode !== "ai"}
                                    loading={handoffConfirmLoading}
                                  />
                                )}

                              {msg.role === "assistant" &&
                                Boolean(msg.metadata?.pending_activity_rating) &&
                                sessionId &&
                                msg.metadata?.pending_activity_rating && (
                                  <ActivityStarRating
                                    sessionId={sessionId}
                                    messageId={msg.id}
                                    activityId={
                                      (msg.metadata.pending_activity_rating as {
                                        activity_id: string;
                                      }).activity_id
                                    }
                                    completionId={
                                      (msg.metadata.pending_activity_rating as {
                                        completion_id: string;
                                      }).completion_id
                                    }
                                    initialRating={
                                      (msg.metadata.pending_activity_rating as {
                                        rating?: number;
                                      }).rating
                                    }
                                    readOnly={Boolean(
                                      (msg.metadata.pending_activity_rating as {
                                        rated?: boolean;
                                      }).rated
                                    )}
                                    initialThanks={
                                      typeof msg.metadata.rating_thanks === "string"
                                        ? msg.metadata.rating_thanks
                                        : undefined
                                    }
                                    lang="vi"
                                    onRated={(rating, thankMessage) => {
                                      const pending = msg.metadata?.pending_activity_rating as
                                        | {
                                            activity_id: string;
                                            completion_id: string;
                                            rated?: boolean;
                                            rating?: number;
                                          }
                                        | undefined;
                                      if (!pending) return;
                                      setMessages((prev) =>
                                        prev.map((m) =>
                                          msg.id && m.id === msg.id
                                            ? {
                                                ...m,
                                                metadata: {
                                                  ...m.metadata,
                                                  pending_activity_rating: {
                                                    ...pending,
                                                    rated: true,
                                                    rating,
                                                  },
                                                  rating_thanks: thankMessage,
                                                },
                                              }
                                            : m === msg
                                              ? {
                                                  ...m,
                                                  metadata: {
                                                    ...m.metadata,
                                                    pending_activity_rating: {
                                                      ...pending,
                                                      rated: true,
                                                      rating,
                                                    },
                                                    rating_thanks: thankMessage,
                                                  },
                                                }
                                              : m
                                        )
                                      );
                                    }}
                                  />
                                )}
                            </motion.div>
                          </motion.div>
                        </motion.div>
                        );
                      })}
                    </AnimatePresence>

                    {isTyping && !isHumanChat && (
                      <HeliosTypingIndicator statusMessage={typingStatus} />
                    )}
                    <div ref={messagesEndRef} />
                  </motion.div>
                </motion.div>
              </>
            )}

            {/* Input area */}
            <div
              className={cn(
                "z-20 shrink-0 px-6 pb-6 pt-4",
                messages.length === 0
                  ? "absolute bottom-0 left-0 right-0"
                  : "border-t border-brand-border/40"
              )}
            >
              <div className="w-full space-y-3">
                <form onSubmit={handleSubmit} className="min-w-0">
                  <div
                    className={cn(
                      "flex flex-col rounded-2xl border-2 bg-brand-light transition-all focus-within:border-brand",
                      voiceInput.isRecording
                        ? "border-red-300 ring-2 ring-red-100"
                        : "border-brand-border/80",
                      isTyping && "opacity-50"
                    )}
                  >
                    {voiceInput.isRecording && (
                      <VoiceRecordingVisualizer level={voiceInput.audioLevel} />
                    )}
                    <textarea
                      value={message}
                      onChange={(e) => setMessage(e.target.value)}
                      placeholder={
                        voiceInput.isRecording
                          ? "Listening to your voice..."
                          : "Chia sẻ hoặc hỏi về sức khỏe tâm thần..."
                      }
                      rows={1}
                      disabled={isTyping}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          handleSubmit(e);
                        }
                      }}
                      className={cn(
                        "w-full resize-none border-0 bg-transparent px-4 pb-1 pt-3 text-gray-700 outline-none placeholder:text-gray-400 focus:ring-0",
                        "min-h-[44px] max-h-[120px]",
                        isTyping && "cursor-not-allowed"
                      )}
                    />
                    <div className="flex items-center justify-between gap-2 px-2 pb-2">
                      <div className="flex items-center gap-1">
                        <HandoffButton
                          onClick={() => void handleHandoffRequest()}
                          disabled={isTyping || supportMode !== "ai"}
                          loading={handoffLoading}
                        />
                        <VoiceMicButton
                          toggle={voiceInput.toggle}
                          isRecording={voiceInput.isRecording}
                          isTranscribing={voiceInput.isTranscribing}
                          disabled={isTyping}
                        />
                      </div>
                      <button
                        type="submit"
                        disabled={isTyping || !message.trim()}
                        className="rounded-full bg-slate-700 p-2.5 text-white transition-all hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                        aria-label="Send message"
                      >
                        <Send className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </form>
                {speechError && (
                  <p className="px-1 text-xs text-red-500">{speechError}</p>
                )}
              </div>

              <p className="mt-4 w-full text-center text-[10px] italic text-gray-400">
                Helios chỉ cung cấp thông tin tham khảo và hỗ trợ sức khỏe tâm thần,
                không thay thế chẩn đoán hay điều trị chuyên môn. Hãy liên hệ chuyên gia
                khi cần hỗ trợ lâm sàng hoặc trong tình huống khẩn cấp.
              </p>
            </div>
          </section>
        </div>
      </div>

      <AlertDialog
        open={sessionToDelete !== null}
        onOpenChange={(open) => {
          if (!open && !isDeletingSession) setSessionToDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this chat?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently remove the conversation and its messages. This
              action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeletingSession}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={isDeletingSession}
              className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
              onClick={(e) => {
                e.preventDefault();
                void confirmDeleteSession();
              }}
            >
              {isDeletingSession ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deleting…
                </>
              ) : (
                "Delete"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <ActivityPopupHost
        activity={activeActivity}
        open={activityPopupOpen}
        onOpenChange={setActivityPopupOpen}
        onComplete={() => void handleWellnessComplete()}
      />
    </>
  );
}
