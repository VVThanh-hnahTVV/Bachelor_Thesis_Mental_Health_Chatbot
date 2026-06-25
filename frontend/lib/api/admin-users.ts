import { getAuthToken } from "@/lib/auth-token";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export type UserRole = "user" | "admin" | "support";

export interface AdminUser {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  created_at: string | null;
}

export interface AdminUsersListResponse {
  users: AdminUser[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
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

export async function listAdminUsers(params?: {
  page?: number;
  page_size?: number;
  search?: string;
  role?: UserRole | "";
}): Promise<AdminUsersListResponse> {
  const q = new URLSearchParams();
  if (params?.page) q.set("page", String(params.page));
  if (params?.page_size) q.set("page_size", String(params.page_size));
  if (params?.search) q.set("search", params.search);
  if (params?.role) q.set("role", params.role);
  const qs = q.toString();
  return adminFetch(`/api/v1/admin/users${qs ? `?${qs}` : ""}`);
}

export async function createAdminUser(body: {
  name: string;
  email: string;
  password: string;
  role: UserRole;
}): Promise<AdminUser> {
  return adminFetch("/api/v1/admin/users", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateAdminUser(
  userId: string,
  body: {
    name?: string;
    role?: UserRole;
    password?: string;
  }
): Promise<AdminUser> {
  return adminFetch(`/api/v1/admin/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteAdminUser(userId: string): Promise<void> {
  await adminFetch(`/api/v1/admin/users/${userId}`, { method: "DELETE" });
}
