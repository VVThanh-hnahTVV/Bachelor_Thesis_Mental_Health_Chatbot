"use client";

import { useCallback, useEffect, useState } from "react";
import { Globe, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type ArticleStatus,
  type IndexStats,
  type StagedArticle,
  bulkArticles,
  getIndexStats,
  listArticles,
  patchArticle,
  runCrawl,
} from "@/lib/api/admin-knowledge";

const STATUSES: ArticleStatus[] = ["pending", "approved", "rejected", "indexed"];

export default function AdminKnowledgePage() {
  const [status, setStatus] = useState<ArticleStatus>("pending");
  const [articles, setArticles] = useState<StagedArticle[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [stats, setStats] = useState<IndexStats | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    const [listRes, statsRes] = await Promise.all([
      listArticles(status),
      getIndexStats(),
    ]);
    setArticles(listRes.articles || []);
    setStats(statsRes);
    setSelected(new Set());
  }, [status]);

  useEffect(() => {
    void load().catch((err) =>
      setMessage(err instanceof Error ? err.message : "Load failed")
    );
  }, [load]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleCrawl = async () => {
    setBusy(true);
    setMessage("");
    try {
      const res = await runCrawl();
      const extras: string[] = [];
      if (res.site_added) extras.push(`${res.site_added} WHO/Vinmec`);
      if (res.research_added) extras.push(`${res.research_added} research`);
      const extra = extras.length ? ` (${extras.join(", ")})` : "";
      const old = res.skipped_too_old
        ? `, skipped ${res.skipped_too_old} old links`
        : "";
      setMessage(
        `Crawl done: ${res.added_to_pending} new in pending${extra}${old}`
      );
      setStatus("pending");
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Crawl failed");
    } finally {
      setBusy(false);
    }
  };

  const handleBulk = async (action: "approve" | "reject") => {
    if (selected.size === 0) return;
    setBusy(true);
    try {
      await bulkArticles([...selected], action);
      await load();
      setMessage(`${action}d ${selected.size} article(s)`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Bulk action failed");
    } finally {
      setBusy(false);
    }
  };

  const handleSingle = async (id: string, action: "approve" | "reject") => {
    setBusy(true);
    try {
      await patchArticle(id, { action });
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-12 py-8">
      <div>
        <h1 className="font-serif text-3xl italic">Tri thức — Crawl & Duyệt</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Thu thập và duyệt bài viết sức khỏe tâm thần. Tạo vector index tại
          trang Vector DB.
        </p>
      </div>

      {stats && (
        <div className="grid gap-4 md:grid-cols-5">
          {STATUSES.map((s) => (
            <Card key={s}>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm capitalize">{s}</CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-bold">
                {stats.staging[s] ?? 0}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">Thao tác</CardTitle>
          <div className="flex flex-wrap gap-2">
            <Button onClick={handleCrawl} disabled={busy} size="sm">
              <Globe className="mr-1 h-4 w-4" />
              Crawl mới
            </Button>
            <Button
              onClick={() => void load()}
              disabled={busy}
              size="sm"
              variant="outline"
            >
              <RefreshCw className="mr-1 h-4 w-4" />
              Làm mới
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-1 text-sm text-muted-foreground">
          {message && <p className="text-foreground">{message}</p>}
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2">
        {STATUSES.map((s) => (
          <Button
            key={s}
            size="sm"
            variant={status === s ? "default" : "outline"}
            onClick={() => setStatus(s)}
          >
            {s}
          </Button>
        ))}
        {status === "pending" && selected.size > 0 && (
          <>
            <Button
              size="sm"
              onClick={() => void handleBulk("approve")}
              disabled={busy}
            >
              Approve ({selected.size})
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => void handleBulk("reject")}
              disabled={busy}
            >
              Reject ({selected.size})
            </Button>
          </>
        )}
      </div>

      <div className="space-y-3">
        {articles.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No articles in {status}.
          </p>
        )}
        {articles.map((article) => (
          <Card key={article.source_id}>
            <CardContent className="space-y-2 pt-4">
              <div className="flex items-start gap-3">
                {status === "pending" && (
                  <input
                    type="checkbox"
                    checked={selected.has(article.source_id)}
                    onChange={() => toggleSelect(article.source_id)}
                    className="mt-1"
                  />
                )}
                <div className="min-w-0 flex-1">
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="line-clamp-2 font-medium hover:underline"
                  >
                    {article.title}
                  </a>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {article.publisher} · {article.language}
                    {article.content_type === "research_article"
                      ? " · nghiên cứu"
                      : ""}
                    {" · "}score {article.relevance_score} ·{" "}
                    {article.matched_keywords?.join(", ")}
                  </p>
                  {article.preview && (
                    <p className="mt-2 line-clamp-3 text-sm text-muted-foreground">
                      {article.preview}
                    </p>
                  )}
                </div>
                {status === "pending" && (
                  <div className="flex shrink-0 gap-1">
                    <Button
                      size="sm"
                      onClick={() =>
                        void handleSingle(article.source_id, "approve")
                      }
                      disabled={busy}
                    >
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        void handleSingle(article.source_id, "reject")
                      }
                      disabled={busy}
                    >
                      Reject
                    </Button>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {busy && (
        <div className="fixed bottom-8 right-8">
          <Loader2 className="h-6 w-6 animate-spin text-serene-accent" />
        </div>
      )}
    </div>
  );
}
