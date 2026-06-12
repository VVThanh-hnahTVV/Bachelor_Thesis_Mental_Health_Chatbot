"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { SupportMode } from "@/lib/api/handoff";
import { buildChatWsUrl } from "@/lib/api/handoff";

export interface WsChatMessage {
  id?: string;
  role: string;
  content: string;
  sender_name?: string;
  created_at?: string;
  metadata?: Record<string, unknown>;
}

export interface UseChatWsOptions {
  sessionId: string | null;
  role?: "user" | "support";
  token?: string | null;
  enabled?: boolean;
  onMessage?: (msg: WsChatMessage) => void;
  onSupportJoined?: (supportName: string) => void;
  onSupportLeft?: () => void;
  onHandoffPending?: () => void;
  onSupportModeChange?: (mode: SupportMode) => void;
}

export function useChatWs({
  sessionId,
  role = "user",
  token = null,
  enabled = true,
  onMessage,
  onSupportJoined,
  onSupportLeft,
  onHandoffPending,
  onSupportModeChange,
}: UseChatWsOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [connected, setConnected] = useState(false);

  const callbacksRef = useRef({
    onMessage,
    onSupportJoined,
    onSupportLeft,
    onHandoffPending,
    onSupportModeChange,
  });
  callbacksRef.current = {
    onMessage,
    onSupportJoined,
    onSupportLeft,
    onHandoffPending,
    onSupportModeChange,
  };

  const sendMessage = useCallback((content: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify({ type: "message", content }));
    return true;
  }, []);

  useEffect(() => {
    if (!sessionId || !enabled) return;

    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      const url = buildChatWsUrl(sessionId, role, token);
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!cancelled) setConnected(true);
      };

      ws.onclose = () => {
        setConnected(false);
        if (!cancelled) {
          reconnectTimer.current = setTimeout(connect, 2500);
        }
      };

      ws.onerror = () => {
        ws.close();
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data as string) as Record<string, unknown>;
          const type = String(data.type || "");
          if (type === "message") {
            callbacksRef.current.onMessage?.({
              id: data.id as string | undefined,
              role: String(data.role || ""),
              content: String(data.content || ""),
              sender_name: data.sender_name as string | undefined,
              created_at: data.created_at as string | undefined,
              metadata: data.metadata as Record<string, unknown> | undefined,
            });
          } else if (type === "support_joined") {
            const name = String(data.support_name || "Support");
            callbacksRef.current.onSupportJoined?.(name);
            callbacksRef.current.onSupportModeChange?.("human");
          } else if (type === "support_left") {
            callbacksRef.current.onSupportLeft?.();
            callbacksRef.current.onSupportModeChange?.("ai");
          } else if (type === "handoff_pending") {
            callbacksRef.current.onHandoffPending?.();
            callbacksRef.current.onSupportModeChange?.("awaiting_support");
          }
        } catch {
          /* ignore */
        }
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
      wsRef.current = null;
      setConnected(false);
    };
  }, [sessionId, role, token, enabled]);

  return { connected, sendMessage };
}
