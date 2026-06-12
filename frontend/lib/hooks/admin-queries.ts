import {
  keepPreviousData,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { getAdminOverview } from "@/lib/api/admin-overview";
import {
  getIndexJob,
  getIndexStats,
  listArticles,
  listIndexJobs,
  listPdfFiles,
  type ArticleStatus,
  type KnowledgeJob,
  type StagedArticle,
} from "@/lib/api/admin-knowledge";
import {
  listAdminUsers,
  type UserRole,
} from "@/lib/api/admin-users";
import {
  getAdminSettings,
  getAdminUsageStats,
} from "@/lib/api/admin-settings";
import {
  getConversationStats,
  getAdminConversation,
  getAdminConversationMessages,
  getSupportQueue,
  listAdminConversations,
  type ConversationOwnerFilter,
} from "@/lib/api/admin-conversations";
import {
  getWellnessStats,
  listWellnessActivities,
} from "@/lib/api/admin-wellness";
import { ADMIN_GC_TIME, ADMIN_STALE_TIME } from "@/lib/query/admin-query-client";

const adminQueryDefaults = {
  staleTime: ADMIN_STALE_TIME,
  gcTime: ADMIN_GC_TIME,
};

const knowledgeRoot = ["admin", "knowledge"] as const;
const wellnessRoot = ["admin", "wellness"] as const;
const conversationsRoot = ["admin", "conversations"] as const;

const settingsRoot = ["admin", "settings"] as const;

export const adminKeys = {
  all: ["admin"] as const,
  overview: (days: number) => [...adminKeys.all, "overview", days] as const,
  users: (params: {
    page: number;
    page_size: number;
    search?: string;
    role?: UserRole | "";
  }) => [...adminKeys.all, "users", params] as const,
  knowledge: {
    all: knowledgeRoot,
    stats: () => [...knowledgeRoot, "stats"] as const,
    articles: (status: ArticleStatus) =>
      [...knowledgeRoot, "articles", status] as const,
    pdfs: () => [...knowledgeRoot, "pdfs"] as const,
    jobs: () => [...knowledgeRoot, "jobs"] as const,
    job: (jobId: string) => [...knowledgeRoot, "job", jobId] as const,
  },
  wellness: {
    all: wellnessRoot,
    stats: () => [...wellnessRoot, "stats"] as const,
    activities: (params: { active_only?: boolean; implemented_only?: boolean }) =>
      [...wellnessRoot, "activities", params] as const,
  },
  conversations: {
    all: conversationsRoot,
    stats: (days: number) => [...conversationsRoot, "stats", days] as const,
    list: (params: {
      page: number;
      page_size: number;
      search?: string;
      owner?: ConversationOwnerFilter | "";
    }) => [...conversationsRoot, "list", params] as const,
    queue: () => [...conversationsRoot, "queue"] as const,
    detail: (sessionId: string) =>
      [...conversationsRoot, "detail", sessionId] as const,
    messages: (sessionId: string) =>
      [...conversationsRoot, "messages", sessionId] as const,
  },
  settings: {
    all: settingsRoot,
    snapshot: () => [...settingsRoot, "snapshot"] as const,
    usage: (days: number) => [...settingsRoot, "usage", days] as const,
  },
};

export function useAdminOverview(days = 7) {
  return useQuery({
    queryKey: adminKeys.overview(days),
    queryFn: () => getAdminOverview(days),
    ...adminQueryDefaults,
  });
}

export function useAdminUsers(params: {
  page: number;
  page_size: number;
  search?: string;
  role?: UserRole | "";
}) {
  return useQuery({
    queryKey: adminKeys.users(params),
    queryFn: () =>
      listAdminUsers({
        page: params.page,
        page_size: params.page_size,
        search: params.search || undefined,
        role: params.role || undefined,
      }),
    placeholderData: keepPreviousData,
    ...adminQueryDefaults,
  });
}

export function useKnowledgeStats() {
  return useQuery({
    queryKey: adminKeys.knowledge.stats(),
    queryFn: getIndexStats,
    ...adminQueryDefaults,
  });
}

export function useKnowledgeArticles(status: ArticleStatus) {
  return useQuery<StagedArticle[]>({
    queryKey: adminKeys.knowledge.articles(status),
    queryFn: async () => {
      const res = await listArticles(status);
      return res.articles || [];
    },
    ...adminQueryDefaults,
  });
}

export function useKnowledgePdfs() {
  return useQuery({
    queryKey: adminKeys.knowledge.pdfs(),
    queryFn: async () => {
      const res = await listPdfFiles();
      return res.files || [];
    },
    ...adminQueryDefaults,
  });
}

export function useKnowledgeJobs() {
  return useQuery({
    queryKey: adminKeys.knowledge.jobs(),
    queryFn: async () => {
      const res = await listIndexJobs();
      return res.jobs || [];
    },
    ...adminQueryDefaults,
  });
}

export function useWellnessStats() {
  return useQuery({
    queryKey: adminKeys.wellness.stats(),
    queryFn: getWellnessStats,
    ...adminQueryDefaults,
  });
}

export function useConversationStats(days = 7) {
  return useQuery({
    queryKey: adminKeys.conversations.stats(days),
    queryFn: () => getConversationStats(days),
    ...adminQueryDefaults,
  });
}

export function useAdminConversations(params: {
  page: number;
  page_size: number;
  search?: string;
  owner?: ConversationOwnerFilter | "";
}) {
  return useQuery({
    queryKey: adminKeys.conversations.list(params),
    queryFn: () =>
      listAdminConversations({
        page: params.page,
        page_size: params.page_size,
        search: params.search || undefined,
        owner: params.owner || undefined,
      }),
    placeholderData: keepPreviousData,
    ...adminQueryDefaults,
  });
}

export function useSupportQueue() {
  return useQuery({
    queryKey: adminKeys.conversations.queue(),
    queryFn: getSupportQueue,
    refetchInterval: 10_000,
    ...adminQueryDefaults,
  });
}

export function useAdminConversationDetail(sessionId: string) {
  return useQuery({
    queryKey: adminKeys.conversations.detail(sessionId),
    queryFn: () => getAdminConversation(sessionId),
    enabled: Boolean(sessionId),
    refetchOnMount: "always",
    ...adminQueryDefaults,
  });
}

export function useAdminConversationMessages(sessionId: string) {
  return useQuery({
    queryKey: adminKeys.conversations.messages(sessionId),
    queryFn: () => getAdminConversationMessages(sessionId),
    enabled: Boolean(sessionId),
    refetchInterval: 5_000,
    ...adminQueryDefaults,
  });
}

export function useWellnessActivities(params?: {
  active_only?: boolean;
  implemented_only?: boolean;
}) {
  return useQuery({
    queryKey: adminKeys.wellness.activities(params ?? {}),
    queryFn: () => listWellnessActivities(params),
    ...adminQueryDefaults,
  });
}

export function useAdminSettings() {
  return useQuery({
    queryKey: adminKeys.settings.snapshot(),
    queryFn: getAdminSettings,
    ...adminQueryDefaults,
  });
}

export function useAdminUsageStats(days = 7) {
  return useQuery({
    queryKey: adminKeys.settings.usage(days),
    queryFn: () => getAdminUsageStats(days),
    ...adminQueryDefaults,
  });
}

export function useKnowledgeJob(jobId: string | null) {
  return useQuery({
    queryKey: adminKeys.knowledge.job(jobId ?? ""),
    queryFn: () => getIndexJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "done" || status === "error") return false;
      return 1500;
    },
    ...adminQueryDefaults,
  });
}

