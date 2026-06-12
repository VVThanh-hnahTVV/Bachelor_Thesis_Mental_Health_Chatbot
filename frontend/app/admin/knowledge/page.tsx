"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Loader2, RefreshCw, Database, Globe } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Container } from "@/components/ui/container";
import { useSession } from "@/lib/contexts/session-context";
import {
  type ArticleStatus,
  type IndexStats,
  type StagedArticle,
  buildIndex,
  bulkArticles,
  getIndexJob,
  getIndexStats,
  listArticles,
  patchArticle,
  runCrawl,
} from "@/lib/api/admin-knowledge";

const STATUSES: ArticleStatus[] = ["pending", "approved", "rejected", "indexed"];

export default function AdminKnowledgePage() {
  const router = useRouter();
  const { user, loading, isAuthenticated } = useSession();
  const [status, setStatus] = useState<ArticleStatus>("pending");
  const [articles, setArticles] = useState<StagedArticle[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [stats, setStats] = useState<IndexStats | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [indexJobId, setIndexJobId] = useState<string | null>(null);
  const [indexProgress, setIndexProgress] = useState("");

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
    if (loading) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    if (user?.role !== "admin") {
      router.replace("/dashboard");
      return;
    }
    void load().catch((err) =>
      setMessage(err instanceof Error ? err.message : "Load failed")
    );
  }, [loading, isAuthenticated, user, router, load]);

  useEffect(() => {
    if (!indexJobId) return;
    const timer = setInterval(async () => {
      try {
        const job = await getIndexJob(indexJobId);
        const prog = job.progress || {};
        setIndexProgress(
          `${job.status}: ${prog.title || ""} (${prog.current || 0}/${prog.total || 0})`
        );
        if (job.status === "done" || job.status === "error") {
          clearInterval(timer);
          setIndexJobId(null);
          setBusy(false);
          if (job.result) {
            setMessage(
              `Indexed ${job.result.indexed_articles} articles, ${job.result.chunks_indexed} chunks`
            );
          } else if (job.error) {
            setMessage(job.error);
          }
          void load();
        }
      } catch {
        clearInterval(timer);
        setBusy(false);
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [indexJobId, load]);

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
      const old = res.skipped_too_old ? `, skipped ${res.skipped_too_old} old links` : "";
      setMessage(`Crawl done: ${res.added_to_pending} new in pending${extra}${old}`);
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

  const handleBuildIndex = async () => {
    setBusy(true);
    setMessage("");
    try {
      const res = await buildIndex();
      setIndexJobId(res.job_id);
      setIndexProgress("running...");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Index failed");
      setBusy(false);
    }
  };

  if (loading || user?.role !== "admin") {
    return (
      <Container className="py-16 flex justify-center">
        <Loader2 className="h-8 w-8 animate-spin" />
      </Container>
    );
  }

  return (
    <Container className="py-8 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Admin — Knowledge Corpus</h1>
          <p className="text-muted-foreground text-sm">
            Crawl mental-health news, review, then build Qdrant web index.
          </p>
        </div>
        <Button variant="outline" asChild>
          <Link href="/dashboard">Back to dashboard</Link>
        </Button>
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
          <CardTitle className="text-base">Actions</CardTitle>
          <div className="flex flex-wrap gap-2">
            <Button onClick={handleCrawl} disabled={busy} size="sm">
              <Globe className="h-4 w-4 mr-1" />
              Crawl mới
            </Button>
            <Button
              onClick={handleBuildIndex}
              disabled={busy || (stats?.staging?.approved ?? 0) === 0}
              size="sm"
              variant="default"
            >
              <Database className="h-4 w-4 mr-1" />
              Tạo Vector DB
            </Button>
            <Button onClick={() => void load()} disabled={busy} size="sm" variant="outline">
              <RefreshCw className="h-4 w-4 mr-1" />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-1">
          {stats && (
            <p>
              Web collection <code>{stats.web_collection}</code>:{" "}
              {stats.web_collection_points ?? 0} points
            </p>
          )}
          {indexProgress && <p>{indexProgress}</p>}
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
            <Button size="sm" onClick={() => void handleBulk("approve")} disabled={busy}>
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
          <p className="text-muted-foreground text-sm">No articles in {status}.</p>
        )}
        {articles.map((article) => (
          <Card key={article.source_id}>
            <CardContent className="pt-4 space-y-2">
              <div className="flex items-start gap-3">
                {status === "pending" && (
                  <input
                    type="checkbox"
                    checked={selected.has(article.source_id)}
                    onChange={() => toggleSelect(article.source_id)}
                    className="mt-1"
                  />
                )}
                <div className="flex-1 min-w-0">
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium hover:underline line-clamp-2"
                  >
                    {article.title}
                  </a>
                  <p className="text-xs text-muted-foreground mt-1">
                    {article.publisher} · {article.language}
                    {article.content_type === "research_article" ? " · nghiên cứu" : ""}
                    {" · "}score {article.relevance_score} ·{" "}
                    {article.matched_keywords?.join(", ")}
                  </p>
                  {article.preview && (
                    <p className="text-sm text-muted-foreground mt-2 line-clamp-3">
                      {article.preview}
                    </p>
                  )}
                </div>
                {status === "pending" && (
                  <div className="flex gap-1 shrink-0">
                    <Button
                      size="sm"
                      onClick={() => void handleSingle(article.source_id, "approve")}
                      disabled={busy}
                    >
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void handleSingle(article.source_id, "reject")}
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
    </Container>
  );
}
