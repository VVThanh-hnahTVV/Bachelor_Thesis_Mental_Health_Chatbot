"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { format, parseISO } from "date-fns";
import {
  Bolt,
  Database,
  FileText,
  Globe,
  Loader2,
  MoreVertical,
  RefreshCw,
  Trash2,
  Upload,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  type ArticleStatus,
  type IndexStats,
  type KnowledgeJob,
  type PdfFile,
  type StagedArticle,
  buildIndex,
  bulkArticles,
  deletePdf,
  deleteWebArticle,
  removePdfVectors,
  getIndexJob,
  getIndexStats,
  listArticles,
  listIndexJobs,
  listPdfFiles,
  patchArticle,
  runCrawl,
  triggerPdfIngest,
  uploadPdf,
} from "@/lib/api/admin-knowledge";

type Tab = "web" | "pdf" | "jobs";

const WEB_STATUSES: ArticleStatus[] = ["pending", "approved", "indexed"];

const STATUS_LABELS: Record<ArticleStatus, string> = {
  pending: "Chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Từ chối",
  indexed: "Đã lập chỉ mục",
};

const JOB_STATUS_LABELS: Record<string, string> = {
  running: "Đang chạy",
  done: "Hoàn tất",
  error: "Lỗi",
};

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTime(iso?: string | null) {
  if (!iso) return "—";
  try {
    return format(parseISO(iso), "HH:mm dd/MM/yyyy");
  } catch {
    return "—";
  }
}

function formatJobTitle(job: KnowledgeJob) {
  if (job.title) {
    return job.title
      .replace(/^PDF ingest: all files$/, "Nhúng PDF: tất cả tệp")
      .replace(/^PDF ingest: /, "Nhúng PDF: ")
      .replace(/^Web corpus index$/, "Lập chỉ mục corpus web")
      .replace(/^Web corpus index: (\d+) article\(s\)$/, "Lập chỉ mục: $1 bài");
  }
  return job.job_type === "pdf" ? "Nhúng PDF" : "Lập chỉ mục web";
}

type DeletePending =
  | {
      kind: "delete-web";
      article: StagedArticle;
      status: ArticleStatus;
    }
  | {
      kind: "delete-pdf";
      pdf: PdfFile;
    };

type IndexPending =
  | { kind: "bulk"; sourceIds: string[] }
  | { kind: "single"; sourceIds: string[]; sourceId: string };

function InlineConfirmPopover({
  open,
  message,
  confirmLabel,
  onCancel,
  onConfirm,
  busy,
  anchorRef,
  variant = "destructive",
}: {
  open: boolean;
  message: string;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void;
  busy?: boolean;
  anchorRef: React.RefObject<HTMLDivElement | null>;
  variant?: "destructive" | "primary";
}) {
  const [placement, setPlacement] = useState<"above" | "below">("below");

  useLayoutEffect(() => {
    if (!open || !anchorRef.current) return;
    const rect = anchorRef.current.getBoundingClientRect();
    const popoverHeight = 76;
    setPlacement(rect.top < popoverHeight + 12 ? "below" : "above");
  }, [open, anchorRef]);

  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 z-20" aria-hidden onClick={onCancel} />
      <div
        className={cn(
          "absolute right-0 z-30 w-44 rounded-md border border-border/50 bg-white p-2.5 shadow-md",
          placement === "above" ? "bottom-full mb-1.5" : "top-full mt-1.5"
        )}
      >
        <p className="text-xs leading-snug text-foreground">{message}</p>
        <div className="mt-2 flex justify-end gap-1.5">
          <button
            type="button"
            className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
            onClick={onCancel}
            disabled={busy}
          >
            Hủy
          </button>
          <button
            type="button"
            className={cn(
              "rounded px-2 py-1 text-xs text-white disabled:opacity-50",
              variant === "destructive"
                ? "bg-destructive hover:bg-destructive/90"
                : "bg-primary hover:bg-primary/90"
            )}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "..." : confirmLabel}
          </button>
        </div>
      </div>
    </>
  );
}

