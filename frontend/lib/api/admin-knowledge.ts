import { getAuthToken } from "@/lib/auth-token";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export type ArticleStatus = "pending" | "approved" | "rejected" | "indexed";

export interface StagedArticle {
  source_id: string;
  title: string;
  url: string;
  publisher: string;
  language: string;
  content_type?: string;
  relevance_score: number;
  matched_keywords: string[];
  fetched_at?: string;
  preview?: string;
  status?: string;
}

export interface CrawlRunResult {
  success: boolean;
  added_to_pending: number;
  site_added?: number;
  research_added?: number;
  skipped_too_old?: number;
  skipped_duplicate?: number;
  skipped_filter?: number;
  errors?: string[];
}

export interface IndexStats {
  staging: Record<string, number>;
  web_collection_points: number | null;
  web_collection: string;
  pdf_collection_points: number | null;
  pdf_collection: string;
  pdf_files_count: number;
  raw_documents_dir: string;
  chunk_size: number;
  chunk_overlap: number;
  embedding_provider: string;
}

export interface PdfFile {
  name: string;
  path: string;
  size_bytes: number;
  modified_at: string | null;
}

export interface KnowledgeJob {
  job_id: string;
  job_type?: "web" | "pdf";
  title?: string;
  status: string;
  progress?: { current?: number; total?: number; title?: string };
  result?: Record<string, unknown>;
  error?: string;
  started_at?: string;
  finished_at?: string;
}

async function adminFetch(path: string, init?: RequestInit) {
  const token = getAuthToken();
  if (!token) throw new Error("Not authenticated");

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    let message = "Request failed";
    try {
      const data = await res.json();
      message = data.detail || message;
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }
  return res.json();
}

export async function runCrawl(
  maxPerFeed = 8,
  maxTotal = 25,
  options?: { includeResearch?: boolean; maxAgeDays?: number }
): Promise<CrawlRunResult> {
  return adminFetch("/api/v1/admin/crawl/run", {
    method: "POST",
    body: JSON.stringify({
      max_per_feed: maxPerFeed,
      max_total: maxTotal,
      include_research: options?.includeResearch ?? true,
      max_age_days: options?.maxAgeDays ?? 730,
    }),
  });
}

export async function listArticles(status: ArticleStatus) {
  return adminFetch(`/api/v1/admin/articles?status=${status}`);
}

export async function patchArticle(
  sourceId: string,
  body: { action?: "approve" | "reject"; topics?: string[] }
) {
  return adminFetch(`/api/v1/admin/articles/${sourceId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function bulkArticles(
  sourceIds: string[],
  action: "approve" | "reject"
) {
  return adminFetch("/api/v1/admin/articles/bulk", {
    method: "POST",
    body: JSON.stringify({ source_ids: sourceIds, action }),
  });
}

export async function buildIndex(sourceIds?: string[]) {
  return adminFetch("/api/v1/admin/index/build", {
    method: "POST",
    body: JSON.stringify({
      source_ids: sourceIds?.length ? sourceIds : null,
    }),
  });
}

export async function triggerPdfIngest(path?: string) {
  return adminFetch("/api/v1/admin/pdf/ingest", {
    method: "POST",
    body: JSON.stringify({ path: path ?? null }),
  });
}

export async function getIndexJob(jobId: string) {
  return adminFetch(`/api/v1/admin/index/jobs/${jobId}`);
}

export async function listIndexJobs(): Promise<{ jobs: KnowledgeJob[] }> {
  return adminFetch("/api/v1/admin/index/jobs");
}

export async function getIndexStats(): Promise<IndexStats> {
  return adminFetch("/api/v1/admin/index/stats");
}

export async function listPdfFiles(): Promise<{ files: PdfFile[]; count: number }> {
  return adminFetch("/api/v1/admin/pdf");
}

export async function uploadPdf(file: File): Promise<PdfFile> {
  const token = getAuthToken();
  if (!token) throw new Error("Not authenticated");

  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/api/v1/admin/pdf/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });

  if (!res.ok) {
    let message = "Upload failed";
    try {
      const data = await res.json();
      message = data.detail || message;
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }
  return res.json();
}

export interface VectorRemovalResult {
  found?: boolean;
  points_deleted: number;
  staging_updated?: boolean;
  source_id?: string;
  source?: string;
  path?: string;
}

export interface WebArticleDeleteResult {
  found?: boolean;
  action: "recycled" | "blocked" | "not_found" | "error";
  points_deleted: number;
  moved_to?: string;
  source_id?: string;
}

export async function deleteWebArticle(
  sourceId: string
): Promise<WebArticleDeleteResult> {
  return adminFetch(`/api/v1/admin/articles/${encodeURIComponent(sourceId)}`, {
    method: "DELETE",
  });
}

export async function removeWebArticleVectors(
  sourceId: string
): Promise<VectorRemovalResult> {
  return adminFetch(
    `/api/v1/admin/articles/${encodeURIComponent(sourceId)}/vectors`,
    { method: "DELETE" }
  );
}

export async function removePdfVectors(path: string): Promise<VectorRemovalResult> {
  return adminFetch(
    `/api/v1/admin/pdf/vectors?path=${encodeURIComponent(path)}`,
    { method: "DELETE" }
  );
}

export async function deletePdf(
  path: string,
  options?: { removeVectors?: boolean }
): Promise<{ message: string; vectors_removed?: number }> {
  const params = new URLSearchParams({ path });
  if (options?.removeVectors === false) {
    params.set("remove_vectors", "false");
  }
  return adminFetch(`/api/v1/admin/pdf?${params.toString()}`, {
    method: "DELETE",
  });
}
