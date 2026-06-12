"use client";

import { useState } from "react";
import Link from "next/link";
import { format, parseISO } from "date-fns";
import {
  ChevronLeft,
  ChevronRight,
  Clock,
  Loader2,
  MessageSquare,
  RefreshCw,
  Search,
  User,
  UserX,
} from "lucide-react";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useAdminConversations,
  useConversationStats,
  useSupportQueue,
} from "@/lib/hooks/admin-queries";
import { filterAwaitingSupportQueue } from "@/components/admin/support-queue-sidebar";
import { ChatMessageMarkdown } from "@/components/therapy/chat-message-markdown";
import type {
  AdminConversation,
  ConversationOwnerFilter,
} from "@/lib/api/admin-conversations";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 10;

function formatNum(n: number) {
  return n.toLocaleString("vi-VN");
}

function formatTime(iso: string | null) {
  if (!iso) return "—";
  try {
    return format(parseISO(iso), "dd/MM/yyyy HH:mm");
  } catch {
    return "—";
  }
}

function truncateSessionId(id: string, len = 8) {
  if (id.length <= len * 2 + 3) return id;
  return `${id.slice(0, len)}…${id.slice(-len)}`;
}

function userLabel(conv: AdminConversation) {
  if (conv.user?.name) return conv.user.name;
  if (conv.user?.email) return conv.user.email;
  return "Khách";
}

