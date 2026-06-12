"use client";

import { useState } from "react";
import { format, parseISO } from "date-fns";
import {
  Brain,
  Clock,
  Coins,
  Database,
  Globe,
  Loader2,
  RefreshCw,
  Search,
  Shield,
  Zap,
} from "lucide-react";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useAdminSettings,
  useAdminUsageStats,
} from "@/lib/hooks/admin-queries";
import { cn } from "@/lib/utils";

function formatNum(n: number) {
  return n.toLocaleString("vi-VN");
}

function formatCost(usd: number) {
  if (usd === 0) return "$0.00";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

function ConfigRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border/30 py-3 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span
        className={cn(
          "max-w-[60%] text-right text-sm text-foreground",
          mono && "font-mono text-xs"
        )}
      >
        {value}
      </span>
    </div>
  );
}

function BoolBadge({ on, labelOn = "Bật", labelOff = "Tắt" }: { on: boolean; labelOn?: string; labelOff?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "font-normal",
        on
          ? "border-emerald-300 bg-emerald-50 text-emerald-800"
          : "border-border bg-muted/50 text-muted-foreground"
      )}
    >
      {on ? labelOn : labelOff}
    </Badge>
  );
}

function ConfiguredBadge({ configured }: { configured: boolean }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "font-normal",
        configured
          ? "border-emerald-300 bg-emerald-50 text-emerald-800"
          : "border-amber-300 bg-amber-50 text-amber-800"
      )}
    >
      {configured ? "Đã cấu hình" : "Chưa cấu hình"}
    </Badge>
  );
}

function SectionCard({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: typeof Brain;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-border/40 bg-white/70 p-6 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <Icon className="h-4 w-4 text-serene-accent" />
        <h4 className="font-serif text-lg italic text-foreground">{title}</h4>
      </div>
      {children}
    </div>
  );
}

