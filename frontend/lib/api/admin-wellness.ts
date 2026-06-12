import { getAuthToken } from "@/lib/auth-token";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface WellnessActivityAdmin {
  id: string;
  scope: string[];
  content_type: string;
  activity_type: string;
  ui_component: string;
  title: { vi: string; en: string };
  description: { vi: string; en: string };
  benefits: string[];
  benefits_en: string[];
  tags: string[];
  duration_min: number;
  avg_rating: number;
  rating_count: number;
  active: boolean;
  implemented: boolean;
  video_url?: string | null;
  youtube_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WellnessStats {
  db_total: number;
  db_active: number;
  db_implemented: number;
  seed_catalog_count: number;
  using_seed_fallback: boolean;
  vector_points: number;
  vector_collection: string;
}

export interface WellnessActivitiesResponse {
  source: "mongodb" | "seed";
  count: number;
  activities: WellnessActivityAdmin[];
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
  if (res.status === 204) return null;
  return res.json();
}

export async function getWellnessStats(): Promise<WellnessStats> {
  return adminFetch("/api/v1/admin/wellness/stats");
}

export async function listWellnessActivities(params?: {
  active_only?: boolean;
  implemented_only?: boolean;
  scope?: string;
}): Promise<WellnessActivitiesResponse> {
  const q = new URLSearchParams();
  if (params?.active_only) q.set("active_only", "true");
  if (params?.implemented_only) q.set("implemented_only", "true");
  if (params?.scope) q.set("scope", params.scope);
  const qs = q.toString();
  return adminFetch(`/api/v1/admin/wellness/activities${qs ? `?${qs}` : ""}`);
}

export async function updateWellnessActivity(
  activityId: string,
  body: {
    active?: boolean;
    implemented?: boolean;
    title_vi?: string;
    title_en?: string;
    description_vi?: string;
    description_en?: string;
    duration_min?: number;
    tags?: string[];
    benefits?: string[];
    benefits_en?: string[];
  }
): Promise<{ activity: WellnessActivityAdmin }> {
  return adminFetch(`/api/v1/admin/wellness/activities/${activityId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function seedWellnessActivities(): Promise<{
  seeded: number;
  total: number;
}> {
  return adminFetch("/api/v1/admin/wellness/seed", { method: "POST" });
}

export async function reindexWellnessVectors(): Promise<{
  success: boolean;
  indexed: number;
  total: number;
  errors: string[];
}> {
  return adminFetch("/api/v1/admin/wellness/reindex", { method: "POST" });
}

export async function clearWellnessVectors(): Promise<{
  success: boolean;
  points_deleted: number;
  collection: string;
}> {
  return adminFetch("/api/v1/admin/wellness/vectors", { method: "DELETE" });
}

export async function deleteWellnessActivityVectors(activityId: string): Promise<{
  success: boolean;
  points_deleted: number;
  activity_id: string;
}> {
  return adminFetch(`/api/v1/admin/wellness/activities/${activityId}/vectors`, {
    method: "DELETE",
  });
}
