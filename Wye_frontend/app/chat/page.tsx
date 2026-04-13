"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { io, type Socket } from "socket.io-client";
import {
  App as AntApp,
  Avatar,
  Button,
  Card,
  Col,
  Empty,
  Input,
  Layout,
  List,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import {
  BulbOutlined,
  MessageOutlined,
  PlusCircleOutlined,
  RobotOutlined,
  SendOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Header } from "../../components/Header/Header";
import { Footer } from "../../components/Footer/Footer";
import { chatApi } from "../../api";
import styles from "./page.module.css";

type ChatMessageView = {
  _id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  pending?: boolean;
};

type SocketMessage = {
  id: string;
  sessionId: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
};

const quickReplies = ["I'm feeling anxious", "Can we talk?", "Daily Check-in", "Help me sleep"];

const formatTime = (dateString: string) =>
  new Date(dateString).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

const getAccessToken = () => {
  if (typeof document === "undefined") return "";
  const match = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith("accessToken="));
  if (!match) return "";
  return decodeURIComponent(match.slice("accessToken=".length));
};

const upsertMessage = (items: ChatMessageView[], incoming: ChatMessageView) => {
  const existedIndex = items.findIndex((item) => item._id === incoming._id);
  if (existedIndex >= 0) {
    const clone = [...items];
    clone[existedIndex] = incoming;
    return clone;
  }
  return [...items, incoming];
};

