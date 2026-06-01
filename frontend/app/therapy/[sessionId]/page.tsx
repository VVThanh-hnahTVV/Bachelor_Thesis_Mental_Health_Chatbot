"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  Send,
  User,
  Loader2,
  Moon,
  MessageSquare,
  PlusCircle,
  AlertTriangle,
  BookOpenCheck,
  ImagePlus,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import {
  AssistantMessageBubble,
  ChatMessageMarkdown,
} from "@/components/therapy/chat-message-markdown";
import { BreathingGame } from "@/components/games/breathing-game";
import { OceanWaves } from "@/components/games/ocean-waves";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  createChatSession,
  sendChatMessage,
  getChatHistory,
  ChatMessage,
  getAllChatSessions,
  ChatSession,
  uploadMedicalImage,
  validateMedicalOutput,
  chatModeStorageKey,
  type ChatMode,
} from "@/lib/api/chat";
import { ChatModeToggle } from "@/components/therapy/chat-mode-toggle";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MessageFeedback } from "@/components/therapy/message-feedback";
import { QuickReplyChips } from "@/components/therapy/quick-reply-chips";
import { LunaAvatar } from "@/components/therapy/luna-avatar";
import { LunaTypingIndicator } from "@/components/therapy/luna-typing-indicator";
import { startWellnessSession, completeWellnessSession } from "@/lib/api/wellness";
import type { QuickReply, CrisisChoice } from "@/lib/api/chat";
import {
  CRISIS_CHIP_PREFIX,
  formatMessageForDisplay,
  normalizeCrisisChoices,
} from "@/lib/api/chat";
import { fetchCurrentUser, linkChatSession } from "@/lib/api/auth";
import { getDefaultLunaGreeting, getDefaultMedicalGreeting } from "@/lib/luna-greeting";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const MEDICAL_SUGGESTED_QUESTIONS = [
  { text: "What are common symptoms of brain tumors?" },
  { text: "Explain chest X-ray findings for COVID-19" },
  { text: "How is skin lesion analysis performed?" },
];

const SUGGESTED_QUESTIONS = [
  { text: "Làm thế nào để quản lý lo lắng tốt hơn?" },
  { text: "Gần đây tôi cảm thấy rất áp lực" },
  { text: "Tôi muốn nói về giấc ngủ của mình" },
  { text: "Tôi cần giúp đỡ về cân bằng cuộc sống" },
];

const EMOTION_LABELS: Record<string, string> = {
  anxiety: "Lo lắng",
  sadness: "Buồn bã",
  anger: "Tức giận",
  hopeless: "Tuyệt vọng",
  neutral: "Bình thường",
  overwhelmed: "Quá tải",
  lonely: "Cô đơn",
  grief: "Đau buồn",
  fear: "Sợ hãi",
  shame: "Xấu hổ",
  guilt: "Tội lỗi",
  joy: "Vui vẻ",
};

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
  const first =
    session.messages.find((m) => m.role === "user")?.content ||
    session.messages[0]?.content;
  if (!first) return "Cuộc trò chuyện mới";
  const trimmed = first.trim();
  if (trimmed.length <= 36) return trimmed;
  return `${trimmed.slice(0, 36)}…`;
}

