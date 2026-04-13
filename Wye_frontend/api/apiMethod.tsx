const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

type HttpMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

type QueryParams = Record<string, string | number | boolean | null | undefined>;

type ApiRequestOptions = {
  headers?: HeadersInit;
  query?: QueryParams;
  signal?: AbortSignal;
  skipRefresh?: boolean;
};

type ApiErrorPayload = {
  message?: string;
  [key: string]: unknown;
};

export class ApiError extends Error {
  status: number;
  payload?: ApiErrorPayload;

  constructor(status: number, message: string, payload?: ApiErrorPayload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

const buildUrl = (endpoint: string, query?: QueryParams): string => {
  const normalizedEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const url = new URL(`${API_BASE_URL}${normalizedEndpoint}`);

  if (!query) return url.toString();

  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    url.searchParams.append(key, String(value));
  });

  return url.toString();
};

const mergeHeaders = (headers?: HeadersInit): Headers => {
  const merged = new Headers(headers);
  if (!merged.has("Content-Type")) {
    merged.set("Content-Type", "application/json");
  }
  return merged;
};

const getCookie = (name: string): string => {
  if (typeof document === "undefined") return "";
  const token = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(`${name}=`));
  if (!token) return "";
  return decodeURIComponent(token.slice(name.length + 1));
};

const setCookie = (name: string, value: string, maxAgeSeconds: number) => {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=${encodeURIComponent(value)}; Max-Age=${maxAgeSeconds}; Path=/; SameSite=Lax`;
};

const shouldAttemptRefresh = (endpoint: string) =>
  !endpoint.startsWith("/auth/login") &&
  !endpoint.startsWith("/auth/register") &&
  !endpoint.startsWith("/auth/refresh");

const shouldAttachAccessToken = (endpoint: string) =>
  !endpoint.startsWith("/auth/login") &&
  !endpoint.startsWith("/auth/register") &&
  !endpoint.startsWith("/auth/refresh");

const tryRefreshAccessToken = async (): Promise<boolean> => {
  const refreshToken = getCookie("refreshToken");
  if (!refreshToken) return false;
  try {
    const response = await fetch(buildUrl("/auth/refresh"), {
      method: "POST",
      headers: mergeHeaders(),
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) return false;
    const payload = (await response.json()) as { access_token?: string };
    if (!payload.access_token) return false;
    setCookie("accessToken", payload.access_token, 60 * 60 * 24 * 7);
    return true;
  } catch {
    return false;
  }
};

const parseError = async (response: Response): Promise<ApiError> => {
  let payload: ApiErrorPayload | undefined;
  try {
    payload = (await response.json()) as ApiErrorPayload;
  } catch {
    payload = undefined;
  }

  return new ApiError(
    response.status,
    payload?.message ?? `Request failed with status ${response.status}`,
    payload
  );
};

async function apiRequest<TResponse, TBody = unknown>(
  method: HttpMethod,
  endpoint: string,
  body?: TBody,
  options?: ApiRequestOptions
): Promise<TResponse> {
  const requestUrl = buildUrl(endpoint, options?.query);
  const requestHeaders = mergeHeaders(options?.headers);
  if (shouldAttachAccessToken(endpoint) && !requestHeaders.has("Authorization")) {
    const accessToken = getCookie("accessToken");
    if (accessToken) {
      requestHeaders.set("Authorization", `Bearer ${accessToken}`);
    }
  }

  const response = await fetch(requestUrl, {
    method,
    headers: requestHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: options?.signal,
  });

  if (!response.ok) {
    if (
      response.status === 401 &&
      !options?.skipRefresh &&
      shouldAttemptRefresh(endpoint) &&
      (await tryRefreshAccessToken())
    ) {
      return apiRequest<TResponse, TBody>(method, endpoint, body, { ...options, skipRefresh: true });
    }
    throw await parseError(response);
  }

  if (response.status === 204) {
    return undefined as TResponse;
  }

  return (await response.json()) as TResponse;
}

export async function apiGet<TResponse>(
  endpoint: string,
  options?: ApiRequestOptions
): Promise<TResponse> {
  return apiRequest<TResponse>("GET", endpoint, undefined, options);
}

export async function apiPost<TResponse, TBody = unknown>(
  endpoint: string,
  body: TBody,
  options?: ApiRequestOptions
): Promise<TResponse> {
  return apiRequest<TResponse, TBody>("POST", endpoint, body, options);
}

export async function apiPatch<TResponse, TBody = unknown>(
  endpoint: string,
  body: TBody,
  options?: ApiRequestOptions
): Promise<TResponse> {
  return apiRequest<TResponse, TBody>("PATCH", endpoint, body, options);
}

export async function apiPut<TResponse, TBody = unknown>(
  endpoint: string,
  body: TBody,
  options?: ApiRequestOptions
): Promise<TResponse> {
  return apiRequest<TResponse, TBody>("PUT", endpoint, body, options);
}

export async function apiDelete<TResponse>(
  endpoint: string,
  options?: ApiRequestOptions
): Promise<TResponse> {
  return apiRequest<TResponse>("DELETE", endpoint, undefined, options);
}