export function useAdminQueryInvalidation() {
  const qc = useQueryClient();

  return {
    overview: (days = 7) =>
      qc.invalidateQueries({ queryKey: adminKeys.overview(days) }),
    users: () =>
      qc.invalidateQueries({ queryKey: [...adminKeys.all, "users"] }),
    knowledgeAll: () =>
      qc.invalidateQueries({ queryKey: adminKeys.knowledge.all }),
    knowledgeStats: () =>
      qc.invalidateQueries({ queryKey: adminKeys.knowledge.stats() }),
    knowledgeArticles: (status?: ArticleStatus) =>
      status
        ? qc.invalidateQueries({
            queryKey: adminKeys.knowledge.articles(status),
          })
        : qc.invalidateQueries({
            queryKey: [...adminKeys.knowledge.all, "articles"],
          }),
    knowledgePdfs: () =>
      qc.invalidateQueries({ queryKey: adminKeys.knowledge.pdfs() }),
    knowledgeJobs: () =>
      qc.invalidateQueries({ queryKey: adminKeys.knowledge.jobs() }),
    updateKnowledgeJobs: (updater: (jobs: KnowledgeJob[]) => KnowledgeJob[]) => {
      qc.setQueryData<KnowledgeJob[]>(adminKeys.knowledge.jobs(), (prev) =>
        updater(prev ?? [])
      );
    },
    refetchKnowledgeAll: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: adminKeys.knowledge.stats() }),
        qc.invalidateQueries({ queryKey: [...adminKeys.knowledge.all, "articles"] }),
        qc.invalidateQueries({ queryKey: adminKeys.knowledge.pdfs() }),
        qc.invalidateQueries({ queryKey: adminKeys.knowledge.jobs() }),
      ]),
    wellnessAll: () =>
      qc.invalidateQueries({ queryKey: adminKeys.wellness.all }),
    wellnessStats: () =>
      qc.invalidateQueries({ queryKey: adminKeys.wellness.stats() }),
    wellnessActivities: () =>
      qc.invalidateQueries({ queryKey: [...wellnessRoot, "activities"] }),
    conversationsAll: () =>
      qc.invalidateQueries({ queryKey: adminKeys.conversations.all }),
    settings: () =>
      qc.invalidateQueries({ queryKey: adminKeys.settings.all }),
  };
}
