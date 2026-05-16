"use client";

import { RefObject } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import {
  Send,
  Bot,
  User,
  Loader2,
  Moon,
  Plus,
  MessageSquare,
  Phone,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { ChatMessage, ChatSession } from "@/lib/api/chat";

const SUGGESTED_QUESTIONS = [
  "Làm thế nào để quản lý lo lắng tốt hơn?",
  "Gần đây tôi cảm thấy rất áp lực",
  "Tôi muốn nói về giấc ngủ của mình",
  "Tôi cần giúp đỡ về cân bằng cuộc sống",
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

function getSessionTitle(session: ChatSession): string {
  const first =
    session.messages.find((m) => m.role === "user")?.content ||
    session.messages[0]?.content;
  if (!first) return "Cuộc trò chuyện mới";
  const trimmed = first.trim();
  if (trimmed.length <= 36) return trimmed;
  return `${trimmed.slice(0, 36)}…`;
}

export interface TherapyChatViewProps {
  sessions: ChatSession[];
  sessionId: string | null;
  messages: ChatMessage[];
  message: string;
  isLoading: boolean;
  isTyping: boolean;
  isChatPaused: boolean;
  crisisChoices: string[];
  messagesEndRef: RefObject<HTMLDivElement | null>;
  onMessageChange: (value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  onNewSession: () => void;
  onSelectSession: (id: string) => void;
  onSuggestedQuestion: (text: string) => void;
  onCrisisChoice: (text: string) => void;
  onBreathingExercise?: () => void;
  onOceanSounds?: () => void;
  getSuggestedActivities: (metadata: ChatMessage["metadata"]) => string[];
  hasBreathingSuggestion: (text: string) => boolean;
  hasOceanSuggestion: (text: string) => boolean;
}

export function TherapyChatView(props: TherapyChatViewProps) {
  const {
    sessions,
    sessionId,
    messages,
    message,
    isLoading,
    isTyping,
    isChatPaused,
    crisisChoices,
    messagesEndRef,
    onMessageChange,
    onSubmit,
    onNewSession,
    onSelectSession,
    onSuggestedQuestion,
    onCrisisChoice,
    onBreathingExercise,
    onOceanSounds,
    getSuggestedActivities,
    hasBreathingSuggestion,
    hasOceanSuggestion,
  } = props;

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Sidebar */}
      <aside className="flex w-72 shrink-0 flex-col border-r border-gray-200/80 bg-[#F3F5F2]">
        <div className="p-5 pb-4">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-lg font-bold text-gray-800">Chat Sessions</h2>
            <button
              type="button"
              onClick={onNewSession}
              disabled={isLoading}
              className="flex h-8 w-8 items-center justify-center rounded-full border border-serene-green/30 bg-white text-serene-accent transition-colors hover:bg-[#E8F0E7] disabled:opacity-50"
              aria-label="New session"
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
            </button>
          </div>
          <button
            type="button"
            onClick={onNewSession}
            disabled={isLoading}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-serene-green/25 bg-white/80 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:border-serene-green/40 hover:bg-white disabled:opacity-50"
          >
            <MessageSquare className="h-4 w-4 text-serene-accent" />
            New Session
          </button>
        </div>

        <ScrollArea className="flex-1 px-5">
          <p className="mb-3 text-[10px] font-medium uppercase tracking-widest text-gray-400">
            Recent
          </p>
          <div className="space-y-1 pb-4">
            {sessions.map((session) => (
              <button
                key={session.sessionId}
                type="button"
                onClick={() => onSelectSession(session.sessionId)}
                className={cn(
                  "w-full rounded-lg px-3 py-2.5 text-left text-sm transition-colors",
                  session.sessionId === sessionId
                    ? "bg-white font-medium text-gray-800 shadow-sm"
                    : "text-gray-600 hover:bg-white/60"
                )}
              >
                {getSessionTitle(session)}
              </button>
            ))}
            {sessions.length === 0 && (
              <p className="py-2 text-sm text-gray-500">No sessions yet</p>
            )}
          </div>
        </ScrollArea>
      </aside>

      {/* Main area */}
      <div className="flex flex-1 flex-col overflow-hidden bg-white">
        {messages.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center px-6 pb-8">
            <div className="relative flex w-full max-w-lg flex-col items-center justify-center">
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                <div className="h-[min(420px,70vw)] w-[min(420px,70vw)] rounded-full border border-serene-green/10" />
              </div>
              <div className="relative z-10 flex flex-col items-center px-4 text-center">
                <Moon className="mb-6 h-10 w-10 stroke-[1.25] text-serene-accent" />
                <h1 className="mb-3 text-3xl font-bold text-gray-800 md:text-4xl">Luna AI</h1>
                <p className="mb-10 text-lg text-gray-500">Mình có thể giúp gì cho bạn hôm nay?</p>
                <div className="w-full max-w-md space-y-3">
                  {SUGGESTED_QUESTIONS.map((text, index) => (
                    <motion.button
                      key={text}
                      type="button"
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: index * 0.08 }}
                      onClick={() => onSuggestedQuestion(text)}
                      disabled={isTyping}
                      className="w-full rounded-xl border border-gray-200 bg-white px-5 py-4 text-left text-sm text-gray-700 transition-colors hover:border-serene-green/30 hover:bg-[#F9FAF7] disabled:opacity-50"
                    >
                      {text}
                    </motion.button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
              <AnimatePresence initial={false}>
                {messages.map((msg, i) => (
                  <motion.div
                    key={`${msg.timestamp.toISOString()}-${i}`}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={cn(
                      "flex gap-3",
                      msg.role === "user" ? "flex-row-reverse" : "flex-row"
                    )}
                  >
                    <div
                      className={cn(
                        "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
                        msg.role === "assistant"
                          ? msg.metadata?.message_type === "crisis"
                            ? "bg-red-100 text-red-600"
                            : "bg-[#E8F0E7] text-serene-accent"
                          : "bg-gray-100 text-gray-600"
                      )}
                    >
                      {msg.role === "assistant" ? (
                        msg.metadata?.message_type === "crisis" ? (
                          <AlertTriangle className="h-4 w-4" />
                        ) : (
                          <Bot className="h-4 w-4" />
                        )
                      ) : (
                        <User className="h-4 w-4" />
                      )}
                    </div>

                    <div
                      className={cn(
                        "max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
                        msg.role === "assistant"
                          ? msg.metadata?.message_type === "crisis"
                            ? "bg-red-50 text-gray-700"
                            : "bg-[#F9FAF7] text-gray-700"
                          : "bg-serene-green text-white"
                      )}
                    >
                      {/* Emotion badge (therapy strategy hidden from users) */}
                      {msg.role === "assistant" && (
                        <div className="mb-2 flex flex-wrap gap-1">
                          {msg.metadata?.emotion && msg.metadata.emotion !== "neutral" && (
                            <Badge
                              variant="secondary"
                              className="rounded-full px-2 py-0 text-[10px]"
                            >
                              {EMOTION_LABELS[msg.metadata.emotion as string] ?? msg.metadata.emotion}
                            </Badge>
                          )}
                        </div>
                      )}

                      <div className="prose prose-sm max-w-none prose-p:my-1">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>

                      {/* Wellness activity buttons */}
                      {msg.role === "assistant" && msg.metadata?.message_type !== "crisis" &&
                        (() => {
                          const activityIds = getSuggestedActivities(msg.metadata);
                          const showBreathing =
                            activityIds.includes("breathing_box") ||
                            hasBreathingSuggestion(msg.content);
                          const showOcean =
                            activityIds.includes("ocean_sound") ||
                            hasOceanSuggestion(msg.content);
                          if (!showBreathing && !showOcean) return null;
                          return (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {showBreathing && onBreathingExercise && (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="rounded-full border-serene-green/30 text-serene-accent"
                                  onClick={onBreathingExercise}
                                >
                                  Bài tập hít thở
                                </Button>
                              )}
                              {showOcean && onOceanSounds && (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="rounded-full"
                                  onClick={onOceanSounds}
                                >
                                  Âm sóng thư giãn
                                </Button>
                              )}
                            </div>
                          );
                        })()}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>

              {isTyping && (
                <div className="flex gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#E8F0E7]">
                    <Loader2 className="h-4 w-4 animate-spin text-serene-accent" />
                  </div>
                  <div className="rounded-2xl bg-[#F9FAF7] px-4 py-3 text-sm text-gray-500">
                    Luna đang soạn…
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>
        )}

        {/* Input area */}
        <div className="border-t border-gray-100 bg-white px-6 py-4">
          {/* Crisis hotline banner */}
          <AnimatePresence>
            {isChatPaused && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="mx-auto mb-4 max-w-3xl rounded-xl border border-red-200 bg-red-50 px-4 py-3"
              >
                <div className="flex items-start gap-3">
                  <Phone className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
                  <div>
                    <p className="text-sm font-semibold text-red-700">
                      Đường dây hỗ trợ khẩn cấp
                    </p>
                    <p className="mt-0.5 text-sm text-red-600">
                      <span className="font-bold">1800 599 920</span> — Sức khỏe tâm thần (miễn phí, 24/7)
                      &nbsp;·&nbsp;
                      <span className="font-bold">115</span> — Cấp cứu
                    </p>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Crisis choice buttons OR textarea */}
          {isChatPaused && crisisChoices.length > 0 ? (
            <div className="mx-auto max-w-3xl">
              <p className="mb-3 text-center text-xs text-gray-400">
                Chọn một bước nhỏ để mình cùng đồng hành với bạn:
              </p>
              <div className="grid grid-cols-2 gap-2">
                {crisisChoices.map((choice) => (
                  <motion.button
                    key={choice}
                    type="button"
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    disabled={isTyping}
                    onClick={() => onCrisisChoice(choice)}
                    className="rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-700 transition-colors hover:border-serene-green/30 hover:bg-[#F9FAF7] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {choice}
                  </motion.button>
                ))}
              </div>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="mx-auto flex max-w-3xl items-end gap-3">
              <textarea
                value={message}
                onChange={(e) => onMessageChange(e.target.value)}
                placeholder="Chia sẻ điều bạn đang nghĩ..."
                className={cn(
                  "max-h-[160px] min-h-[52px] flex-1 resize-none rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-800",
                  "placeholder:text-gray-400 focus:border-serene-green/40 focus:outline-none focus:ring-2 focus:ring-serene-green/30",
                  (isTyping || isChatPaused) && "cursor-not-allowed opacity-50"
                )}
                rows={1}
                disabled={isTyping || isChatPaused}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    onSubmit(e);
                  }
                }}
              />
              <Button
                type="submit"
                size="icon"
                className="h-[52px] w-[52px] shrink-0 rounded-2xl bg-serene-green text-white shadow-sm hover:bg-serene-accent disabled:opacity-50"
                disabled={isTyping || isChatPaused || !message.trim()}
              >
                <Send className="h-5 w-5" />
              </Button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