export default function AdminConversationsPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [ownerFilter, setOwnerFilter] = useState<"" | ConversationOwnerFilter>(
    ""
  );
  const [detail, setDetail] = useState<AdminConversation | null>(null);

  const {
    data: stats,
    isFetching: statsFetching,
    refetch: refetchStats,
  } = useConversationStats(7);

  const {
    data,
    isPending,
    isFetching: listFetching,
    error: queryError,
    refetch: refetchList,
  } = useAdminConversations({
    page,
    page_size: PAGE_SIZE,
    search: search || undefined,
    owner: ownerFilter || undefined,
  });

  const {
    data: queueData,
    isFetching: queueFetching,
    refetch: refetchQueue,
  } = useSupportQueue();

  const needsSupport = filterAwaitingSupportQueue(queueData?.conversations ?? []);
  const total = data?.total ?? 0;
  const totalPages = data?.total_pages ?? 1;
  const loading = isPending && !data;

  const error =
    queryError instanceof Error
      ? queryError.message
      : queryError
        ? "Không tải được danh sách"
        : "";

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setSearch(searchInput.trim());
  };

  const resetFilters = () => {
    setSearchInput("");
    setSearch("");
    setOwnerFilter("");
    setPage(1);
  };

  const handleRefresh = () => {
    void refetchStats();
    void refetchList();
    void refetchQueue();
  };

  const conversations = data?.conversations ?? [];

  const rangeStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(page * PAGE_SIZE, total);

  const chartData =
    stats?.messages_by_day.map((d) => ({
      name: d.label,
      messages: d.messages,
      sessions: d.active_sessions,
      newSessions: d.new_sessions,
    })) ?? [];

  if (loading) {
    return (
      <div className="flex justify-center py-32">
        <Loader2 className="h-8 w-8 animate-spin text-serene-accent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-12 pb-20 pt-8">
      <div className="mb-10 flex flex-wrap items-end justify-between gap-6">
        <div>
          <h3 className="mb-2 font-serif text-3xl italic tracking-tight text-foreground">
            Hội thoại
          </h3>
          <p className="max-w-xl text-muted-foreground leading-relaxed">
            Danh sách phiên chat, hàng chờ hỗ trợ và thống kê hoạt động.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {stats?.updated_at && (
            <div className="hidden items-center gap-2 text-xs font-medium uppercase tracking-widest text-serene-accent sm:flex">
              <Clock className="h-4 w-4" />
              Cập nhật:{" "}
              {format(parseISO(stats.updated_at), "HH:mm dd/MM/yyyy")}
            </div>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={statsFetching || listFetching}
          >
            <RefreshCw
              className={`mr-1 h-4 w-4 ${statsFetching || listFetching ? "animate-spin" : ""}`}
            />
            Làm mới
          </Button>
        </div>
      </div>

      {stats && (
        <>
          <div className="mb-8 grid grid-cols-12 gap-4">
            <div className="col-span-12 bg-[#f4f4ef] p-6 md:col-span-3">
              <p className="mb-2 text-xs font-medium uppercase tracking-widest text-muted-foreground opacity-60">
                Tổng phiên
              </p>
              <p className="font-serif text-3xl italic text-serene-accent">
                {formatNum(stats.total_conversations)}
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                +{formatNum(stats.conversations_today)} hôm nay
              </p>
            </div>
            <div className="col-span-12 bg-[#e9e8e4] p-6 md:col-span-3">
              <p className="mb-2 text-xs font-medium uppercase tracking-widest text-muted-foreground opacity-60">
                Tin nhắn
              </p>
              <p className="font-serif text-3xl text-foreground">
                {formatNum(stats.total_messages)}
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                +{formatNum(stats.messages_today)} hôm nay · TB{" "}
                {stats.avg_messages_per_conversation}/phiên
              </p>
            </div>
            <div className="col-span-12 bg-white p-6 md:col-span-3">
              <p className="mb-2 text-xs font-medium uppercase tracking-widest text-muted-foreground opacity-60">
                Phiên đăng nhập
              </p>
              <p className="font-serif text-3xl text-foreground">
                {formatNum(stats.registered_sessions)}
              </p>
              <p className="mt-2 flex items-center gap-1 text-sm text-muted-foreground">
                <User className="h-3.5 w-3.5" />
                {formatNum(stats.unique_users_with_sessions ?? 0)} tài khoản
              </p>
            </div>
            <div className="col-span-12 bg-[#f4f4ef] p-6 md:col-span-3">
              <p className="mb-2 text-xs font-medium uppercase tracking-widest text-muted-foreground opacity-60">
                Khách
              </p>
              <p className="font-serif text-3xl text-foreground">
                {formatNum(stats.guest_sessions)}
              </p>
              <p className="mt-2 flex items-center gap-1 text-sm text-muted-foreground">
                <UserX className="h-3.5 w-3.5" />
                {formatNum(stats.with_summary)} có tóm tắt
              </p>
            </div>
          </div>

          {chartData.length > 0 && (
            <div className="mb-10 bg-white p-6">
              <div className="mb-4 flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-serene-accent" />
                <h4 className="text-sm font-medium uppercase tracking-widest text-muted-foreground">
                  Hoạt động 7 ngày qua
                </h4>
              </div>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} barGap={2}>
                    <XAxis
                      dataKey="name"
                      axisLine={false}
                      tickLine={false}
                      tick={{ fontSize: 11, fill: "#6b7280" }}
                    />
                    <YAxis
                      axisLine={false}
                      tickLine={false}
                      tick={{ fontSize: 11, fill: "#6b7280" }}
                      width={36}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#f4f4ef",
                        border: "none",
                        borderRadius: 0,
                        fontSize: 12,
                      }}
                    />
                    <Bar
                      dataKey="messages"
                      name="Tin nhắn"
                      fill="#4a6741"
                      radius={[2, 2, 0, 0]}
                    />
                    <Bar
                      dataKey="sessions"
                      name="Phiên hoạt động"
                      fill="#a8b5a0"
                      radius={[2, 2, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </>
      )}

      <Tabs defaultValue="all" className="mb-6">
        <TabsList className="mb-6 h-auto rounded-none border-b border-border/40 bg-transparent p-0">
          <TabsTrigger
            value="all"
            className="rounded-none border-b-2 border-transparent px-4 py-2 data-[state=active]:border-serene-accent data-[state=active]:bg-transparent data-[state=active]:shadow-none"
          >
            Tất cả phiên
          </TabsTrigger>
          <TabsTrigger
            value="support"
            className="rounded-none border-b-2 border-transparent px-4 py-2 data-[state=active]:border-amber-600 data-[state=active]:bg-transparent data-[state=active]:shadow-none"
          >
            Cần hỗ trợ
            {needsSupport.length > 0 && (
              <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                {needsSupport.length}
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="all" className="mt-0">
      <form onSubmit={handleSearch} className="mb-6 flex flex-wrap items-center gap-4">
        <div className="relative w-full max-w-md">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Tìm theo tiêu đề, session ID..."
            className="border-none bg-[#f4f4ef] pl-10 focus-visible:ring-serene-green/30"
          />
        </div>
        <Button type="submit" variant="outline" size="sm">
          Tìm
        </Button>
        <Select
          value={ownerFilter || "all"}
          onValueChange={(v) => {
            setOwnerFilter(
              v === "all" ? "" : (v as ConversationOwnerFilter)
            );
            setPage(1);
          }}
        >
          <SelectTrigger className="w-44 bg-white">
            <SelectValue placeholder="Người dùng" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tất cả</SelectItem>
            <SelectItem value="registered">Đã đăng nhập</SelectItem>
            <SelectItem value="guest">Khách</SelectItem>
          </SelectContent>
        </Select>
        {(search || ownerFilter) && (
          <Button type="button" variant="ghost" size="sm" onClick={resetFilters}>
            Xóa bộ lọc
          </Button>
        )}
      </form>

      {error && <p className="mb-4 text-sm text-destructive">{error}</p>}

      <div className="mb-4 flex items-center justify-between">
        <h4 className="font-serif text-xl italic">
          Danh sách phiên ({formatNum(total)})
        </h4>
        {total > 0 && (
          <p className="text-xs text-muted-foreground">
            {rangeStart}–{rangeEnd} / {formatNum(total)}
          </p>
        )}
      </div>

      <div className="border border-border/40 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border/40 bg-[#f4f4ef]/60 text-xs uppercase tracking-widest text-muted-foreground">
            <tr>
              <th className="px-6 py-4 font-medium">Tiêu đề</th>
              <th className="px-4 py-4 font-medium">Người dùng</th>
              <th className="px-4 py-4 font-medium">Tin nhắn</th>
              <th className="px-4 py-4 font-medium">Cập nhật</th>
              <th className="px-4 py-4 font-medium">Session ID</th>
            </tr>
          </thead>
          <tbody>
            {conversations.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-6 py-16 text-center text-muted-foreground"
                >
                  Không có phiên hội thoại nào.
                </td>
              </tr>
            ) : (
              conversations.map((conv) => (
                <tr
                  key={conv.session_id}
                  className="cursor-pointer border-b border-border/20 transition-colors hover:bg-[#f4f4ef]/40"
                  onClick={() => setDetail(conv)}
                >
                  <td className="px-6 py-4">
                    <p className="max-w-xs truncate font-medium text-foreground">
                      {conv.title}
                    </p>
                    {conv.summary && (
                      <p className="mt-0.5 max-w-xs truncate text-xs text-muted-foreground">
                        {conv.summary}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-4">
                    <span
                      className={cn(
                        "inline-flex items-center gap-1.5 text-sm",
                        conv.user ? "text-foreground" : "text-muted-foreground"
                      )}
                    >
                      {conv.user ? (
                        <User className="h-3.5 w-3.5" />
                      ) : (
                        <UserX className="h-3.5 w-3.5" />
                      )}
                      {userLabel(conv)}
                    </span>
                  </td>
                  <td className="px-4 py-4 tabular-nums">
                    {formatNum(conv.message_count)}
                  </td>
                  <td className="px-4 py-4 text-muted-foreground">
                    {formatTime(conv.updated_at)}
                  </td>
                  <td className="px-4 py-4 font-mono text-xs text-muted-foreground">
                    {truncateSessionId(conv.session_id)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-4">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm text-muted-foreground">
            Trang {page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}

        </TabsContent>

        <TabsContent value="support" className="mt-0">
          <div className="mb-4 flex items-center justify-between">
            <h4 className="font-serif text-xl italic text-amber-950">
              Phiên chờ hỗ trợ ({formatNum(needsSupport.length)})
            </h4>
            {queueFetching && (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            )}
          </div>

          <div className="border border-amber-200/60 bg-white">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border/40 bg-amber-50/50 text-xs uppercase tracking-widest text-muted-foreground">
                <tr>
                  <th className="px-6 py-4 font-medium">Tiêu đề</th>
                  <th className="px-4 py-4 font-medium">Người dùng</th>
                  <th className="px-4 py-4 font-medium">Yêu cầu lúc</th>
                  <th className="px-4 py-4 font-medium">Session ID</th>
                  <th className="px-4 py-4 font-medium" />
                </tr>
              </thead>
              <tbody>
                {needsSupport.length === 0 ? (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-6 py-16 text-center text-muted-foreground"
                    >
                      Không có phiên nào đang chờ hỗ trợ.
                    </td>
                  </tr>
                ) : (
                  needsSupport.map((conv) => (
                    <tr
                      key={conv.session_id}
                      className="border-b border-border/20 transition-colors hover:bg-amber-50/30"
                    >
                      <td className="px-6 py-4">
                        <p className="max-w-xs truncate font-medium text-foreground">
                          {conv.title}
                        </p>
                        {conv.summary && (
                          <p className="mt-0.5 max-w-xs truncate text-xs text-muted-foreground">
                            {conv.summary.replace(/[#*_`]/g, "").slice(0, 80)}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-4">
                        <span className="inline-flex items-center gap-1.5 text-sm">
                          {conv.user ? (
                            <User className="h-3.5 w-3.5" />
                          ) : (
                            <UserX className="h-3.5 w-3.5" />
                          )}
                          {userLabel(conv)}
                        </span>
                      </td>
                      <td className="px-4 py-4 text-muted-foreground">
                        {formatTime(conv.handoff_requested_at ?? conv.updated_at)}
                      </td>
                      <td className="px-4 py-4 font-mono text-xs text-muted-foreground">
                        {truncateSessionId(conv.session_id)}
                      </td>
                      <td className="px-4 py-4 text-right">
                        <Button size="sm" asChild>
                          <Link
                            href={`/admin/conversations/${conv.session_id}?join=1`}
                          >
                            Tham gia
                          </Link>
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </TabsContent>
      </Tabs>

      <Dialog open={!!detail} onOpenChange={(open) => !open && setDetail(null)}>
        <DialogContent className="flex max-h-[min(85vh,100dvh-2rem)] max-w-lg flex-col overflow-hidden p-0">
          <DialogHeader className="shrink-0 space-y-1.5 px-6 pt-6 pr-12">
            <DialogTitle className="font-serif italic leading-snug">
              {detail?.title}
            </DialogTitle>
            <DialogDescription>
              Thông tin phiên — không hiển thị nội dung tin nhắn.
            </DialogDescription>
          </DialogHeader>
          {detail && (
            <div className="admin-scrollbar min-h-0 flex-1 overflow-y-auto px-6 pb-6">
              <dl className="space-y-3 text-sm">
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-muted-foreground">Người dùng</dt>
                  <dd className="col-span-2">{userLabel(detail)}</dd>
                </div>
                {detail.user?.email && (
                  <div className="grid grid-cols-3 gap-2">
                    <dt className="text-muted-foreground">Email</dt>
                    <dd className="col-span-2">{detail.user.email}</dd>
                  </div>
                )}
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-muted-foreground">Session ID</dt>
                  <dd className="col-span-2 break-all font-mono text-xs">
                    {detail.session_id}
                  </dd>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-muted-foreground">Chế độ</dt>
                  <dd className="col-span-2">{detail.chat_mode}</dd>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-muted-foreground">Tin nhắn</dt>
                  <dd className="col-span-2">
                    {formatNum(detail.message_count)} (chỉ số lượng)
                  </dd>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-muted-foreground">Tạo lúc</dt>
                  <dd className="col-span-2">{formatTime(detail.created_at)}</dd>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-muted-foreground">Cập nhật</dt>
                  <dd className="col-span-2">{formatTime(detail.updated_at)}</dd>
                </div>
                {detail.summary && (
                  <div>
                    <dt className="mb-1 text-muted-foreground">Tóm tắt</dt>
                    <dd className="rounded bg-[#f4f4ef] p-3 text-foreground leading-relaxed">
                      <ChatMessageMarkdown content={detail.summary} />
                    </dd>
                  </div>
                )}
                {detail.support_mode === "awaiting_support" && (
                  <Button size="sm" asChild className="mt-2">
                    <Link href={`/admin/conversations/${detail.session_id}?join=1`}>
                      Tham gia hỗ trợ
                    </Link>
                  </Button>
                )}
                {detail.support_mode === "human" && (
                  <Button size="sm" variant="outline" asChild className="mt-2">
                    <Link href={`/admin/conversations/${detail.session_id}`}>
                      Xem phiên hỗ trợ
                    </Link>
                  </Button>
                )}
              </dl>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