export default function AdminSettingsPage() {
  const [usageDays, setUsageDays] = useState(7);
  const {
    data: settings,
    isPending: settingsPending,
    isFetching: settingsFetching,
    error: settingsError,
    refetch: refetchSettings,
  } = useAdminSettings();
  const {
    data: usage,
    isPending: usagePending,
    isFetching: usageFetching,
    refetch: refetchUsage,
  } = useAdminUsageStats(usageDays);

  if (settingsPending && !settings) {
    return (
      <div className="flex justify-center py-32">
        <Loader2 className="h-8 w-8 animate-spin text-serene-accent" />
      </div>
    );
  }

  if (settingsError || !settings) {
    return (
      <div className="mx-auto max-w-7xl px-12 py-16 text-center text-muted-foreground">
        Không tải được cấu hình hệ thống.
      </div>
    );
  }

  const chartData =
    usage?.by_day.map((d) => ({
      name: d.date.slice(5),
      tokens: d.total_tokens,
      cost: d.cost_usd,
    })) ?? [];

  return (
    <div className="mx-auto max-w-7xl px-12 pb-12 pt-8">
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h3 className="mb-2 font-serif text-3xl italic tracking-tight text-foreground">
            Cài đặt AI & hệ thống
          </h3>
        </div>
        <div className="flex items-center gap-3">
          {settings.updated_at && (
            <div className="hidden items-center gap-2 text-xs font-medium uppercase tracking-widest text-serene-accent sm:flex">
              <Clock className="h-4 w-4" />
              {format(parseISO(settings.updated_at), "HH:mm dd/MM/yyyy")}
            </div>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void refetchSettings();
              void refetchUsage();
            }}
            disabled={settingsFetching || usageFetching}
          >
            <RefreshCw
              className={cn(
                "mr-1 h-4 w-4",
                (settingsFetching || usageFetching) && "animate-spin"
              )}
            />
            Làm mới
          </Button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-2xl border border-border/40 bg-white/70 p-5">
          <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-widest text-muted-foreground">
            <Zap className="h-3.5 w-3.5" />
            LLM đang dùng
          </div>
          <p className="font-serif text-xl italic text-serene-accent">
            {settings.llm.primary_provider}
          </p>
          <p className="mt-1 truncate font-mono text-xs text-muted-foreground">
            {settings.llm.active_model}
          </p>
        </div>
        <div className="rounded-2xl border border-border/40 bg-white/70 p-5">
          <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-widest text-muted-foreground">
            <Brain className="h-3.5 w-3.5" />
            Fallback chain
          </div>
          <p className="font-mono text-sm text-foreground">
            {settings.llm.fallback_chain.join(" → ")}
          </p>
        </div>
        <div className="rounded-2xl border border-border/40 bg-white/70 p-5">
          <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-widest text-muted-foreground">
            <Database className="h-3.5 w-3.5" />
            Qdrant collections
          </div>
          <p className="text-sm text-foreground">
            PDF · Web · Wellness
          </p>
          <p className="mt-1 truncate font-mono text-xs text-muted-foreground">
            {settings.rag.collections.pdf_rag}
          </p>
        </div>
        <div className="rounded-2xl border border-border/40 bg-white/70 p-5">
          <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-widest text-muted-foreground">
            <Coins className="h-3.5 w-3.5" />
            Token hôm nay
          </div>
          {usagePending && !usage ? (
            <Loader2 className="h-5 w-5 animate-spin text-serene-accent" />
          ) : (
            <>
              <p className="font-serif text-xl italic text-serene-accent">
                {formatNum(usage?.today.total_tokens ?? 0)}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                ~{formatCost(usage?.today.cost_usd ?? 0)} ·{" "}
                {formatNum(usage?.today.calls ?? 0)} lần gọi
              </p>
            </>
          )}
        </div>
      </div>

      <Tabs defaultValue="llm" className="space-y-6">
        <TabsList className="h-auto flex-wrap gap-1 bg-white/60 p-1">
          <TabsTrigger value="llm" className="gap-1.5">
            <Zap className="h-3.5 w-3.5" />
            LLM
          </TabsTrigger>
          <TabsTrigger value="rag" className="gap-1.5">
            <Database className="h-3.5 w-3.5" />
            RAG
          </TabsTrigger>
          <TabsTrigger value="web" className="gap-1.5">
            <Globe className="h-3.5 w-3.5" />
            Web search
          </TabsTrigger>
          <TabsTrigger value="guardrails" className="gap-1.5">
            <Shield className="h-3.5 w-3.5" />
            Guardrails
          </TabsTrigger>
          <TabsTrigger value="usage" className="gap-1.5">
            <Coins className="h-3.5 w-3.5" />
            Token & chi phí
          </TabsTrigger>
        </TabsList>

        <TabsContent value="llm">
          <div className="grid gap-6 lg:grid-cols-2">
            <SectionCard title="Provider đang hoạt động" icon={Zap}>
              <ConfigRow label="Primary provider" value={settings.llm.primary_provider} mono />
              <ConfigRow label="Active model" value={settings.llm.active_model} mono />
              <ConfigRow
                label="Fallback chain (.env)"
                value={settings.llm.fallback_chain_env}
                mono
              />
              <ConfigRow
                label="Chuỗi đã lọc (configured)"
                value={settings.llm.fallback_chain.join(", ")}
                mono
              />
              <ConfigRow
                label="Ingest LLM provider"
                value={settings.llm.ingest_llm_provider}
                mono
              />
              <ConfigRow
                label="Local chat (Ollama)"
                value={<BoolBadge on={settings.llm.enable_local_chat} />}
              />
              <ConfigRow
                label="Debug LLM prompts"
                value={<BoolBadge on={settings.llm.debug_llm_prompts} />}
              />
            </SectionCard>

            <SectionCard title="Tất cả providers" icon={Brain}>
              <div className="space-y-4">
                {settings.llm.providers.map((p) => (
                  <div
                    key={p.name}
                    className="rounded-xl border border-border/30 bg-serene-bg/40 p-4"
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <span className="font-medium capitalize">{p.name}</span>
                      <ConfiguredBadge configured={p.configured} />
                    </div>
                    <p className="font-mono text-xs text-muted-foreground">{p.model}</p>
                    {p.base_url && (
                      <p className="mt-1 font-mono text-xs text-muted-foreground">
                        {p.base_url}
                      </p>
                    )}
                    {p.api_key.configured && p.api_key.masked && (
                      <p className="mt-1 font-mono text-xs text-muted-foreground">
                        Key: {p.api_key.masked}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </SectionCard>
          </div>
        </TabsContent>

        <TabsContent value="rag">
          <div className="grid gap-6 lg:grid-cols-2">
            <SectionCard title="Retrieval & chunking" icon={Database}>
              <ConfigRow label="Embedding provider" value={settings.rag.embedding_provider} mono />
              <ConfigRow label="Embedding model" value={settings.rag.embedding_model} mono />
              <ConfigRow label="Top-K retrieval" value={settings.rag.top_k} />
              <ConfigRow label="Reranker top-K" value={settings.rag.reranker_top_k} />
              <ConfigRow
                label="Min retrieval confidence"
                value={settings.rag.min_retrieval_confidence}
              />
              <ConfigRow label="Vector search" value={settings.rag.vector_search_type} />
              <ConfigRow label="Distance metric" value={settings.rag.distance_metric} />
              <ConfigRow label="Chunk size (words)" value={settings.rag.chunk_size_words} />
              <ConfigRow label="Chunk overlap" value={settings.rag.chunk_overlap_words} />
              <ConfigRow
                label="LLM chunking"
                value={<BoolBadge on={settings.rag.enable_llm_chunking} />}
              />
            </SectionCard>

            <SectionCard title="Qdrant collections" icon={Search}>
              <ConfigRow label="PDF RAG" value={settings.rag.collections.pdf_rag} mono />
              <ConfigRow label="Web corpus" value={settings.rag.collections.web_corpus} mono />
              <ConfigRow label="Wellness" value={settings.rag.collections.wellness} mono />
              <ConfigRow label="Qdrant URL" value={settings.rag.qdrant_url} mono />
              <ConfigRow label="Wellness top-K" value={settings.rag.wellness_top_k} />
              <ConfigRow label="Wellness min score" value={settings.rag.wellness_min_score} />
              <ConfigRow
                label="Suggestion min score"
                value={settings.rag.wellness_suggestion_min_score}
              />
            </SectionCard>
          </div>
        </TabsContent>

        <TabsContent value="web">
          <div className="grid gap-6 lg:grid-cols-2">
            <SectionCard title="Tavily" icon={Globe}>
              <ConfigRow
                label="Bật Tavily"
                value={<BoolBadge on={settings.web_search.enable_tavily} />}
              />
              <ConfigRow label="Max results" value={settings.web_search.tavily_max_results} />
              <ConfigRow label="Search depth" value={settings.web_search.tavily_search_depth} />
              <ConfigRow
                label="Include domains"
                value={
                  settings.web_search.tavily_include_domains.length
                    ? settings.web_search.tavily_include_domains.join(", ")
                    : "(tất cả)"
                }
              />
              <ConfigRow
                label="API key"
                value={
                  <ConfiguredBadge
                    configured={settings.web_search.tavily_api_key.configured}
                  />
                }
              />
            </SectionCard>

            <SectionCard title="PubMed / NCBI" icon={Search}>
              <ConfigRow
                label="Bật PubMed"
                value={<BoolBadge on={settings.web_search.enable_pubmed} />}
              />
              <ConfigRow label="Max results" value={settings.web_search.pubmed_max_results} />
              <ConfigRow
                label="Dùng NCBI E-utilities"
                value={<BoolBadge on={settings.web_search.pubmed_use_ncbi} />}
              />
              <ConfigRow
                label="Europe PMC fallback"
                value={<BoolBadge on={settings.web_search.pubmed_europepmc_fallback} />}
              />
              <ConfigRow
                label="Email"
                value={settings.web_search.pubmed_email || "—"}
              />
              <ConfigRow
                label="API key"
                value={
                  <ConfiguredBadge
                    configured={settings.web_search.pubmed_api_key.configured}
                  />
                }
              />
              <ConfigRow label="Context limit" value={settings.web_search.context_limit} />
            </SectionCard>
          </div>
        </TabsContent>

        <TabsContent value="guardrails">
          <div className="grid gap-6 lg:grid-cols-2">
            <SectionCard title="Trạng thái" icon={Shield}>
              <ConfigRow
                label="Input guardrails"
                value={<BoolBadge on={settings.guardrails.enable_input_guardrails} />}
              />
              <ConfigRow
                label="Output guardrails"
                value={<BoolBadge on={settings.guardrails.enable_output_guardrails} />}
              />
              <ConfigRow label="Model source" value={settings.guardrails.model_source} />
              <p className="mt-4 text-xs text-muted-foreground">
                Bật/tắt qua <code className="rounded bg-muted px-1">ENABLE_INPUT_GUARDRAILS</code>{" "}
                và <code className="rounded bg-muted px-1">ENABLE_OUTPUT_GUARDRAILS</code> trong
                .env — restart backend để áp dụng.
              </p>
            </SectionCard>

            <SectionCard title="Kiểm tra nội dung" icon={Shield}>
              <div className="mb-4">
                <p className="mb-2 text-xs font-medium uppercase tracking-widest text-muted-foreground">
                  Input
                </p>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {settings.guardrails.input_checks.map((c) => (
                    <li key={c} className="flex items-start gap-2">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-serene-accent" />
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-widest text-muted-foreground">
                  Output
                </p>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {settings.guardrails.output_checks.map((c) => (
                    <li key={c} className="flex items-start gap-2">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-serene-accent" />
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
            </SectionCard>
          </div>
        </TabsContent>

        <TabsContent value="usage">
          <div className="mb-4 flex items-center gap-2">
            {[7, 14, 30].map((d) => (
              <Button
                key={d}
                variant={usageDays === d ? "default" : "outline"}
                size="sm"
                onClick={() => setUsageDays(d)}
                className={usageDays === d ? "bg-serene-accent hover:bg-serene-accent/90" : ""}
              >
                {d} ngày
              </Button>
            ))}
          </div>

          {usagePending && !usage ? (
            <div className="flex justify-center py-16">
              <Loader2 className="h-8 w-8 animate-spin text-serene-accent" />
            </div>
          ) : usage ? (
            <>
              {!usage.available && (
                <div className="mb-6 rounded-2xl border border-amber-200/60 bg-amber-50/80 p-4 text-sm text-amber-950">
                  <p className="font-medium">Chưa kết nối OpenAI billing</p>
                  <p className="mt-1 text-muted-foreground">
                    {usage.message ||
                      "Thêm OPENAI_ADMIN_API_KEY (sk-admin-…) vào .env rồi restart backend."}
                  </p>
                </div>
              )}

              <p className="mb-4 text-xs text-muted-foreground">{usage.pricing_note}</p>

              <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-2xl border border-border/40 bg-white/70 p-5">
                  <p className="text-xs uppercase tracking-widest text-muted-foreground">
                    Tổng token ({usage.days} ngày)
                  </p>
                  <p className="mt-1 font-serif text-2xl italic text-serene-accent">
                    {formatNum(usage.period.total_tokens)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    In: {formatNum(usage.period.prompt_tokens)} · Out:{" "}
                    {formatNum(usage.period.completion_tokens)}
                  </p>
                </div>
                <div className="rounded-2xl border border-border/40 bg-white/70 p-5">
                  <p className="text-xs uppercase tracking-widest text-muted-foreground">
                    Chi phí thực tế
                  </p>
                  <p className="mt-1 font-serif text-2xl italic text-serene-accent">
                    {formatCost(usage.period.cost_usd)}
                  </p>
                </div>
                <div className="rounded-2xl border border-border/40 bg-white/70 p-5">
                  <p className="text-xs uppercase tracking-widest text-muted-foreground">
                    Requests
                  </p>
                  <p className="mt-1 font-serif text-2xl italic text-serene-accent">
                    {formatNum(usage.period.calls)}
                  </p>
                </div>
                <div className="rounded-2xl border border-border/40 bg-white/70 p-5">
                  <p className="text-xs uppercase tracking-widest text-muted-foreground">
                    Hôm nay
                  </p>
                  <p className="mt-1 font-serif text-2xl italic text-serene-accent">
                    {formatNum(usage.today.total_tokens)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatCost(usage.today.cost_usd)}
                  </p>
                </div>
              </div>

              {chartData.length > 0 && (
                <div className="rounded-2xl border border-border/40 bg-white/70 p-6">
                  <h4 className="mb-4 font-serif text-lg italic">Token theo ngày</h4>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={chartData}>
                      <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip
                        formatter={(value: number) => [formatNum(value), "Tokens"]}
                      />
                      <Bar dataKey="tokens" fill="#6b8f71" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </>
          ) : null}
        </TabsContent>
      </Tabs>
    </div>
  );
}
