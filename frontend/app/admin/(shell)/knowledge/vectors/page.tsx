"use client";

import { useCallback, useEffect, useState } from "react";
import { Database, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  buildIndex,
  getIndexJob,
  getIndexStats,
  type IndexStats,
} from "@/lib/api/admin-knowledge";

export default function AdminVectorsPage() {
  const [stats, setStats] = useState<IndexStats | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [indexJobId, setIndexJobId] = useState<string | null>(null);
  const [indexProgress, setIndexProgress] = useState("");

  const load = useCallback(async () => {
    const statsRes = await getIndexStats();
    setStats(statsRes);
  }, []);

  useEffect(() => {
    void load().catch((err) =>
      setMessage(err instanceof Error ? err.message : "Load failed")
    );
  }, [load]);

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

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-12 py-8">
      <div>
        <h1 className="font-serif text-3xl italic">Vector DB — Web Corpus</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Nhúng bài viết đã duyệt vào Qdrant để RAG web search sử dụng.
        </p>
      </div>

      {stats && (
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Collection</CardTitle>
            </CardHeader>
            <CardContent>
              <code className="text-sm">{stats.web_collection}</code>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Vector points</CardTitle>
            </CardHeader>
            <CardContent className="text-3xl font-bold text-serene-accent">
              {stats.web_collection_points?.toLocaleString("vi-VN") ?? 0}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Bài đã duyệt (chưa index)</CardTitle>
            </CardHeader>
            <CardContent className="text-3xl font-bold">
              {stats.staging.approved ?? 0}
            </CardContent>
          </Card>
        </div>
      )}

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">Tạo / cập nhật index</CardTitle>
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={handleBuildIndex}
              disabled={busy || (stats?.staging?.approved ?? 0) === 0}
              size="sm"
            >
              <Database className="mr-1 h-4 w-4" />
              Build Vector Index
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
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            Chỉ các bài ở trạng thái <strong>approved</strong> mới được nhúng.
            Sau khi index thành công, trạng thái chuyển sang{" "}
            <strong>indexed</strong>.
          </p>
          {indexProgress && (
            <p className="text-foreground">{indexProgress}</p>
          )}
          {message && <p className="text-foreground">{message}</p>}
        </CardContent>
      </Card>

      {stats && (
        <div className="grid gap-4 md:grid-cols-4">
          {(["pending", "approved", "rejected", "indexed"] as const).map(
            (s) => (
              <Card key={s}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm capitalize">{s}</CardTitle>
                </CardHeader>
                <CardContent className="text-xl font-bold">
                  {stats.staging[s] ?? 0}
                </CardContent>
              </Card>
            )
          )}
        </div>
      )}

      {busy && !indexJobId && (
        <div className="flex justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-serene-accent" />
        </div>
      )}
    </div>
  );
}
