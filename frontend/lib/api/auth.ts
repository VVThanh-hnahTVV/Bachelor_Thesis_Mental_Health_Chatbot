import { getOrCreateSessionId } from "@/lib/session";
import { clearAuthToken, getAuthToken, setAuthToken } from "@/lib/auth-token";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return (
        data.detail
          .map((d: { msg?: string }) => d.msg)
          .filter(Boolean)
          .join(", ") || "Request failed"
      );
    }
    return data.message || "Request failed";
  } catch {
    return "Request failed";
  }
}

export async function registerUser(
  name: string,
  email: string,
  password: string
): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      email,
      password,
      session_id: getOrCreateSessionId(),
    }),
  });
  if (!res.ok) {
    throw new Error(await parseError(res));
  }
  const data: AuthResponse = await res.json();
  setAuthToken(data.token);
  return data;
}

export async function loginUser(
  email: string,
  password: string
): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password,
      session_id: getOrCreateSessionId(),
    }),
  });
  if (!res.ok) {
    throw new Error(await parseError(res));
  }
  const data: AuthResponse = await res.json();
  setAuthToken(data.token);
  return data;
}

export async function fetchCurrentUser(): Promise<AuthUser | null> {
  const token = getAuthToken();
  if (!token) return null;
  const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) {
    if (res.status === 401) clearAuthToken();
    return null;
  }
  return res.json();
}

export function logoutUser(): void {
  clearAuthToken();
}
