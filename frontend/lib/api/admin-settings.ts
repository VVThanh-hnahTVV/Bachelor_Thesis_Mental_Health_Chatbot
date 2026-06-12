import { getAuthToken } from "@/lib/auth-token";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

async function adminFetch(path: string) {
  const token = getAuthToken();
  if (!token) throw new Error("Not authenticated");

  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
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

export interface ProviderConfig {
  name: string;
  configured: boolean;
  model: string;
  api_key: { configured: boolean; masked: string | null };
  base_url?: string;
}

export interface AdminSettingsSnapshot {
  updated_at: string;
  read_only_note: string;
  llm: {
    primary_provider: string;
    active_model: string;
    fallback_chain: string[];
    fallback_chain_env: string;
    enable_local_chat: boolean;
    debug_llm_prompts: boolean;
    ingest_llm_provider: string;
    providers: ProviderConfig[];
  };
  rag: {
    embedding_provider: string;
    embedding_model: string;
    chunk_size_words: number;
    chunk_overlap_words: number;
    chunk_batch_max_words: number;
    enable_llm_chunking: boolean;
    top_k: number;
    reranker_top_k: number;
    min_retrieval_confidence: number;
    vector_search_type: string;
    distance_metric: string;
    collections: {
      pdf_rag: string;
      web_corpus: string;
      wellness: string;
    };
    qdrant_url: string;
    vector_local_path: string;
    wellness_top_k: number;
    wellness_min_score: number;
    wellness_suggestion_min_score: number;
  };
  web_search: {
    enable_tavily: boolean;
    enable_pubmed: boolean;
    tavily_max_results: number;
    tavily_search_depth: string;
    tavily_include_domains: string[];
    tavily_api_key: { configured: boolean; masked: string | null };
    pubmed_max_results: number;
    pubmed_use_ncbi: boolean;
    pubmed_europepmc_fallback: boolean;
    pubmed_email: string | null;
    pubmed_api_key: { configured: boolean; masked: string | null };
    context_limit: number;
  };
  guardrails: {
    enable_input_guardrails: boolean;
    enable_output_guardrails: boolean;
    input_checks: string[];
    output_checks: string[];
    model_source: string;
  };
  system: {
    enable_medical_mode: boolean;
    mongo_db_name: string;
    redis_url: string;
    cors_origins: string[];
    conversation_summary_max_tokens: number;
  };
}

export interface UsageTotals {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  calls: number;
}

export interface UsageByDay {
  date: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  calls: number;
}

export interface AdminUsageStats {
  days: number;
  updated_at: string;
  available: boolean;
  message?: string;
  today: UsageTotals;
  period: UsageTotals;
  by_day: UsageByDay[];
  pricing_note: string;
}

export function getAdminSettings(): Promise<AdminSettingsSnapshot> {
  return adminFetch("/api/v1/admin/settings");
}

export function getAdminUsageStats(days = 7): Promise<AdminUsageStats> {
  return adminFetch(`/api/v1/admin/settings/usage?days=${days}`);
}