export default function TherapyPage() {
  const params = useParams();
  const [message, setMessage] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesScrollRef = useRef<HTMLDivElement>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [mounted, setMounted] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [showBreathingPopup, setShowBreathingPopup] = useState(false);
  const [showOceanPopup, setShowOceanPopup] = useState(false);
  // Crisis state
  const [crisisChoices, setCrisisChoices] = useState<CrisisChoice[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(
    params.sessionId as string
  );
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [inputQuickReplies, setInputQuickReplies] = useState<QuickReply[]>([]);
  const [chatMode, setChatMode] = useState<ChatMode>("psychologist");
  const [pendingMedicalValidation, setPendingMedicalValidation] = useState(false);
  const imageInputRef = useRef<HTMLInputElement>(null);

  const hasUserMessages = messages.some((m) => m.role === "user");
  const isMedicalMode = chatMode === "medical";

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
      ? `Dựa trên kiến thức: ${topics.join(", ")}`
      : "Dựa trên kiến thức đã tuyển chọn";
  };

  const handleNewSession = async () => {
    try {
      setIsLoading(true);
      const newSessionId = await createChatSession();
      const newSession: ChatSession = {
        sessionId: newSessionId,
        messages: [],
        createdAt: new Date(),
        updatedAt: new Date(),
      };
      setSessions((prev) => [newSession, ...prev]);
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
      setPendingMedicalValidation(false);
      window.history.pushState({}, "", `/therapy/${newSessionId}`);
    } catch (error) {
      console.error("Failed to create new session:", error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const initChat = async () => {
      try {
        setIsLoading(true);
        let activeSessionId = sessionId;
        if (!activeSessionId || activeSessionId === "new") {
          activeSessionId = await createChatSession();
          setSessionId(activeSessionId);
          window.history.pushState({}, "", `/therapy/${activeSessionId}`);
        }
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
            const restoredMode = resolveChatModeFromHistory(mapped);
            setChatMode(restoredMode);
            if (typeof window !== "undefined" && activeSessionId) {
              window.localStorage.setItem(
                chatModeStorageKey(activeSessionId),
                restoredMode
              );
            }
            setMessages(mapped);
            const last = [...mapped].reverse().find((m) => m.role === "assistant");
            setPendingMedicalValidation(
              Boolean(last?.metadata?.needs_validation)
            );
            if (restoredMode === "medical") {
              setCrisisChoices([]);
              setInputQuickReplies([]);
            } else {
              setInputQuickReplies(quickRepliesFromMessages(mapped));
              const restoredChoices = normalizeCrisisChoices(
                last?.metadata?.crisis_choices
              );
              if (
                last?.metadata?.chat_blocked &&
                restoredChoices.length > 0
              ) {
                setCrisisChoices(restoredChoices);
                setInputQuickReplies([]);
              } else {
                setCrisisChoices([]);
              }
            }
          } else {
            const stored =
              typeof window !== "undefined" && activeSessionId
                ? (window.localStorage.getItem(
                    chatModeStorageKey(activeSessionId)
                  ) as ChatMode | null)
                : null;
            const mode: ChatMode =
              stored === "medical" ? "medical" : "psychologist";
            setChatMode(mode);
            setMessages(await welcomeMessages(mode));
            setInputQuickReplies([]);
            setPendingMedicalValidation(false);
          }
        } catch {
          setMessages(await welcomeMessages("psychologist"));
          setChatMode("psychologist");
          setInputQuickReplies([]);
        }
      } catch {
        setMessages([
          {
            role: "assistant",
            content: "Xin lỗi, đã có lỗi khi tải phiên trò chuyện. Vui lòng thử lại.",
            timestamp: new Date(),
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    };
    initChat();
  }, [sessionId]);

  useEffect(() => {
    const loadSessions = async () => {
      try {
        const allSessions = await getAllChatSessions();
        setSessions(allSessions);
      } catch (error) {
        console.error("Failed to load sessions:", error);
      }
    };
    loadSessions();
  }, [messages]);

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
    setInputQuickReplies([]);
    setMessages((prev) => [
      ...prev,
      { role: "user", content: displayContent, timestamp: new Date() },
    ]);
    scrollToBottom();

    try {
      const response = await sendChatMessage(sessionId, currentMessage, chatMode);

      let quickReplies: QuickReply[] = [];
      if (chatMode === "medical") {
        setCrisisChoices([]);
        setInputQuickReplies([]);
        setPendingMedicalValidation(
          Boolean(response.metadata?.needs_validation)
        );
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
        setPendingMedicalValidation(false);
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

      const resultImage = response.metadata?.result_image as string | undefined;
      const imageUrl = resultImage
        ? resultImage.startsWith("http")
          ? resultImage
          : `${API_BASE}${resultImage}`
        : undefined;

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
              : "Mình ở đây với bạn. Bạn có thể chia sẻ thêm không?"),
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
            ...(imageUrl ? { result_image: imageUrl } : {}),
          },
        },
      ]);

      // PHQ-2 is now analysed implicitly from conversation signals
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Xin lỗi, mình đang gặp sự cố kết nối. Vui lòng thử lại sau.",
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsTyping(false);
      scrollToBottom();
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const currentMessage = message.trim();
    if (!currentMessage || isTyping) return;
    if (!isMedicalMode && crisisChoices.length > 0) return;
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
      setPendingMedicalValidation(false);
    })();
  };

  const handleImageUpload = async (file: File) => {
    if (!sessionId || isTyping || chatMode !== "medical") return;
    setIsTyping(true);
    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: `[Uploaded image: ${file.name}]`,
        timestamp: new Date(),
      },
    ]);
    try {
      const response = await uploadMedicalImage(sessionId, file, message.trim());
      setMessage("");
      const resultImage = response.metadata?.result_image as string | undefined;
      const imageUrl = resultImage
        ? resultImage.startsWith("http")
          ? resultImage
          : `${API_BASE}${resultImage}`
        : undefined;
      setPendingMedicalValidation(
        Boolean(response.metadata?.needs_validation)
      );
      setMessages((prev) => [
        ...prev,
        {
          id: response.assistant_message_id,
          role: "assistant",
          content: response.response || response.message || "",
          timestamp: new Date(),
          metadata: {
            chat_mode: "medical",
            message_type: "medical",
            ...(response.metadata || {}),
            ...(imageUrl ? { result_image: imageUrl } : {}),
          },
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, image analysis failed. Please try again.",
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleMedicalValidation = async (result: "yes" | "no", comments?: string) => {
    if (!sessionId || isTyping) return;
    setIsTyping(true);
    setPendingMedicalValidation(false);
    try {
      const response = await validateMedicalOutput(sessionId, result, comments);
      setMessages((prev) => [
        ...prev,
        {
          role: "user",
          content: result === "yes" ? "Yes, confirmed." : `No. ${comments || ""}`.trim(),
          timestamp: new Date(),
        },
        {
          id: response.assistant_message_id,
          role: "assistant",
          content: response.response || response.message || "",
          timestamp: new Date(),
          metadata: { chat_mode: "medical", ...(response.metadata || {}) },
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Validation could not be processed. Please try again.",
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsTyping(false);
    }
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

  const openBreathing = async () => {
    if (!sessionId) return;
    setShowBreathingPopup(true);
    try {
      await startWellnessSession(sessionId, "breathing_box", { quiet: true, lang: "en" });
    } catch {
      /* popup still opens */
    }
  };

  const openOcean = async () => {
    if (!sessionId) return;
    setShowOceanPopup(true);
    try {
      await startWellnessSession(sessionId, "ocean_sound", { quiet: true, lang: "en" });
    } catch {
      /* popup still opens */
    }
  };

  const handleWellnessComplete = async () => {
    if (!sessionId) return;
    try {
      const { checkin_message, show_micro_feedback } =
        await completeWellnessSession(sessionId, { lang: "en" });
      if (checkin_message) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: checkin_message,
            timestamp: new Date(),
            metadata: { show_micro_feedback },
          },
        ]);
      }
    } catch {
      // ignore
    }
  };

  const handleSessionSelect = async (selectedSessionId: string) => {
    if (selectedSessionId === sessionId) return;
    try {
      setIsLoading(true);
      const history = await getChatHistory(selectedSessionId);
      if (Array.isArray(history)) {
        const mapped = history.map((msg) => ({
          ...msg,
          timestamp: new Date(msg.timestamp),
        }));
        const restoredMode = resolveChatModeFromHistory(mapped);
        setChatMode(restoredMode);
        if (typeof window !== "undefined") {
          window.localStorage.setItem(
            chatModeStorageKey(selectedSessionId),
            restoredMode
          );
        }
        setMessages(mapped);
        setSessionId(selectedSessionId);
        const lastAssistant = [...mapped]
          .reverse()
          .find((m) => m.role === "assistant");
        setPendingMedicalValidation(
          Boolean(lastAssistant?.metadata?.needs_validation)
        );
        if (restoredMode === "medical") {
          setCrisisChoices([]);
          setInputQuickReplies([]);
        } else {
          const restoredChoices = normalizeCrisisChoices(
            lastAssistant?.metadata?.crisis_choices
          );
          if (
            lastAssistant?.metadata?.chat_blocked &&
            restoredChoices.length > 0
          ) {
            setCrisisChoices(restoredChoices);
            setInputQuickReplies([]);
          } else {
            setCrisisChoices([]);
            setInputQuickReplies(quickRepliesFromMessages(mapped));
          }
        }
        window.history.pushState({}, "", `/therapy/${selectedSessionId}`);
      }
    } catch (error) {
      console.error("Failed to load session:", error);
    } finally {
      setIsLoading(false);
    }
  };

  if (!mounted || isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-brand" />
      </div>
    );
  }

  const recentSessions = sessions.filter((s) => s.messages.length > 0);

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
                disabled={isLoading}
                className="text-gray-500 transition-colors hover:text-brand disabled:opacity-50"
                aria-label="New session"
              >
                {isLoading ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <PlusCircle className="h-5 w-5" />
                )}
              </button>
            </div>

            <button
              type="button"
              onClick={handleNewSession}
              disabled={isLoading}
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
                    <button
                      key={session.sessionId}
                      type="button"
                      onClick={() => handleSessionSelect(session.sessionId)}
                      className={cn(
                        "w-full rounded-full px-4 py-3 text-left text-sm transition-colors",
                        session.sessionId === sessionId
                          ? "bg-brand-light font-medium text-brand"
                          : "text-gray-700 hover:bg-brand-light/60"
                      )}
                    >
                      {getSessionTitle(session)}
                    </button>
                  ))}
                  {recentSessions.length === 0 && (
                    <p className="px-4 py-3 text-sm italic text-gray-400">
                      No more history...
                    </p>
                  )}
                </div>
              </div>
            </ScrollArea>
          </aside>

          {/* Main chat area */}
          <section className="relative flex min-h-0 flex-1 flex-col bg-white/40">
            {messages.length === 0 ? (
              <div className="relative flex flex-1 flex-col items-center justify-center overflow-hidden p-8 pb-36">
                <div className="bg-arc-decorator opacity-50" aria-hidden />
                <div className="relative z-10 mb-20 w-full max-w-xl space-y-10 text-center">
                  <div className="space-y-4">
                    <div className="mb-2 flex justify-center text-brand/40">
                      <Moon className="h-16 w-16 stroke-[1.25]" />
                    </div>
                    <h3 className="text-4xl font-bold text-gray-800">
                      {isMedicalMode ? "Medical Assistant" : "Luna AI"}
                    </h3>
                    <p className="text-lg text-gray-500">
                      {isMedicalMode
                        ? "Ask a medical question or upload an image for analysis."
                        : "Mình có thể giúp gì cho bạn hôm nay?"}
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
                  <LunaAvatar size="md" />
                  <div>
                    <h2 className="font-bold text-gray-800">
                      {isMedicalMode ? "Medical Assistant" : "Luna AI"}
                    </h2>
                    <p className="text-xs text-gray-500">
                      {messages.length} tin nhắn
                    </p>
                  </div>
                </div>

                <motion.div
                  ref={messagesScrollRef}
                  className="min-h-0 flex-1 overflow-y-auto scroll-smooth"
                >
                  <motion.div className="mx-auto max-w-3xl">
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
                            <div className="mt-1 h-8 w-8 shrink-0">
                              {msg.role === "assistant" ? (
                                <div
                                  className={cn(
                                    "flex h-8 w-8 items-center justify-center rounded-full ring-1",
                                    msg.metadata?.message_type === "crisis"
                                      ? "bg-red-100 text-red-600 ring-red-200"
                                      : "bg-brand/15 text-brand ring-brand/20"
                                  )}
                                >
                                  {msg.metadata?.message_type === "crisis" ? (
                                    <AlertTriangle className="h-4 w-4" />
                                  ) : (
                                    <LunaAvatar />
                                  )}
                                </div>
                              ) : (
                                <motion.div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand text-white">
                                  <User className="h-4 w-4" />
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
                                      ? "Medical AI"
                                      : "Luna AI"
                                    : "Bạn"}
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
                                      Có nguồn
                                    </Badge>
                                  )}
                              </div>

                              {msg.role === "user" ? (
                                <motion.div className="inline-block w-fit max-w-full rounded-2xl bg-brand px-4 py-3 text-left text-white">
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
                                typeof msg.metadata?.result_image === "string" && (
                                  <img
                                    src={msg.metadata.result_image}
                                    alt="Analysis result"
                                    className="mt-2 max-h-64 rounded-lg border border-gray-200 object-contain"
                                  />
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
                              {!isMedicalMode &&
                                msg.role === "assistant" &&
                                msg.metadata?.message_type !== "crisis" &&
                                (() => {
                                  const activityIds = getSuggestedActivities(msg.metadata);
                                  // Use metadata only — keyword scan duplicated CTAs already in prose.
                                  const canShowBreathing =
                                    activityIds.includes("breathing_box");
                                  const canShowOcean =
                                    activityIds.includes("ocean_sound");
                                  if (!canShowBreathing && !canShowOcean) return null;
                                  return (
                                    <div className="mt-3 flex flex-wrap gap-2">
                                      {canShowBreathing && (
                                        <Button
                                          size="sm"
                                          className="rounded-full bg-brand hover:bg-brand/90"
                                          onClick={() => void openBreathing()}
                                        >
                                          Mở bài tập hít thở
                                        </Button>
                                      )}
                                      {canShowOcean && (
                                        <Button
                                          size="sm"
                                          variant="secondary"
                                          className="rounded-full"
                                          onClick={() => void openOcean()}
                                        >
                                          Mở âm sóng thư giãn
                                        </Button>
                                      )}
                                    </div>
                                  );
                                })()}
                            </motion.div>
                          </motion.div>
                        </motion.div>
                      ))}
                    </AnimatePresence>

                    {isTyping && <LunaTypingIndicator />}
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
              {pendingMedicalValidation && isMedicalMode ? (
                <div className="mx-auto max-w-3xl space-y-2">
                  <p className="text-center text-sm text-gray-600">
                    Human validation required — confirm the analysis result:
                  </p>
                  <div className="flex flex-wrap justify-center gap-2">
                    <Button
                      type="button"
                      disabled={isTyping}
                      onClick={() => void handleMedicalValidation("yes")}
                    >
                      Yes, confirm
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={isTyping}
                      onClick={() => void handleMedicalValidation("no", "Needs review")}
                    >
                      No, needs review
                    </Button>
                  </div>
                </div>
              ) : !isMedicalMode && crisisChoices.length > 0 ? (
                <div className="mx-auto max-w-3xl">
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
                <div className="mx-auto max-w-3xl space-y-3">
                  {!isMedicalMode && inputQuickReplies.length > 0 && (
                    <QuickReplyChips
                      replies={inputQuickReplies}
                      onSelect={(text) => void sendUserMessage(text)}
                      disabled={isTyping}
                    />
                  )}
                  <form onSubmit={handleSubmit} className="flex items-end gap-2">
                    <ChatModeToggle
                      value={chatMode}
                      onChange={handleChatModeChange}
                      disabled={hasUserMessages || isTyping}
                    />
                    {isMedicalMode && (
                      <>
                        <input
                          ref={imageInputRef}
                          type="file"
                          accept="image/png,image/jpeg,image/jpg"
                          className="hidden"
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) void handleImageUpload(file);
                            e.target.value = "";
                          }}
                        />
                        <button
                          type="button"
                          disabled={isTyping || pendingMedicalValidation}
                          onClick={() => imageInputRef.current?.click()}
                          className="flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-full border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                          aria-label="Upload medical image"
                        >
                          <ImagePlus className="h-5 w-5" />
                        </button>
                      </>
                    )}
                    <div className="relative min-w-0 flex-1">
                      <textarea
                        value={message}
                        onChange={(e) => setMessage(e.target.value)}
                        placeholder={
                          isMedicalMode
                            ? "Ask a medical question..."
                            : "Chia sẻ điều bạn đang nghĩ..."
                        }
                        rows={1}
                        disabled={isTyping || pendingMedicalValidation}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            handleSubmit(e);
                          }
                        }}
                        className={cn(
                          "w-full resize-none rounded-full border-2 border-brand-border/80 bg-brand-light py-4 pl-6 pr-14 text-gray-700 outline-none transition-all placeholder:text-gray-400 focus:border-brand focus:ring-0",
                          "min-h-[52px] max-h-[120px]",
                          isTyping && "cursor-not-allowed opacity-50"
                        )}
                      />
                      <button
                        type="submit"
                        disabled={
                          isTyping || !message.trim() || pendingMedicalValidation
                        }
                        className={cn(
                          "absolute right-2 top-1/2 -translate-y-1/2 rounded-full p-3 text-white transition-all disabled:cursor-not-allowed disabled:opacity-50",
                          isMedicalMode
                            ? "bg-slate-700 hover:bg-slate-800"
                            : "bg-brand/80 hover:bg-brand"
                        )}
                        aria-label="Send message"
                      >
                        <Send className="h-5 w-5" />
                      </button>
                    </div>
                  </form>
                </div>
              )}

              <p className="mx-auto mt-4 max-w-3xl text-center text-[10px] italic text-gray-400">
                {isMedicalMode
                  ? "Medical mode provides educational information only — not medical diagnosis. Always consult a licensed healthcare professional."
                  : "Luna AI hỗ trợ tinh thần, không thay thế chẩn đoán y tế. Nếu bạn đang trong khủng hoảng, hãy liên hệ chuyên gia ngay."}
              </p>
            </div>
          </section>
        </div>
      </div>

      <Dialog
        open={showBreathingPopup}
        onOpenChange={(open) => {
          setShowBreathingPopup(open);
          if (!open) void handleWellnessComplete();
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Bài tập hít thở</DialogTitle>
            <DialogDescription>
              Dành vài phút hít vào - giữ - thở ra để ổn định nhịp thở và giảm căng thẳng.
            </DialogDescription>
          </DialogHeader>
          <BreathingGame onComplete={() => void handleWellnessComplete()} />
        </DialogContent>
      </Dialog>

      <Dialog
        open={showOceanPopup}
        onOpenChange={(open) => {
          setShowOceanPopup(open);
          if (!open) void handleWellnessComplete();
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Âm sóng thư giãn</DialogTitle>
            <DialogDescription>
              Mở âm nền sóng biển và điều chỉnh âm lượng theo nhu cầu của bạn.
            </DialogDescription>
          </DialogHeader>
          <OceanWaves />
        </DialogContent>
      </Dialog>
    </>
  );
}
