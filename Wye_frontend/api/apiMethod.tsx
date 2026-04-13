const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

type HttpMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

type QueryParams = Record<string, string | number | boolean | null | undefined>;

type ApiRequestOptions = {
  headers?: HeadersInit;
  query?: QueryParams;
  signal?: AbortSignal;
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
  const response = await fetch(buildUrl(endpoint, options?.query), {
    method,
    headers: mergeHeaders(options?.headers),
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: options?.signal,
  });

  if (!response.ok) {
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
