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
  AlertTriangle,
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
  chatModeStorageKey,
  type ChatMode,
} from "@/lib/api/chat";
import { ChatModeToggle } from "@/components/therapy/chat-mode-toggle";
import { VoiceMicButton } from "@/components/therapy/voice-mic-button";
import { VoiceRecordingVisualizer } from "@/components/therapy/voice-recording-visualizer";
import { useSpeechToText } from "@/hooks/use-speech-to-text";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MessageFeedback } from "@/components/therapy/message-feedback";
import { QuickReplyChips } from "@/components/therapy/quick-reply-chips";
import { HeliosAvatar } from "@/components/therapy/helios-avatar";
import { LunaAvatar } from "@/components/therapy/luna-avatar";
import { LunaTypingIndicator } from "@/components/therapy/luna-typing-indicator";
import { startWellnessSession, completeWellnessSession, getActivityCatalog, type WellnessActivity } from "@/lib/api/wellness";
import { ActivityPopupHost } from "@/components/activities/activity-popup-host";
import { ActivityStarRating } from "@/components/activities/activity-star-rating";
import type { QuickReply, CrisisChoice } from "@/lib/api/chat";
import {
  CRISIS_CHIP_PREFIX,
  formatMessageForDisplay,
  normalizeCrisisChoices,
} from "@/lib/api/chat";
import { fetchCurrentUser, linkChatSession } from "@/lib/api/auth";
import { getDefaultLunaGreeting, getDefaultMedicalGreeting } from "@/lib/luna-greeting";
import { registerChatSessionId, unregisterChatSessionId } from "@/lib/session";

const MEDICAL_SUGGESTED_QUESTIONS = [
  { text: "What are common symptoms of HIV/AIDS?" },
  { text: "Explain how antiretroviral therapy works" },
  { text: "What should I know about infectious disease prevention?" },
];

const SUGGESTED_QUESTIONS = [
  { text: "How can I manage anxiety better?" },
  { text: "I've been feeling a lot of pressure lately" },
  { text: "I want to talk about my sleep" },
  { text: "I need help with work-life balance" },
];

const EMOTION_LABELS: Record<string, string> = {
  anxiety: "Anxious",
  sadness: "Sad",
  anger: "Angry",
  hopeless: "Hopeless",
  neutral: "Neutral",
  overwhelmed: "Overwhelmed",
  lonely: "Lonely",
  grief: "Grief",
  fear: "Afraid",
  shame: "Ashamed",
  guilt: "Guilty",
  joy: "Joyful",
};

const DEFAULT_SESSION_TITLES = new Set([
  "New chat",
  "Chat",
  "New conversation",
  "Cuộc trò chuyện mới",
]);

async function welcomeMessages(mode: ChatMode): Promise<ChatMessage[]> {
  if (mode === "medical") {
    return [
      {
        role: "assistant",
        content: getDefaultMedicalGreeting(),
        timestamp: new Date(),
        metadata: { chat_mode: "medical", message_type: "medical" },
      },
    ];
  }
  const user = await fetchCurrentUser();
  return [
    {
      role: "assistant",
      content: getDefaultLunaGreeting(user?.name),
      timestamp: new Date(),
      metadata: { chat_mode: "psychologist" },
    },
  ];
}

function resolveChatModeFromHistory(history: ChatMessage[]): ChatMode {
  for (const msg of history) {
    const m = msg.metadata?.chat_mode;
    if (m === "medical" || m === "psychologist") return m;
  }
  return "psychologist";
}