function webDeleteSuccessMessage(
  status: ArticleStatus,
  result: { action: string; points_deleted: number }
): string {
  if (status === "indexed" || result.action === "recycled") {
    return result.points_deleted > 0
      ? `Đã gỡ ${result.points_deleted} điểm vector và đưa bài về chờ duyệt`
      : "Đã đưa bài về chờ duyệt (không còn vector trong DB)";
  }
  return "Đã xóa bài và chặn crawl lại";
}

function jobSummary(job: KnowledgeJob) {
  if (job.status === "error") return job.error || "Lỗi";
  const r = job.result;
  if (!r) return job.progress?.title || "—";
  if (job.job_type === "pdf") {
    const docs = r.documents_ingested ?? r.chunks_processed;
    return `Hoàn tất • ${docs ?? 0} khối`;
  }
  return `Hoàn tất • ${r.chunks_indexed ?? 0} khối`;
}

export default function AdminKnowledgePage() {
  const [tab, setTab] = useState<Tab>("web");
  const [stats, setStats] = useState<IndexStats | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  // Web corpus
  const [webStatus, setWebStatus] = useState<ArticleStatus>("pending");
  const [articles, setArticles] = useState<StagedArticle[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // PDF corpus
  const [pdfs, setPdfs] = useState<PdfFile[]>([]);
  const [pdfMenu, setPdfMenu] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Jobs
  const [jobs, setJobs] = useState<KnowledgeJob[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const [deletePending, setDeletePending] = useState<DeletePending | null>(
    null
  );
  const [indexPending, setIndexPending] = useState<IndexPending | null>(null);
  const confirmAnchorRef = useRef<HTMLDivElement | null>(null);

  const loadStats = useCallback(async () => {
    setStats(await getIndexStats());
  }, []);

  const loadWeb = useCallback(async () => {
    const res = await listArticles(webStatus);
    setArticles(res.articles || []);
    setSelected(new Set());
  }, [webStatus]);

  const loadPdfs = useCallback(async () => {
    const res = await listPdfFiles();
    setPdfs(res.files || []);
  }, []);

  const loadJobs = useCallback(async () => {
    const res = await listIndexJobs();
    setJobs(res.jobs || []);
  }, []);

  const loadAll = useCallback(async () => {
    await Promise.all([loadStats(), loadWeb(), loadPdfs(), loadJobs()]);
  }, [loadStats, loadWeb, loadPdfs, loadJobs]);

  useEffect(() => {
    void loadAll().catch((err) =>
      setMessage(err instanceof Error ? err.message : "Không tải được dữ liệu")
    );
  }, [loadAll]);

  useEffect(() => {
    void loadWeb().catch(() => undefined);
  }, [loadWeb]);

  useEffect(() => {
    if (!activeJobId) return;
    const timer = setInterval(async () => {
      try {
        const job = await getIndexJob(activeJobId);
        setJobs((prev) => {
          const rest = prev.filter((j) => j.job_id !== job.job_id);
          return [job, ...rest];
        });
        if (job.status === "done" || job.status === "error") {
          clearInterval(timer);
          setActiveJobId(null);
          setBusy(false);
          setMessage(jobSummary(job));
          void loadAll();
        }
      } catch {
        clearInterval(timer);
        setBusy(false);
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [activeJobId, loadAll]);

  const startJob = async (fn: () => Promise<{ job_id: string }>) => {
    setBusy(true);
    setMessage("");
    try {
      const res = await fn();
      setActiveJobId(res.job_id);
      setTab("jobs");
      await loadJobs();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Tác vụ thất bại");
      setBusy(false);
    }
  };

  const handleCrawl = async () => {
    setBusy(true);
    try {
      const res = await runCrawl();
      setMessage(`Thu thập: +${res.added_to_pending} bài chờ duyệt`);
      setWebStatus("pending");
      await loadWeb();
      await loadStats();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Thu thập thất bại");
    } finally {
      setBusy(false);
    }
  };

  const handleConfirmIndex = () => {
    if (!indexPending) return;
    const ids = [...indexPending.sourceIds];
    setIndexPending(null);
    void startJob(() => buildIndex(ids));
  };

  const handleConfirmDelete = async () => {
    if (!deletePending) return;
    setBusy(true);
    try {
      if (deletePending.kind === "delete-web") {
        const { article, status } = deletePending;
        const res = await deleteWebArticle(article.source_id);
        setMessage(webDeleteSuccessMessage(status, res));
        if (res.action === "recycled") {
          setWebStatus("pending");
        }
        await Promise.all([loadWeb(), loadStats()]);
      } else {
        const { pdf } = deletePending;
        const res = await deletePdf(pdf.path);
        setMessage(
          res.vectors_removed
            ? `Đã xóa tệp và gỡ ${res.vectors_removed} điểm vector`
            : "Đã xóa tệp PDF"
        );
        await Promise.all([loadPdfs(), loadStats()]);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Thao tác thất bại");
    } finally {
      setBusy(false);
      setDeletePending(null);
      setPdfMenu(null);
    }
  };

  const handleBulk = async (action: "approve" | "reject") => {
    if (!selected.size) return;
    setBusy(true);
    try {
      await bulkArticles([...selected], action);
      await loadStats();
      if (action === "approve") {
        setWebStatus("approved");
        setMessage(
          `Đã duyệt ${selected.size} bài — bấm "Tạo chỉ mục web" để đưa vào vector DB`
        );
      } else {
        await loadWeb();
        setMessage(`Đã từ chối ${selected.size} bài`);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Thao tác hàng loạt thất bại");
    } finally {
      setBusy(false);
    }
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true);
    try {
      for (const file of Array.from(files)) {
        await uploadPdf(file);
      }
      setMessage(`Đã tải lên ${files.length} PDF`);
      await loadPdfs();
      await loadStats();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Tải lên thất bại");
    } finally {
      setBusy(false);
    }
  };

  const totalPoints =
    (stats?.web_collection_points ?? 0) + (stats?.pdf_collection_points ?? 0);

  const pendingJobs = jobs.filter((j) => j.status === "running").length;

  return (
    <div className="px-12 pb-20 pt-8">
      {/* Hero */}
      <div className="mb-10 flex items-end justify-between">
        <div className="max-w-2xl">
          <h2 className="mb-2 font-serif text-3xl italic leading-tight tracking-tight text-serene-accent">
            Quản lý tri thức & cơ sở vector
          </h2>
          <p className="max-w-xl text-muted-foreground">
            Thu thập bài web, quản lý PDF y khoa và điều phối quy trình nhúng
            vector Qdrant cho hệ thống RAG.
          </p>
        </div>
        <div className="text-right">
          <div className="font-serif text-3xl italic">
            {totalPoints.toLocaleString("vi-VN")}
          </div>
          <div className="text-xs uppercase tracking-widest text-muted-foreground">
            Điểm Qdrant
          </div>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="mb-10 grid grid-cols-2 gap-4 md:grid-cols-4">
          {[
            {
              label: "Kho PDF",
              value: stats.pdf_files_count,
              suffix: "tệp",
              border: "border-serene-accent/40",
            },
            {
              label: "Web chờ duyệt",
              value: stats.staging.pending ?? 0,
              suffix: "bài",
              border: "border-destructive/30",
            },
            {
              label: "Vector web",
              value: stats.web_collection_points ?? 0,
              suffix: "điểm",
              border: "border-serene-green/40",
            },
            {
              label: "Tác vụ lập chỉ mục",
              value: pendingJobs,
              suffix: "đang chạy",
              border: "border-amber-500/30",
            },
          ].map((s) => (
            <div
              key={s.label}
              className={cn(
                "rounded-xl border-l-4 bg-[#f4f4ef] p-6",
                s.border
              )}
            >
              <p className="mb-2 text-xs uppercase tracking-widest text-muted-foreground">
                {s.label}
              </p>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold">
                  {s.value.toLocaleString("vi-VN")}
                </span>
                <span className="text-sm opacity-60">{s.suffix}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {message && (
        <p className="mb-4 text-sm text-foreground">{message}</p>
      )}

      <div className="grid grid-cols-12 gap-10">
        {/* Main */}
        <div className="col-span-12 lg:col-span-8">
          {/* Tabs */}
          <div className="relative mb-8 flex gap-8 border-b border-border/30">
            {(
              [
                ["web", "Tri thức web"],
                ["pdf", "PDF y khoa"],
                ["jobs", "Tác vụ lập chỉ mục"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setTab(id)}
                className={cn(
                  "relative pb-4 text-sm font-medium transition-colors",
                  tab === id
                    ? "font-bold text-serene-accent"
                    : "text-muted-foreground hover:text-serene-accent"
                )}
              >
                {label}
                {tab === id && (
                  <span className="absolute bottom-0 left-0 h-0.5 w-full bg-serene-accent" />
                )}
              </button>
            ))}
            <div className="ml-auto flex gap-2 pb-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => void loadAll()}
                disabled={busy}
              >
                <RefreshCw className="mr-1 h-4 w-4" />
                Làm mới
              </Button>
            </div>
          </div>

          {/* Web tab */}
          {tab === "web" && (
            <div className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="font-serif text-xl italic">Bài viết web</h3>
                <Button size="sm" onClick={() => void handleCrawl()} disabled={busy}>
                  <Globe className="mr-1 h-4 w-4" />
                  Thu thập mới
                </Button>
              </div>

              <div className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {WEB_STATUSES.map((s) => (
                  <Button
                    key={s}
                    size="sm"
                    variant={webStatus === s ? "default" : "outline"}
                    onClick={() => setWebStatus(s)}
                  >
                    {STATUS_LABELS[s]} ({stats?.staging[s] ?? 0})
                  </Button>
                ))}
                {webStatus === "pending" && selected.size > 0 && (
                  <>
                    <Button size="sm" onClick={() => void handleBulk("approve")} disabled={busy}>
                      Duyệt ({selected.size})
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => void handleBulk("reject")} disabled={busy}>
                      Từ chối ({selected.size})
                    </Button>
                  </>
                )}
              </div>
              {webStatus === "approved" && (
                <div
                  className="relative flex justify-end"
                  ref={(node) => {
                    if (indexPending?.kind === "bulk") {
                      confirmAnchorRef.current = node;
                    }
                  }}
                >
                  <InlineConfirmPopover
                    open={indexPending?.kind === "bulk"}
                    message="Bạn có chắc tạo chỉ mục cho các bài đã chọn?"
                    confirmLabel="Tạo chỉ mục"
                    variant="primary"
                    anchorRef={confirmAnchorRef}
                    onCancel={() => setIndexPending(null)}
                    onConfirm={handleConfirmIndex}
                    busy={busy}
                  />
                  <Button
                    size="sm"
                    disabled={busy || selected.size === 0}
                    onClick={() => {
                      setDeletePending(null);
                      setIndexPending({
                        kind: "bulk",
                        sourceIds: [...selected],
                      });
                    }}
                  >
                    <Database className="mr-1 h-4 w-4" />
                    Tạo chỉ mục cho bài đã chọn
                    {selected.size > 0 ? ` (${selected.size})` : ""}
                  </Button>
                </div>
              )}
              </div>

              <div className="overflow-visible rounded-xl bg-white p-6 shadow-sm">
                {articles.length === 0 ? (
                  <p className="py-8 text-center text-muted-foreground">
                    Không có bài trong trạng thái {STATUS_LABELS[webStatus]}.
                  </p>
                ) : (
                  <div className="space-y-4">
                    {articles.map((article) => (
                      <div
                        key={article.source_id}
                        className="flex items-start gap-3 border-b border-border/20 pb-4 last:border-0"
                      >
                        {(webStatus === "pending" || webStatus === "approved") && (
                          <input
                            type="checkbox"
                            className="mt-1"
                            checked={selected.has(article.source_id)}
                            onChange={() =>
                              setSelected((prev) => {
                                const next = new Set(prev);
                                if (next.has(article.source_id))
                                  next.delete(article.source_id);
                                else next.add(article.source_id);
                                return next;
                              })
                            }
                          />
                        )}
                        <div className="min-w-0 flex-1">
                          <a
                            href={article.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-medium hover:underline"
                          >
                            {article.title}
                          </a>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {article.publisher} · điểm {article.relevance_score}
                          </p>
                        </div>
                        <div className="flex shrink-0 gap-1">
                          {webStatus === "pending" && (
                            <Button
                              size="sm"
                              disabled={busy}
                              onClick={() => {
                                setBusy(true);
                                void patchArticle(article.source_id, {
                                  action: "approve",
                                })
                                  .then(async () => {
                                    setWebStatus("approved");
                                    setMessage(
                                      "Đã duyệt — bấm \"Tạo chỉ mục\" để đưa vào vector DB"
                                    );
                                    await loadStats();
                                  })
                                  .finally(() => setBusy(false));
                              }}
                            >
                              Duyệt
                            </Button>
                          )}
                          {webStatus === "approved" && (
                            <div
                              className="relative"
                              ref={(node) => {
                                const isOpen =
                                  indexPending?.kind === "single" &&
                                  indexPending.sourceId === article.source_id;
                                if (isOpen) confirmAnchorRef.current = node;
                              }}
                            >
                              <InlineConfirmPopover
                                open={
                                  indexPending?.kind === "single" &&
                                  indexPending.sourceId === article.source_id
                                }
                                message="Bạn có chắc tạo chỉ mục cho bài này?"
                                confirmLabel="Tạo chỉ mục"
                                variant="primary"
                                anchorRef={confirmAnchorRef}
                                onCancel={() => setIndexPending(null)}
                                onConfirm={handleConfirmIndex}
                                busy={busy}
                              />
                              <Button
                                size="sm"
                                disabled={busy}
                                onClick={() => {
                                  setDeletePending(null);
                                  setIndexPending({
                                    kind: "single",
                                    sourceIds: [article.source_id],
                                    sourceId: article.source_id,
                                  });
                                }}
                              >
                                <Database className="mr-1 h-3.5 w-3.5" />
                                Tạo chỉ mục
                              </Button>
                            </div>
                          )}
                          <div
                            className="relative"
                            ref={(node) => {
                              const isOpen =
                                deletePending?.kind === "delete-web" &&
                                deletePending.article.source_id ===
                                  article.source_id;
                              if (isOpen) confirmAnchorRef.current = node;
                            }}
                          >
                            <InlineConfirmPopover
                              open={
                                deletePending?.kind === "delete-web" &&
                                deletePending.article.source_id ===
                                  article.source_id
                              }
                              message="Bạn có chắc xóa tài liệu?"
                              confirmLabel="Xóa"
                              variant="destructive"
                              anchorRef={confirmAnchorRef}
                              onCancel={() => setDeletePending(null)}
                              onConfirm={() => void handleConfirmDelete()}
                              busy={busy}
                            />
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={busy}
                              className="text-destructive hover:text-destructive"
                              onClick={() => {
                                setIndexPending(null);
                                setDeletePending({
                                  kind: "delete-web",
                                  article,
                                  status: webStatus,
                                });
                              }}
                            >
                              <Trash2 className="mr-1 h-3.5 w-3.5" />
                              Xóa
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* PDF tab */}
          {tab === "pdf" && (
            <div className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="font-serif text-xl italic">PDF y khoa</h3>
                <Button
                  size="sm"
                  disabled={busy || pdfs.length === 0}
                  onClick={() => void startJob(() => triggerPdfIngest())}
                >
                  <Bolt className="mr-1 h-4 w-4" />
                  Nhúng tất cả
                </Button>
              </div>

              <div className="overflow-hidden rounded-xl bg-white shadow-sm">
                <table className="w-full text-left">
                  <thead className="border-b border-border/20 bg-[#f4f4ef]">
                    <tr>
                      {["Tài liệu", "Kích thước", "Cập nhật", ""].map((h) => (
                        <th
                          key={h}
                          className="px-6 py-4 text-xs font-normal uppercase tracking-widest text-muted-foreground"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/10">
                    {pdfs.length === 0 && (
                      <tr>
                        <td
                          colSpan={4}
                          className="px-6 py-12 text-center text-muted-foreground"
                        >
                          Chưa có PDF. Tải lên từ panel bên phải.
                        </td>
                      </tr>
                    )}
                    {pdfs.map((pdf) => (
                      <tr key={pdf.path} className="group hover:bg-[#f4f4ef]/60">
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-3">
                            <FileText className="h-5 w-5 text-red-800/70" />
                            <div>
                              <p className="font-bold">{pdf.name}</p>
                              <p className="text-[10px] opacity-40">
                                {stats?.raw_documents_dir}/{pdf.path}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-sm text-muted-foreground">
                          {formatBytes(pdf.size_bytes)}
                        </td>
                        <td className="px-6 py-4 text-sm text-muted-foreground">
                          {formatTime(pdf.modified_at)}
                        </td>
                        <td className="relative px-6 py-4 text-right">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() =>
                              setPdfMenu(pdfMenu === pdf.path ? null : pdf.path)
                            }
                          >
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                          {pdfMenu === pdf.path && (
                            <>
                              <div
                                className="fixed inset-0 z-10"
                                onClick={() => setPdfMenu(null)}
                              />
                              <div className="absolute right-6 top-12 z-20 min-w-[150px] rounded-lg border bg-white py-1 shadow-lg">
                                <button
                                  type="button"
                                  className="flex w-full items-center gap-2 px-4 py-2 text-sm hover:bg-muted"
                                  onClick={() => {
                                    setPdfMenu(null);
                                    void startJob(() =>
                                      triggerPdfIngest(pdf.path)
                                    );
                                  }}
                                >
                                  <Zap className="h-3.5 w-3.5" />
                                  Nhúng
                                </button>
                                <button
                                  type="button"
                                  className="flex w-full items-center gap-2 px-4 py-2 text-sm hover:bg-muted"
                                  onClick={() => {
                                    setPdfMenu(null);
                                    setBusy(true);
                                    void removePdfVectors(pdf.path)
                                      .then((res) => {
                                        setMessage(
                                          res.points_deleted > 0
                                            ? `Đã gỡ ${res.points_deleted} điểm vector khỏi ${pdf.name}`
                                            : `Không tìm thấy vector cho ${pdf.name}`
                                        );
                                        return loadStats();
                                      })
                                      .catch((e) => setMessage(e.message))
                                      .finally(() => setBusy(false));
                                  }}
                                >
                                  <Database className="h-3.5 w-3.5" />
                                  Gỡ khỏi vector DB
                                </button>
                                <div
                                  className="relative"
                                  ref={(node) => {
                                    const isOpen =
                                      deletePending?.kind === "delete-pdf" &&
                                      deletePending.pdf.path === pdf.path;
                                    if (isOpen) confirmAnchorRef.current = node;
                                  }}
                                >
                                  <InlineConfirmPopover
                                    open={
                                      deletePending?.kind === "delete-pdf" &&
                                      deletePending.pdf.path === pdf.path
                                    }
                                    message="Bạn có chắc xóa tài liệu?"
                                    confirmLabel="Xóa"
                                    variant="destructive"
                                    anchorRef={confirmAnchorRef}
                                    onCancel={() => setDeletePending(null)}
                                    onConfirm={() => void handleConfirmDelete()}
                                    busy={busy}
                                  />
                                  <button
                                    type="button"
                                    className="flex w-full items-center gap-2 px-4 py-2 text-sm text-destructive hover:bg-muted"
                                    onClick={() => {
                                      setIndexPending(null);
                                      setDeletePending({
                                        kind: "delete-pdf",
                                        pdf,
                                      });
                                    }}
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                    Xóa tệp
                                  </button>
                                </div>
                              </div>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Jobs tab */}
          {tab === "jobs" && (
            <div className="space-y-4">
              <h3 className="font-serif text-xl italic">Quy trình vector hóa</h3>
              {jobs.length === 0 ? (
                <p className="py-8 text-muted-foreground">Chưa có tác vụ nào.</p>
              ) : (
                jobs.map((job) => (
                  <div
                    key={job.job_id}
                    className={cn(
                      "flex items-center justify-between rounded-lg bg-[#f4f4ef] p-4",
                      job.status === "error" && "border border-destructive/20"
                    )}
                  >
                    <div className="flex items-center gap-4">
                      <div
                        className={cn(
                          "h-2 w-2 rounded-full",
                          job.status === "running" && "animate-pulse bg-serene-accent",
                          job.status === "done" && "bg-serene-accent",
                          job.status === "error" && "bg-destructive"
                        )}
                      />
                      <div>
                        <p className="font-bold">
                          {formatJobTitle(job)}
                        </p>
                        <p className="text-[10px] text-muted-foreground">
                          {jobSummary(job)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <span
                        className={cn(
                          "rounded px-3 py-1 text-xs font-semibold uppercase tracking-tight",
                          job.status === "done" &&
                            "bg-serene-green/15 text-serene-accent",
                          job.status === "running" &&
                            "bg-amber-500/15 text-amber-700",
                          job.status === "error" &&
                            "bg-destructive/10 text-destructive"
                        )}
                      >
                        {JOB_STATUS_LABELS[job.status] ?? job.status}
                      </span>
                      <span className="text-sm text-muted-foreground">
                        {formatTime(job.started_at)}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="col-span-12 space-y-6 lg:col-span-4">
          <div
            className="flex cursor-pointer flex-col items-center rounded-xl border-2 border-dashed border-serene-green/30 bg-serene-green/5 p-8 text-center transition-colors hover:bg-serene-green/10"
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) =>
              e.key === "Enter" && fileInputRef.current?.click()
            }
            role="button"
            tabIndex={0}
          >
            <div className="mb-4 rounded-full bg-serene-green/15 p-4 text-serene-accent">
              <Upload className="h-8 w-8" />
            </div>
            <h4 className="mb-2 font-serif text-lg italic">Tải lên PDF</h4>
            <p className="text-sm text-muted-foreground">
              Kéo thả hoặc chọn file PDF y khoa
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              multiple
              className="hidden"
              onChange={(e) => void handleUpload(e.target.files)}
            />
          </div>

          <div className="relative overflow-hidden rounded-xl bg-[#e9e8e4] p-8">
            <h4 className="mb-6 text-xs font-bold uppercase tracking-widest opacity-60">
              Hệ vector
            </h4>
            <div className="space-y-4 text-sm">
              <div className="flex justify-between border-b border-border/20 py-2">
                <span>Bộ sưu tập web</span>
                <span className="font-bold">{stats?.web_collection}</span>
              </div>
              <div className="flex justify-between border-b border-border/20 py-2">
                <span>Điểm web</span>
                <span className="font-bold">
                  {stats?.web_collection_points?.toLocaleString("vi-VN") ?? 0}
                </span>
              </div>
              <div className="flex justify-between border-b border-border/20 py-2">
                <span>Bộ sưu tập PDF</span>
                <span className="font-bold">{stats?.pdf_collection}</span>
              </div>
              <div className="flex justify-between py-2">
                <span>Điểm PDF</span>
                <span className="font-bold">
                  {stats?.pdf_collection_points?.toLocaleString("vi-VN") ?? 0}
                </span>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-border/30 p-6">
            <h4 className="mb-3 text-sm font-bold text-serene-accent">
              Cấu hình quy trình
            </h4>
            <p className="text-sm italic text-muted-foreground">
              Mô hình nhúng:{" "}
              <span className="font-bold not-italic">
                {stats?.embedding_provider ?? "—"}
              </span>
              . Khối{" "}
              <span className="font-bold not-italic">
                {stats?.chunk_size ?? 512}
              </span>{" "}
              từ, chồng lấn{" "}
              <span className="font-bold not-italic">
                {stats?.chunk_overlap ?? 50}
              </span>
              .
            </p>
          </div>
        </div>
      </div>

      {busy && (
        <div className="fixed bottom-8 right-8 rounded-full bg-white p-3 shadow-lg">
          <Loader2 className="h-6 w-6 animate-spin text-serene-accent" />
        </div>
      )}
    </div>
  );
}
