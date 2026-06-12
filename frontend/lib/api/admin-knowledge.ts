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

export async function getArticle(sourceId: string) {
  return adminFetch(`/api/v1/admin/articles/${sourceId}`);
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

export async function buildIndex() {
  return adminFetch("/api/v1/admin/index/build", { method: "POST" });
}

export async function getIndexJob(jobId: string) {
  return adminFetch(`/api/v1/admin/index/jobs/${jobId}`);
}

export async function getIndexStats(): Promise<IndexStats> {
  return adminFetch("/api/v1/admin/index/stats");
}