export default function ChatPage() {
  const { message } = AntApp.useApp();
  const [sessions, setSessions] = useState<chatApi.ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [messagesBySession, setMessagesBySession] = useState<Record<string, ChatMessageView[]>>({});
  const [inputValue, setInputValue] = useState("");
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [connected, setConnected] = useState(false);
  const [creatingSession, setCreatingSession] = useState(false);
  const socketRef = useRef<Socket | null>(null);
  const messageEndRef = useRef<HTMLDivElement | null>(null);

  const activeMessages = useMemo(
    () => (activeSessionId ? messagesBySession[activeSessionId] ?? [] : []),
    [activeSessionId, messagesBySession]
  );

  const fetchSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const sessionData = await chatApi.getChatSessions();
      if (sessionData.length === 0) {
        const firstSession = await chatApi.createChatSession({ title: "New conversation" });
        setSessions([firstSession]);
        setActiveSessionId(firstSession._id);
      } else {
        setSessions(sessionData);
        setActiveSessionId((current) => current || sessionData[0]._id);
      }
    } catch {
      message.error("Không thể tải danh sách cuộc trò chuyện.");
    } finally {
      setLoadingSessions(false);
    }
  }, [message]);

  const fetchMessages = useCallback(
    async (sessionId: string) => {
      setLoadingMessages(true);
      try {
        const data = await chatApi.getChatMessages(sessionId);
        setMessagesBySession((prev) => ({
          ...prev,
          [sessionId]: data.map((item) => ({ ...item })),
        }));
      } catch {
        message.error("Không thể tải lịch sử tin nhắn.");
      } finally {
        setLoadingMessages(false);
      }
    },
    [message]
  );

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  useEffect(() => {
    if (!activeSessionId) return;
    if (messagesBySession[activeSessionId]) return;
    fetchMessages(activeSessionId);
  }, [activeSessionId, fetchMessages, messagesBySession]);

  useEffect(() => {
    if (!activeSessionId) return;
    const socketUrl = process.env.NEXT_PUBLIC_SOCKET_URL || process.env.NEXT_PUBLIC_API_URL || "";
    if (!socketUrl) return;

    const token = getAccessToken();
    const socket = io(socketUrl, {
      transports: ["websocket", "polling"],
      auth: token ? { accessToken: token } : undefined,
    });
    socketRef.current = socket;

    const onConnect = () => setConnected(true);
    const onDisconnect = () => setConnected(false);
    const onSocketError = (payload: { message?: string }) =>
      message.error(payload.message || "Socket gặp sự cố.");
    const onSocketMessage = (payload: SocketMessage) => {
      const normalized: ChatMessageView = {
        _id: payload.id,
        conversation_id: payload.sessionId,
        role: payload.role,
        content: payload.content,
        created_at: payload.createdAt,
      };
      setMessagesBySession((prev) => ({
        ...prev,
        [payload.sessionId]: upsertMessage(prev[payload.sessionId] ?? [], normalized),
      }));
    };

    socket.on("connect", onConnect);
    socket.on("disconnect", onDisconnect);
    socket.on("message:error", onSocketError);
    socket.on("message:sent", onSocketMessage);
    socket.on("message:receive", onSocketMessage);

    return () => {
      socket.off("connect", onConnect);
      socket.off("disconnect", onDisconnect);
      socket.off("message:error", onSocketError);
      socket.off("message:sent", onSocketMessage);
      socket.off("message:receive", onSocketMessage);
      socket.disconnect();
      socketRef.current = null;
    };
  }, [activeSessionId, message]);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeMessages, loadingMessages]);

  const handleCreateSession = async () => {
    setCreatingSession(true);
    try {
      const newSession = await chatApi.createChatSession({ title: "New conversation" });
      setSessions((prev) => [newSession, ...prev]);
      setMessagesBySession((prev) => ({ ...prev, [newSession._id]: [] }));
      setActiveSessionId(newSession._id);
      setInputValue("");
    } catch {
      message.error("Không thể tạo cuộc trò chuyện mới.");
    } finally {
      setCreatingSession(false);
    }
  };

  const handleSendMessage = async () => {
    const content = inputValue.trim();
    if (!content || sending) return;
    if (!activeSessionId) {
      message.warning("Bạn cần đăng nhập hoặc tạo session trước khi gửi tin nhắn.");
      return;
    }

    setSending(true);
    setInputValue("");
    const temporaryId = `temp-${Date.now()}`;
    const optimisticMessage: ChatMessageView = {
      _id: temporaryId,
      conversation_id: activeSessionId,
      role: "user",
      content,
      created_at: new Date().toISOString(),
      pending: true,
    };

    setMessagesBySession((prev) => ({
      ...prev,
      [activeSessionId]: [...(prev[activeSessionId] ?? []), optimisticMessage],
    }));

    try {
      const savedMessage = await chatApi.createChatMessage(activeSessionId, { content, role: "user" });
      setMessagesBySession((prev) => {
        const current = prev[activeSessionId] ?? [];
        const withoutTemp = current.filter((item) => item._id !== temporaryId);
        return {
          ...prev,
          [activeSessionId]: [...withoutTemp, { ...savedMessage }],
        };
      });

      setSessions((prev) =>
        prev.map((item) =>
          item._id === activeSessionId
            ? {
                ...item,
                updated_at: new Date().toISOString(),
                last_message_preview: content.slice(0, 120),
              }
            : item
        )
      );

      if (socketRef.current?.connected) {
        socketRef.current.emit("message:send", { sessionId: activeSessionId, content });
      } else {
        message.warning("Đã lưu tin nhắn, nhưng socket chưa kết nối để nhận phản hồi realtime.");
      }
    } catch {
      setMessagesBySession((prev) => ({
        ...prev,
        [activeSessionId]: (prev[activeSessionId] ?? []).filter((item) => item._id !== temporaryId),
      }));
      message.error("Gửi tin nhắn thất bại.");
      setInputValue(content);
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <Header />
      <main className={styles.pageWrap}>
        <Layout className={styles.chatLayout}>
          <Layout.Sider
            className={styles.sider}
            width={300}
            breakpoint="lg"
            collapsedWidth={0}
            theme="light"
          >
            <div className={styles.profileBlock}>
              <Avatar size={52} icon={<UserOutlined />} />
              <div>
                <Typography.Title level={5} className={styles.profileTitle}>
                  The Curator
                </Typography.Title>
                <Typography.Text type="secondary">Good morning, breathe deeply.</Typography.Text>
              </div>
            </div>

            <Button
              type="primary"
              block
              icon={<PlusCircleOutlined />}
              loading={creatingSession}
              onClick={handleCreateSession}
              className={styles.newSessionButton}
            >
              New Session
            </Button>

            {loadingSessions ? (
              <div className={styles.loadingArea}>
                <Spin />
              </div>
            ) : (
              <List
                dataSource={sessions}
                className={styles.sessionList}
                renderItem={(item) => (
                  <List.Item
                    className={`${styles.sessionItem} ${item._id === activeSessionId ? styles.sessionItemActive : ""}`}
                    onClick={() => setActiveSessionId(item._id)}
                  >
                    <List.Item.Meta
                      title={item.title}
                      description={
                        item.last_message_preview ? item.last_message_preview : "Start a mindful conversation"
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Layout.Sider>

          <Layout className={styles.contentLayout}>
            <div className={styles.chatHeader}>
              <div>
                <Typography.Title level={2} className={styles.chatTitle}>
                  Wye Chat
                </Typography.Title>
                <Typography.Text type="secondary" italic>
                  A safe space for your thoughts
                </Typography.Text>
              </div>
              <Space>
                <Tag color={connected ? "green" : "orange"}>{connected ? "Socket online" : "Socket offline"}</Tag>
                <Avatar icon={<RobotOutlined />} className={styles.botAvatar} />
              </Space>
            </div>

            <div className={styles.messageBoard}>
              {loadingMessages ? (
                <div className={styles.loadingArea}>
                  <Spin />
                </div>
              ) : activeMessages.length === 0 ? (
                <Empty description="Chưa có tin nhắn nào, hãy bắt đầu một cuộc trò chuyện." />
              ) : (
                <div className={styles.messageList}>
                  {activeMessages.map((msg) => {
                    const isUser = msg.role === "user";
                    return (
                      <div key={msg._id} className={`${styles.messageRow} ${isUser ? styles.messageUser : ""}`}>
                        <Avatar icon={isUser ? <UserOutlined /> : <RobotOutlined />} />
                        <Card className={`${styles.messageBubble} ${isUser ? styles.userBubble : styles.aiBubble}`}>
                          <Typography.Paragraph className={styles.messageText}>{msg.content}</Typography.Paragraph>
                          <Typography.Text type="secondary" className={styles.messageTime}>
                            {formatTime(msg.created_at)} {msg.pending ? "· Sending..." : ""}
                          </Typography.Text>
                        </Card>
                      </div>
                    );
                  })}
                  <div ref={messageEndRef} />
                </div>
              )}
            </div>

            <Row gutter={[16, 16]} className={styles.insightRow}>
              <Col xs={24} md={12}>
                <Card title="Weekly Mood Summary" className={styles.insightCard}>
                  <Typography.Paragraph>
                    You have felt calm in most recent check-ins. Keep a gentle pace and remember to pause.
                  </Typography.Paragraph>
                </Card>
              </Col>
              <Col xs={24} md={12}>
                <Card className={styles.quoteCard}>
                  <BulbOutlined className={styles.quoteIcon} />
                  <Typography.Paragraph italic>
                    &quot;Within you, there is a stillness and a sanctuary to which you can retreat at any time.&quot;
                  </Typography.Paragraph>
                  <Typography.Text strong>— Hermann Hesse</Typography.Text>
                </Card>
              </Col>
            </Row>

            <div className={styles.footerComposer}>
              <div className={styles.quickReplies}>
                {quickReplies.map((item) => (
                  <Button key={item} onClick={() => setInputValue(item)} className={styles.quickReplyButton}>
                    {item}
                  </Button>
                ))}
              </div>

              <Input.TextArea
                autoSize={{ minRows: 2, maxRows: 6 }}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onPressEnter={(e) => {
                  if (e.shiftKey) return;
                  e.preventDefault();
                  handleSendMessage();
                }}
                placeholder="Type your heart's thoughts..."
                className={styles.composerInput}
              />

              <div className={styles.composerActions}>
                <Button icon={<MessageOutlined />} onClick={() => setInputValue("Can we talk?")} />
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  onClick={handleSendMessage}
                  loading={sending}
                  disabled={!inputValue.trim()}
                >
                  Send
                </Button>
              </div>
            </div>
          </Layout>
        </Layout>
      </main>
      <Footer />
    </>
  );
}
