"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { format, parseISO } from "date-fns";
import {
  ArrowRight,
  Clock,
  Loader2,
  MessageSquare,
  RefreshCw,
  Star,
  TrendingUp,
  Users,
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
import {
  getAdminOverview,
  type AdminOverviewStats,
} from "@/lib/api/admin-overview";

function formatNum(n: number) {
  return n.toLocaleString("vi-VN");
}

export default function AdminOverviewPage() {
  const [stats, setStats] = useState<AdminOverviewStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getAdminOverview(7);
      setStats(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được dữ liệu");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !stats) {
    return (
      <div className="flex justify-center py-32">
        <Loader2 className="h-8 w-8 animate-spin text-serene-accent" />
      </div>
    );
  }

  const chartData =
    stats?.messages_by_day.map((d) => ({
      name: d.label,
      messages: d.messages,
      sessions: d.active_sessions,
    })) ?? [];

  const maxMessages = Math.max(...chartData.map((d) => d.messages), 1);

  return (
    <div className="mx-auto max-w-7xl px-12 pb-12 pt-8">
      <div className="mb-12 flex items-end justify-between">
        <div>
          <h3 className="mb-2 font-serif text-3xl italic tracking-tight text-foreground">
            Tổng quan
          </h3>
          <p className="max-w-lg text-muted-foreground leading-relaxed">
            Trạng thái hệ sinh thái Helios — phiên chat, tin nhắn và hoạt động
            wellness.
          </p>
        </div>
        <div className="flex items-center gap-4">
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
            onClick={() => void load()}
            disabled={loading}
          >
            <RefreshCw
              className={`mr-1 h-4 w-4 ${loading ? "animate-spin" : ""}`}
            />
            Làm mới
          </Button>
        </div>
      </div>

      {error && (
        <p className="mb-6 text-sm text-destructive">{error}</p>
      )}

      {stats && (
        <>
          <div className="mb-12 grid grid-cols-12 gap-6">
            {/* Users */}
            <div className="relative col-span-12 overflow-hidden bg-[#f4f4ef] p-8 md:col-span-4">
              <p className="mb-4 text-xs font-medium uppercase tracking-widest text-muted-foreground opacity-60">
                Người dùng đăng ký
              </p>
              <h4 className="font-serif text-4xl italic text-serene-accent">
                {formatNum(stats.total_users)}
              </h4>
              {stats.user_growth_pct !== null && (
                <div className="mt-6 flex items-center gap-2 font-bold text-serene-accent">
                  <TrendingUp className="h-4 w-4" />
                  <span className="text-sm">
                    {stats.user_growth_pct >= 0 ? "+" : ""}
                    {stats.user_growth_pct}% so với tháng trước
                  </span>
                </div>
              )}
              <Users className="absolute -bottom-4 -right-4 h-40 w-40 text-serene-accent opacity-[0.04]" />
            </div>

            {/* Messages today */}
            <div className="col-span-12 bg-[#e9e8e4] p-8 md:col-span-4">
              <p className="mb-4 text-xs font-medium uppercase tracking-widest text-muted-foreground opacity-60">
                Tin nhắn hôm nay
              </p>
              <div className="flex items-baseline gap-2">
                <h4 className="font-serif text-4xl text-foreground">
                  {formatNum(stats.messages_today)}
                </h4>
                <span className="text-sm italic text-muted-foreground">
                  / {formatNum(stats.conversations_today)} phiên
                </span>
              </div>
              <div className="mt-8 flex h-12 items-end gap-1.5">
                {chartData.map((d, i) => (
                  <div
                    key={d.name}
                    className="w-full rounded-sm bg-serene-green/25 transition-all duration-700"
                    style={{
                      height: `${Math.max(12, (d.messages / maxMessages) * 100)}%`,
                      backgroundColor:
                        i === chartData.length - 1
                          ? "hsl(var(--primary))"
                          : undefined,
                    }}
                  />
                ))}
              </div>
            </div>

            {/* Sessions total */}
            <div className="col-span-12 flex flex-col justify-between bg-serene-green/80 p-8 text-white md:col-span-4">
              <div>
                <p className="mb-4 text-xs font-medium uppercase tracking-widest opacity-80">
                  Tổng phiên chat
                </p>
                <h4 className="font-serif text-4xl italic">
                  {formatNum(stats.total_conversations)}
                </h4>
                <p className="mt-2 text-sm opacity-70">
                  {formatNum(stats.total_messages)} tin nhắn tích lũy
                </p>
              </div>
              <div className="mt-6 flex items-center gap-3">
                <div className="rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs">
                  Phiên hoạt động
                </div>
                <MessageSquare className="h-5 w-5 opacity-60" />
              </div>
            </div>

            {/* Knowledge pipeline */}
            <div className="col-span-12 flex flex-col gap-10 border border-border/30 bg-white p-10 lg:col-span-8 lg:flex-row lg:items-center">
              <div className="flex-1">
                <p className="mb-2 text-xs font-bold uppercase tracking-widest text-serene-accent">
                  Pipeline tri thức
                </p>
                <h3 className="mb-6 font-serif text-2xl">Trạng thái bài viết</h3>
                <div className="space-y-5">
                  <Link
                    href="/admin/knowledge"
                    className="group flex cursor-pointer items-center justify-between"
                  >
                    <div className="flex items-center gap-4">
                      <span className="h-3 w-3 rounded-full bg-destructive" />
                      <span className="font-bold">Chờ duyệt</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="italic text-muted-foreground">
                        {formatNum(stats.knowledge_staging.pending)} bài
                      </span>
                      <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-1" />
                    </div>
                  </Link>
                  <div className="h-px bg-border/40" />
                  <Link
                    href="/admin/knowledge"
                    className="group flex cursor-pointer items-center justify-between"
                  >
                    <div className="flex items-center gap-4">
                      <span className="h-3 w-3 rounded-full bg-serene-accent" />
                      <span className="font-bold">Đã duyệt</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="italic text-muted-foreground">
                        {formatNum(stats.knowledge_staging.approved)} bài
                      </span>
                      <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-1" />
                    </div>
                  </Link>
                </div>
              </div>
              <div className="flex h-48 w-48 shrink-0 items-center justify-center self-center rounded-full bg-[#efeeea]">
                <div className="text-center">
                  <span className="font-serif text-3xl italic text-serene-accent">
                    {stats.knowledge_staging_health_pct}%
                  </span>
                  <p className="text-xs uppercase tracking-tight text-muted-foreground">
                    Đã xử lý
                  </p>
                </div>
              </div>
            </div>

            {/* Wellness */}
            <div className="col-span-12 flex flex-col gap-6 lg:col-span-4">
              <div className="flex-1 bg-[#f4f4ef] p-8">
                <p className="mb-4 text-xs font-medium uppercase tracking-widest text-muted-foreground opacity-60">
                  Wellness hoàn thành
                </p>
                <div className="flex items-end justify-between">
                  <h4 className="font-serif text-3xl text-serene-accent">
                    {formatNum(stats.wellness_completions_today)}
                  </h4>
                  <div className="text-right text-sm">
                    <p className="italic text-muted-foreground">Hôm nay</p>
                    <p className="font-bold">
                      {formatNum(stats.wellness_completions_total)} tổng
                    </p>
                  </div>
                </div>
              </div>
              <div className="flex-1 border-l-4 border-serene-accent bg-[#efeeea] p-8">
                <p className="mb-4 text-xs font-medium uppercase tracking-widest text-muted-foreground opacity-60">
                  Đánh giá wellness TB
                </p>
                <div className="flex items-center gap-4">
                  <h4 className="font-serif text-3xl">
                    {stats.avg_wellness_rating?.toFixed(1) ?? "—"}
                  </h4>
                  <div className="flex text-serene-accent">
                    <Star className="h-5 w-5 fill-current" />
                  </div>
                </div>
                <p className="mt-2 text-sm text-muted-foreground">
                  Dựa trên {formatNum(stats.total_wellness_ratings)} đánh giá
                </p>
              </div>
            </div>
          </div>

          {/* Chart section */}
          <section className="mb-12 rounded-xl border border-border/30 bg-white p-10">
            <h2 className="mb-2 font-serif text-xl italic">
              Tin nhắn & phiên theo ngày
            </h2>
            <p className="mb-8 text-sm text-muted-foreground">
              7 ngày gần nhất
            </p>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} barGap={4}>
                  <XAxis
                    dataKey="name"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 12, fill: "#737970" }}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 12, fill: "#737970" }}
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={{
                      borderRadius: "8px",
                      border: "1px solid #e5e7e2",
                      fontFamily: "var(--font-noto-serif)",
                    }}
                    formatter={(value: number, name: string) => [
                      value,
                      name === "messages" ? "Tin nhắn" : "Phiên hoạt động",
                    ]}
                  />
                  <Bar
                    dataKey="messages"
                    fill="hsl(var(--primary))"
                    radius={[2, 2, 0, 0]}
                    name="messages"
                  />
                  <Bar
                    dataKey="sessions"
                    fill="hsl(var(--primary) / 0.35)"
                    radius={[2, 2, 0, 0]}
                    name="sessions"
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
