"use client";

import { RefObject } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AssistantMessageBubble,
  ChatMessageMarkdown,
} from "@/components/therapy/chat-message-markdown";
import {
  Send,
  Bot,
  User,
  Loader2,
  Moon,
  Plus,
  MessageSquare,
  AlertTriangle,
  BookOpenCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { ChatMessage, ChatSession, CrisisChoice } from "@/lib/api/chat";

const SUGGESTED_QUESTIONS = [
  "How can I manage anxiety better?",
  "I've been feeling a lot of pressure lately",
  "I want to talk about my sleep",
  "I need help with work-life balance",
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

function getRetrievalSummary(metadata: ChatMessage["metadata"]) {
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
}

export interface TherapyChatViewProps {
  sessions: ChatSession[];
  sessionId: string | null;
  messages: ChatMessage[];
  message: string;
  isLoading: boolean;
  isTyping: boolean;
  crisisChoices: CrisisChoice[];
  messagesEndRef: RefObject<HTMLDivElement | null>;
  onMessageChange: (value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  onNewSession: () => void;
  onSelectSession: (id: string) => void;
  onSuggestedQuestion: (text: string) => void;
  onCrisisChoice: (choice: CrisisChoice) => void;
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
                <h1 className="mb-3 text-3xl font-bold text-gray-800 md:text-4xl">Luna</h1>
                <p className="mb-10 text-lg text-gray-500">How can I help you today?</p>
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

                    <div className="max-w-[85%]">
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
                          {msg.metadata?.message_type !== "crisis" &&
                            getRetrievalSummary(msg.metadata) && (
                              <Badge
                                variant="outline"
                                className="gap-1 rounded-full px-2 py-0 text-[10px]"
                                title={getRetrievalSummary(msg.metadata) ?? undefined}
                              >
                                <BookOpenCheck className="h-3 w-3" />
                                Sourced
                              </Badge>
                            )}
                        </div>
                      )}

                      {msg.role === "user" ? (
                        <div className="rounded-2xl bg-serene-green px-4 py-3 text-white">
                          <ChatMessageMarkdown
                            content={msg.content}
                            className="text-white [&_a]:text-white [&_p]:text-white [&_strong]:text-white"
                          />
                        </div>
                      ) : (
                        <AssistantMessageBubble
                          variant={
                            msg.metadata?.message_type === "crisis" ? "crisis" : "default"
                          }
                        >
                          <ChatMessageMarkdown content={msg.content} />
                        </AssistantMessageBubble>
                      )}

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
                                  Breathing exercise
                                </Button>
                              )}
                              {showOcean && onOceanSounds && (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="rounded-full"
                                  onClick={onOceanSounds}
                                >
                                  Calming ocean sounds
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
                    Luna is typing…
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>
        )}

        {/* Input area */}
        <div className="border-t border-gray-100 bg-white px-6 py-4">
          {crisisChoices.length > 0 ? (
            <div className="mx-auto max-w-3xl">
              <div className="grid grid-cols-2 gap-2">
                {crisisChoices.map((choice) => (
                  <button
                    key={choice.id}
                    type="button"
                    disabled={isTyping}
                    onClick={() => onCrisisChoice(choice)}
                    className="rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-700 transition-colors hover:border-serene-green/30 hover:bg-[#F9FAF7] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {choice.label}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="mx-auto flex max-w-3xl items-end gap-3">
              <textarea
                value={message}
                onChange={(e) => onMessageChange(e.target.value)}
                placeholder="Share what's on your mind..."
                className={cn(
                  "max-h-[160px] min-h-[52px] flex-1 resize-none rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-800",
                  "placeholder:text-gray-400 focus:border-serene-green/40 focus:outline-none focus:ring-2 focus:ring-serene-green/30",
                  isTyping && "cursor-not-allowed opacity-50"
                )}
                rows={1}
                disabled={isTyping}
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
                disabled={isTyping || !message.trim()}
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