function quickRepliesFromMessages(msgs: ChatMessage[]): QuickReply[] {
  const last = [...msgs].reverse().find((m) => m.role === "assistant");
  if (!last?.metadata) return [];
  const raw = last.metadata.quick_replies;
  if (!Array.isArray(raw)) return [];
  return (raw as QuickReply[]).slice(0, 3);
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
  // Crisis state
  const [crisisChoices, setCrisisChoices] = useState<CrisisChoice[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(
    params.sessionId as string
  );
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [inputQuickReplies, setInputQuickReplies] = useState<QuickReply[]>([]);
  const [chatMode, setChatMode] = useState<ChatMode>("psychologist");
  const [speechError, setSpeechError] = useState<string | null>(null);
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null);
  const [isDeletingSession, setIsDeletingSession] = useState(false);

  const hasUserMessages = messages.some((m) => m.role === "user");
  const isMedicalMode = chatMode === "medical";

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

  const applyHistoryToChat = (
    activeSessionId: string,
    mapped: ChatMessage[]
  ) => {
    const restoredMode = resolveChatModeFromHistory(mapped);
    setChatMode(restoredMode);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(
        chatModeStorageKey(activeSessionId),
        restoredMode
      );
    }
    setMessages(mapped);
    const last = [...mapped].reverse().find((m) => m.role === "assistant");
    if (restoredMode === "medical") {
      setCrisisChoices([]);
      setInputQuickReplies([]);
      return;
    }
    const restoredChoices = normalizeCrisisChoices(last?.metadata?.crisis_choices);
    if (last?.metadata?.chat_blocked && restoredChoices.length > 0) {
      setCrisisChoices(restoredChoices);
      setInputQuickReplies([]);
    } else {
      setCrisisChoices([]);
      setInputQuickReplies(quickRepliesFromMessages(mapped));
    }
  };

  const loadSessionIntoState = async (activeSessionId: string) => {
    registerChatSessionId(activeSessionId);
    try {
      await linkChatSession(activeSessionId);
    } catch {
      /* optional */
    }
    try {
      const history = await getChatHistory(activeSessionId);
      if (Array.isArray(history) && history.length > 0) {
        const mapped = history.map((msg) => ({
          ...msg,
          timestamp: new Date(msg.timestamp),
        }));
        applyHistoryToChat(activeSessionId, mapped);
        return;
      }
      const stored =
        typeof window !== "undefined"
          ? (window.localStorage.getItem(
              chatModeStorageKey(activeSessionId)
            ) as ChatMode | null)
          : null;
      const mode: ChatMode = stored === "medical" ? "medical" : "psychologist";
      setChatMode(mode);
      setMessages(await welcomeMessages(mode));
      setInputQuickReplies([]);
      setCrisisChoices([]);
    } catch {
      setMessages(await welcomeMessages("psychologist"));
      setChatMode("psychologist");
      setInputQuickReplies([]);
      setCrisisChoices([]);
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
      };
      setSessions((prev) => [newSession, ...prev]);
      skipSessionInitRef.current = true;
      setSessionId(newSessionId);
      try {
        await linkChatSession(newSessionId);
      } catch {
        /* optional — chat still links on first message */
      }
      setChatMode("psychologist");
      if (typeof window !== "undefined") {
        window.localStorage.setItem(
          chatModeStorageKey(newSessionId),
          "psychologist"
        );
      }
      setMessages(await welcomeMessages("psychologist"));
      setInputQuickReplies([]);
      setCrisisChoices([]);
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
  }, [messages, isTyping]);

  useEffect(() => {
    setMounted(true);
  }, []);

  const sendUserMessage = async (
    text: string,
    options?: { displayContent?: string }
  ) => {
    const currentMessage = text.trim();
    if (!currentMessage || isTyping || !sessionId) return;
    const displayContent = formatMessageForDisplay(
      options?.displayContent?.trim() || currentMessage
    );

    setIsTyping(true);
    setTypingStatus("Analyzing your request");
    setInputQuickReplies([]);
    setMessages((prev) => [
      ...prev,
      { role: "user", content: displayContent, timestamp: new Date() },
    ]);
    scrollToBottom();

    try {
      const response = await sendChatMessageWithStatus(
        sessionId,
        currentMessage,
        chatMode,
        (label) => setTypingStatus(label)
      );

      let quickReplies: QuickReply[] = [];
      if (chatMode === "medical") {
        setCrisisChoices([]);
        setInputQuickReplies([]);
      } else {
        const nextCrisisChoices = response.crisis_choices ?? [];
        const blocked = Boolean(
          response.chat_blocked ?? response.metadata?.chat_blocked
        );
        if (blocked && nextCrisisChoices.length > 0) {
          setCrisisChoices(nextCrisisChoices);
          setInputQuickReplies([]);
        } else {
          setCrisisChoices([]);
          quickReplies = (
            (response.quick_replies as QuickReply[] | undefined) ||
            (response.metadata?.quick_replies as QuickReply[] | undefined) ||
            []
          ).slice(0, 3);
          setInputQuickReplies(quickReplies);
        }
      }

      // Auto-open the appropriate wellness popup when an activity is chosen.
      if (chatMode === "psychologist" && response.crisis_stage === "overwhelm_doing") {
        const activityChip =
          (response.metadata?.crisis_chip_id as string | undefined) ?? "";
        if (activityChip === "crisis:calming_music") {
          void openOcean();
        } else {
          // slow_breathing or grounding_exercise — open breathing popup
          void openBreathing();
        }
      }

      setMessages((prev) => [
        ...prev,
        {
          id: response.assistant_message_id,
          role: "assistant",
          content:
            response.response ||
            response.message ||
            (chatMode === "medical"
              ? "I could not generate a response. Please try again."
              : "I'm here with you. Would you like to share more?"),
          timestamp: new Date(),
          metadata: {
            message_type: response.message_type,
            chat_blocked: response.chat_blocked,
            crisis_choices: response.crisis_choices,
            crisis_stage: response.crisis_stage,
            emotion: response.emotion,
            therapy_strategy: response.therapy_strategy,
            quick_replies: quickReplies,
            chat_mode: chatMode,
            ...(response.metadata || {}),
          },
        },
      ]);

      // PHQ-2 is now analysed implicitly from conversation signals
    } catch (err) {
      console.error("Chat stream failed:", err);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, I'm having connection issues. Please try again later.",
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsTyping(false);
      setTypingStatus(null);
      scrollToBottom();
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isTyping) return;
    if (!isMedicalMode && crisisChoices.length > 0) return;

    const currentMessage = message.trim();
    if (!currentMessage) return;
    setMessage("");
    await sendUserMessage(currentMessage);
  };

  const handleChatModeChange = (mode: ChatMode) => {
    if (hasUserMessages) return;
    setChatMode(mode);
    if (sessionId && typeof window !== "undefined") {
      window.localStorage.setItem(chatModeStorageKey(sessionId), mode);
    }
    void (async () => {
      setMessages(await welcomeMessages(mode));
      setCrisisChoices([]);
      setInputQuickReplies([]);
    })();
  };

  const handleSuggestedQuestion = (text: string) => {
    setMessage("");
    void sendUserMessage(text);
  };

  const handleCrisisChoice = (choice: CrisisChoice) => {
    void sendUserMessage(`${CRISIS_CHIP_PREFIX}${choice.id}`, {
      displayContent: choice.label,
    });
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
        chatMode,
      });
    } catch {
      /* popup still opens */
    }
  };

  const openBreathing = async () => {
    await openActivity("breathing_box");
  };

  const openOcean = async () => {
    await openActivity("ocean_sound");
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
              chat_mode: chatMode,
            }
          : { chat_mode: chatMode };

      const assistantContent =
        result.checkin_message ||
        (result.show_activity_rating
          ? chatMode === "medical"
            ? "Bạn vừa hoàn thành bài tập. Bạn đánh giá thế nào?"
            : "You finished the activity. How was it?"
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
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(chatModeStorageKey(targetId));
      }
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

  const latestFeedbackMessageId = (() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const msg = messages[i];
      if (
        msg.role === "assistant" &&
        msg.metadata?.show_micro_feedback &&
        msg.id
      ) {
        return msg.id;
      }
    }
    return null;
  })();

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
            {messages.length === 0 ? (
              <div className="relative flex flex-1 flex-col items-center justify-center overflow-hidden p-8 pb-36">
                <div className="bg-arc-decorator opacity-50" aria-hidden />
                <div className="relative z-10 mb-20 w-full max-w-xl space-y-10 text-center">
                  <div className="space-y-4">
                    <div className="mb-2 flex justify-center">
                      {isMedicalMode ? (
                        <HeliosAvatar size="lg" />
                      ) : (
                        <LunaAvatar size="lg" />
                      )}
                    </div>
                    <h3 className="text-4xl font-bold text-gray-800">
                      {isMedicalMode ? "Helios" : "Luna"}
                    </h3>
                    <p className="text-lg text-gray-500">
                      {isMedicalMode
                        ? "Hỏi Helios hoặc đính kèm ảnh, thêm ghi chú nếu cần, rồi bấm gửi."
                        : "How can I help you today?"}
                    </p>
                  </div>
                  <div className="w-full space-y-3">
                    {(isMedicalMode ? MEDICAL_SUGGESTED_QUESTIONS : SUGGESTED_QUESTIONS).map((q, index) => (
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
                  {isMedicalMode ? (
                    <HeliosAvatar size="md" />
                  ) : (
                    <LunaAvatar size="md" />
                  )}
                  <div>
                    <h2 className="font-bold text-gray-800">
                      {isMedicalMode ? "Helios" : "Luna"}
                    </h2>
                    <p className="text-xs text-gray-500">
                      {messages.length} messages
                    </p>
                  </div>
                </div>

                <motion.div
                  ref={messagesScrollRef}
                  className="min-h-0 flex-1 overflow-y-auto scroll-smooth"
                >
                  <motion.div className="w-full">
                    <AnimatePresence initial={false}>
                      {messages.map((msg, i) => (
                        <motion.div
                          key={`${msg.timestamp.toISOString()}-${i}`}
                          initial={{ opacity: 0, y: 12 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.25 }}
                          className={cn(
                            "px-6 py-4",
                            msg.role === "assistant"
                              ? msg.metadata?.message_type === "crisis"
                                ? "bg-red-50/40"
                                : ""
                              : "flex justify-end"
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
                                msg.metadata?.message_type === "crisis" ? (
                                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-100 text-red-600 ring-1 ring-red-200">
                                    <AlertTriangle className="h-5 w-5" />
                                  </div>
                                ) : msg.metadata?.chat_mode === "medical" ||
                                  isMedicalMode ? (
                                  <HeliosAvatar />
                                ) : (
                                  <LunaAvatar />
                                )
                              ) : (
                                <motion.div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand text-white">
                                  <User className="h-5 w-5" />
                                </motion.div>
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
                                  {msg.role === "assistant"
                                    ? msg.metadata?.chat_mode === "medical" ||
                                      isMedicalMode
                                      ? "Helios"
                                      : "Luna"
                                    : "You"}
                                </p>
                                {msg.role === "assistant" &&
                                  msg.metadata?.agent_name && (
                                    <Badge
                                      variant="outline"
                                      className="rounded-full text-xs text-gray-600"
                                    >
                                      {String(msg.metadata.agent_name)}
                                    </Badge>
                                  )}
                                {/* Emotion badge */}
                                {!isMedicalMode &&
                                  msg.role === "assistant" &&
                                  msg.metadata?.emotion &&
                                  msg.metadata.emotion !== "neutral" && (
                                  <Badge
                                    variant="secondary"
                                    className="rounded-full border-brand-border bg-brand-light text-xs text-brand"
                                  >
                                    {EMOTION_LABELS[msg.metadata.emotion as string] ?? msg.metadata.emotion}
                                  </Badge>
                                )}
                                {msg.role === "assistant" &&
                                  msg.metadata?.message_type !== "crisis" &&
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
                              ) : (
                                <AssistantMessageBubble
                                  variant={
                                    msg.metadata?.message_type === "crisis"
                                      ? "crisis"
                                      : msg.metadata?.chat_mode === "medical" ||
                                          isMedicalMode
                                        ? "medical"
                                        : "default"
                                  }
                                >
                                  <ChatMessageMarkdown content={msg.content} />
                                </AssistantMessageBubble>
                              )}

                              {msg.role === "assistant" &&
                                msg.metadata?.show_micro_feedback &&
                                msg.id === latestFeedbackMessageId &&
                                sessionId && (
                                  <MessageFeedback
                                    sessionId={sessionId}
                                    assistantMessageId={msg.id}
                                  />
                                )}

                              {/* Wellness activity buttons */}
                              {msg.role === "assistant" &&
                                msg.metadata?.message_type !== "crisis" &&
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
                                          {isMedicalMode
                                            ? `Mở: ${entry.title}`
                                            : `Open: ${entry.title}`}
                                        </Button>
                                      ))}
                                    </div>
                                  );
                                })()}

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
                                    chatMode={chatMode}
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
                      ))}
                    </AnimatePresence>

                    {isTyping && (
                      <LunaTypingIndicator
                        label={isMedicalMode ? "Helios" : "Luna"}
                        variant={isMedicalMode ? "helios" : "luna"}
                        statusMessage={typingStatus}
                      />
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
              {!isMedicalMode && crisisChoices.length > 0 ? (
                <div className="w-full">
                  <div className="grid grid-cols-2 gap-2">
                    {crisisChoices.map((choice) => (
                      <button
                        key={choice.id}
                        type="button"
                        disabled={isTyping}
                        onClick={() => handleCrisisChoice(choice)}
                        className="rounded-xl border border-brand-border/80 bg-white px-4 py-3 text-sm text-gray-700 transition-colors hover:border-brand/40 hover:bg-brand-light disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {choice.label}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="w-full space-y-3">
                  {!isMedicalMode && inputQuickReplies.length > 0 && (
                    <QuickReplyChips
                      replies={inputQuickReplies}
                      onSelect={(text) => void sendUserMessage(text)}
                      disabled={isTyping}
                    />
                  )}
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
                            : isMedicalMode
                              ? "Hỏi Helios về y khoa..."
                              : "Share what's on your mind..."
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
                          <ChatModeToggle
                            value={chatMode}
                            onChange={handleChatModeChange}
                            disabled={hasUserMessages || isTyping}
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
                          className={cn(
                            "rounded-full p-2.5 text-white transition-all disabled:cursor-not-allowed disabled:opacity-50",
                            isMedicalMode
                              ? "bg-slate-700 hover:bg-slate-800"
                              : "bg-brand/80 hover:bg-brand"
                          )}
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
              )}

              <p className="mt-4 w-full text-center text-[10px] italic text-gray-400">
                {isMedicalMode
                  ? "Helios provides reference information only and does not replace medical diagnosis. Always consult a licensed physician."
                  : "Luna offers emotional support, not medical diagnosis. If you are in crisis, contact a professional immediately."}
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
