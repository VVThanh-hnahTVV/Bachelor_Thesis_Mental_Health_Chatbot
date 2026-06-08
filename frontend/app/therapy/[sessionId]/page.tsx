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
  ImagePlus,
  Trash2,
  X,
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
  uploadMedicalImage,
  validateMedicalOutput,
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
import { startWellnessSession, completeWellnessSession } from "@/lib/api/wellness";
import type { QuickReply, CrisisChoice } from "@/lib/api/chat";
import {
  CRISIS_CHIP_PREFIX,
  formatMessageForDisplay,
  normalizeCrisisChoices,
} from "@/lib/api/chat";
import { fetchCurrentUser, linkChatSession } from "@/lib/api/auth";
import { getDefaultLunaGreeting, getDefaultMedicalGreeting } from "@/lib/luna-greeting";
import { registerChatSessionId, unregisterChatSessionId } from "@/lib/session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const MEDICAL_SUGGESTED_QUESTIONS = [
  { text: "What are common symptoms of brain tumors?" },
  { text: "Explain chest X-ray findings for COVID-19" },
  { text: "How is skin lesion analysis performed?" },
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
  const [speechError, setSpeechError] = useState<string | null>(null);
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null);
  const [isDeletingSession, setIsDeletingSession] = useState(false);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const [pendingImageFile, setPendingImageFile] = useState<File | null>(null);
  const [pendingImagePreview, setPendingImagePreview] = useState<string | null>(
    null
  );

  const clearPendingImage = () => {
    if (pendingImagePreview) {
      URL.revokeObjectURL(pendingImagePreview);
    }
    setPendingImageFile(null);
    setPendingImagePreview(null);
  };

  const attachImageFile = (file: File) => {
    clearPendingImage();
    setPendingImageFile(file);
    setPendingImagePreview(URL.createObjectURL(file));
  };

  useEffect(() => {
    return () => {
      if (pendingImagePreview) {
        URL.revokeObjectURL(pendingImagePreview);
      }
    };
  }, [pendingImagePreview]);

  const hasUserMessages = messages.some((m) => m.role === "user");
  const isMedicalMode = chatMode === "medical";

  const handleSpeechTranscript = (text: string) => {
    setSpeechError(null);
    setMessage((prev) => (prev.trim() ? `${prev.trim()} ${text}` : text));
  };

  const voiceInput = useSpeechToText({
    onTranscript: handleSpeechTranscript,
    onError: setSpeechError,
    disabled: isTyping || pendingMedicalValidation,
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
    setPendingMedicalValidation(Boolean(last?.metadata?.needs_validation));
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
      setPendingMedicalValidation(false);
    } catch {
      setMessages(await welcomeMessages("psychologist"));
      setChatMode("psychologist");
      setInputQuickReplies([]);
      setCrisisChoices([]);
      setPendingMedicalValidation(false);
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
      setPendingMedicalValidation(false);
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
            ...(imageUrl ? { result_image: imageUrl } : {}),
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

    if (isMedicalMode && pendingImageFile) {
      const file = pendingImageFile;
      const text = message.trim();
      setMessage("");
      clearPendingImage();
      await handleImageUpload(file, text);
      return;
    }

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
    clearPendingImage();
    void (async () => {
      setMessages(await welcomeMessages(mode));
      setCrisisChoices([]);
      setInputQuickReplies([]);
      setPendingMedicalValidation(false);
    })();
  };

  const handleImageUpload = async (file: File, text: string = "") => {
    if (!sessionId || isTyping || chatMode !== "medical") return;
    setIsTyping(true);
    setTypingStatus("Analyzing image");
    const previewUrl = URL.createObjectURL(file);
    const userText = text.trim() || "[Medical image upload]";
    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: userText,
        timestamp: new Date(),
        metadata: { chat_mode: "medical", has_image: true, image_url: previewUrl },
      },
    ]);
    try {
      const response = await uploadMedicalImage(sessionId, file, text.trim());
      const resultImage = response.metadata?.result_image as string | undefined;
      const imageUrl = resultImage
        ? resultImage.startsWith("http")
          ? resultImage
          : `${API_BASE}${resultImage}`
        : undefined;
      const uploadedImageUrl = response.metadata?.image_url as string | undefined;
      setPendingMedicalValidation(
        Boolean(response.metadata?.needs_validation)
      );
      setMessages((prev) => {
        const next = [...prev];
        const lastUserIdx = next.findLastIndex((msg) => msg.role === "user");
        if (lastUserIdx >= 0 && uploadedImageUrl) {
          next[lastUserIdx] = {
            ...next[lastUserIdx],
            metadata: {
              ...(next[lastUserIdx].metadata || {}),
              image_url: uploadedImageUrl,
            },
          };
        }
        next.push({
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
        });
        return next;
      });
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
      URL.revokeObjectURL(previewUrl);
      setIsTyping(false);
      setTypingStatus(null);
    }
  };

  const handleMedicalValidation = async (result: "yes" | "no", comments?: string) => {
    if (!sessionId || isTyping) return;
    setIsTyping(true);
    setTypingStatus("Processing validation");
    setPendingMedicalValidation(false);
    try {
      const response = await validateMedicalOutput(sessionId, result, comments);
      setMessages((prev) => [
        ...prev,
        {
          role: "user",
          content:
            result === "yes"
              ? "Đã xác nhận kết quả sàng lọc."
              : `Chưa chắc — ${comments || "cần xem lại"}`.trim(),
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
      setTypingStatus(null);
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
                                          Open breathing exercise
                                        </Button>
                                      )}
                                      {canShowOcean && (
                                        <Button
                                          size="sm"
                                          variant="secondary"
                                          className="rounded-full"
                                          onClick={() => void openOcean()}
                                        >
                                          Open calming ocean sounds
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
              {pendingMedicalValidation && isMedicalMode ? (
                <div className="w-full space-y-2">
                  <p className="text-center text-sm text-gray-600">
                    Xác nhận kết quả sàng lọc (bạn hoặc người có chuyên môn):
                  </p>
                  <div className="flex flex-wrap justify-center gap-2">
                    <Button
                      type="button"
                      disabled={isTyping}
                      onClick={() => void handleMedicalValidation("yes")}
                    >
                      Đồng ý / Xác nhận
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={isTyping}
                      onClick={() => void handleMedicalValidation("no", "Cần bác sĩ xem lại")}
                    >
                      Chưa chắc — cần xem lại
                    </Button>
                  </div>
                </div>
              ) : !isMedicalMode && crisisChoices.length > 0 ? (
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
                    <input
                      ref={imageInputRef}
                      type="file"
                      accept="image/png,image/jpeg,image/jpg"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) attachImageFile(file);
                        e.target.value = "";
                      }}
                    />
                    <div
                      className={cn(
                        "flex flex-col rounded-2xl border-2 bg-brand-light transition-all focus-within:border-brand",
                        voiceInput.isRecording
                          ? "border-red-300 ring-2 ring-red-100"
                          : "border-brand-border/80",
                        (isTyping || pendingMedicalValidation) && "opacity-50"
                      )}
                    >
                      {voiceInput.isRecording && (
                        <VoiceRecordingVisualizer level={voiceInput.audioLevel} />
                      )}
                      {isMedicalMode && pendingImagePreview && (
                        <div className="flex items-center gap-2 border-b border-brand-border/50 px-3 py-2">
                          <img
                            src={pendingImagePreview}
                            alt="Ảnh đính kèm"
                            className="h-12 w-12 rounded-lg border border-brand-border/60 object-cover"
                          />
                          <div className="min-w-0 flex-1 text-xs text-gray-600">
                            <p className="truncate font-medium">
                              {pendingImageFile?.name || "Medical image"}
                            </p>
                            <p>Thêm ghi chú (không bắt buộc), rồi bấm gửi.</p>
                          </div>
                          <button
                            type="button"
                            onClick={clearPendingImage}
                            disabled={isTyping || pendingMedicalValidation}
                            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100 disabled:opacity-50"
                            aria-label="Remove attached image"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      )}
                      <textarea
                        value={message}
                        onChange={(e) => setMessage(e.target.value)}
                        placeholder={
                          voiceInput.isRecording
                            ? "Listening to your voice..."
                            : isMedicalMode && pendingImagePreview
                              ? "Thêm ghi chú cho ảnh (không bắt buộc)..."
                              : isMedicalMode
                                ? "Hỏi Helios hoặc đính kèm ảnh y khoa..."
                                : "Share what's on your mind..."
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
                          {isMedicalMode && (
                            <button
                              type="button"
                              disabled={isTyping || pendingMedicalValidation}
                              onClick={() => imageInputRef.current?.click()}
                              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-brand-border/60 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                              aria-label="Upload medical image"
                            >
                              <ImagePlus className="h-4 w-4" />
                            </button>
                          )}
                          <VoiceMicButton
                            toggle={voiceInput.toggle}
                            isRecording={voiceInput.isRecording}
                            isTranscribing={voiceInput.isTranscribing}
                            disabled={isTyping || pendingMedicalValidation}
                          />
                        </div>
                        <button
                          type="submit"
                          disabled={
                            isTyping ||
                            pendingMedicalValidation ||
                            (!message.trim() && !pendingImageFile)
                          }
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

      <Dialog
        open={showBreathingPopup}
        onOpenChange={(open) => {
          setShowBreathingPopup(open);
          if (!open) void handleWellnessComplete();
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Breathing exercise</DialogTitle>
            <DialogDescription>
              Take a few minutes to breathe in, hold, and breathe out to steady your rhythm and ease tension.
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
            <DialogTitle>Calming ocean sounds</DialogTitle>
            <DialogDescription>
              Play ocean wave ambience and adjust the volume to your preference.
            </DialogDescription>
          </DialogHeader>
          <OceanWaves />
        </DialogContent>
      </Dialog>
    </>
  );
}
