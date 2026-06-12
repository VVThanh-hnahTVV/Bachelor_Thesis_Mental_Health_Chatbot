"use client";

import { getAuthToken } from "@/lib/auth-token";
import { useChatWs, type UseChatWsOptions } from "@/lib/hooks/use-chat-ws";

export function useSupportChatWs(
  options: Omit<UseChatWsOptions, "role" | "token">
) {
  return useChatWs({
    ...options,
    role: "support",
    token: getAuthToken(),
  });
}
