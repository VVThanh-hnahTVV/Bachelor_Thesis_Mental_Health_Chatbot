"use client";

import { useState } from "react";
import { format, parseISO } from "date-fns";
import {
  Database,
  Loader2,
  MoreVertical,
  Pencil,
  RefreshCw,
  Sparkles,
  Star,
  Trash2,
  Zap,
} from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  clearWellnessVectors,
  deleteWellnessActivityVectors,
  reindexWellnessVectors,
  seedWellnessActivities,
  updateWellnessActivity,
  type WellnessActivityAdmin,
} from "@/lib/api/admin-wellness";
import {
  useAdminQueryInvalidation,
  useWellnessActivities,
  useWellnessStats,
} from "@/lib/hooks/admin-queries";
import { cn } from "@/lib/utils";

type FilterState = "all" | "active" | "implemented";

const CONTENT_TYPE_LABELS: Record<string, string> = {
  interactive: "Tương tác",
  video: "Video",
};

type FormState = {
  title_vi: string;
  title_en: string;
  description_vi: string;
  description_en: string;
  duration_min: string;
  tags: string;
  active: boolean;
  implemented: boolean;
};

function activityToForm(activity: WellnessActivityAdmin): FormState {
  return {
    title_vi: activity.title.vi,
    title_en: activity.title.en,
    description_vi: activity.description.vi,
    description_en: activity.description.en,
    duration_min: String(activity.duration_min),
    tags: activity.tags.join(", "),
    active: activity.active,
    implemented: activity.implemented,
  };
}

function formatTime(iso?: string | null) {
  if (!iso) return "—";
  try {
    return format(parseISO(iso), "dd/MM/yyyy HH:mm");
  } catch {
    return "—";
  }
}

export default function AdminWellnessPage() {
  const { wellnessAll } = useAdminQueryInvalidation();
  const [filter, setFilter] = useState<FilterState>("all");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [editing, setEditing] = useState<WellnessActivityAdmin | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [clearVectorsOpen, setClearVectorsOpen] = useState(false);
  const [vectorDeleteTarget, setVectorDeleteTarget] =
    useState<WellnessActivityAdmin | null>(null);

  const activityParams =
    filter === "active"
      ? { active_only: true }
      : filter === "implemented"
        ? { implemented_only: true }
        : undefined;

  const {
    data: stats,
    isFetching: statsFetching,
    refetch: refetchStats,
  } = useWellnessStats();
  const {
    data: activitiesData,
    isPending,
    isFetching: activitiesFetching,
    refetch: refetchActivities,
  } = useWellnessActivities(activityParams);

  const activities = activitiesData?.activities ?? [];
  const loading = isPending && !activitiesData;

  const openEdit = (activity: WellnessActivityAdmin) => {
    setEditing(activity);
    setForm(activityToForm(activity));
    setActionError("");
    setDialogOpen(true);
    setMenuOpenId(null);
  };

  const closeDialog = () => {
    setDialogOpen(false);
    setEditing(null);
    setForm(null);
    setActionError("");
  };

  const handleSave = async () => {
    if (!editing || !form) return;
    const duration = parseInt(form.duration_min, 10);
    if (!form.title_vi.trim() || !form.title_en.trim()) {
      setActionError("Tiêu đề tiếng Việt và tiếng Anh là bắt buộc.");
      return;
    }
    if (!Number.isFinite(duration) || duration < 1) {
      setActionError("Thời lượng phải là số nguyên dương.");
      return;
    }

    setBusy(true);
    setActionError("");
    try {
      await updateWellnessActivity(editing.id, {
        title_vi: form.title_vi.trim(),
        title_en: form.title_en.trim(),
        description_vi: form.description_vi.trim(),
        description_en: form.description_en.trim(),
        duration_min: duration,
        tags: form.tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        active: form.active,
        implemented: form.implemented,
      });
      await wellnessAll();
      closeDialog();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Lưu thất bại");
    } finally {
      setBusy(false);
    }
  };

  const handleSeed = async () => {
    setBusy(true);
    setActionError("");
    try {
      await seedWellnessActivities();
      await wellnessAll();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Seed thất bại");
    } finally {
      setBusy(false);
    }
  };

  const handleReindex = async () => {
    setBusy(true);
    setActionError("");
    try {
      const result = await reindexWellnessVectors();
      if (result.errors?.length) {
        setActionError(result.errors.join("; "));
      }
      await wellnessAll();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Lập chỉ mục thất bại");
    } finally {
      setBusy(false);
    }
  };

  const handleClearAllVectors = async () => {
    setBusy(true);
    setActionError("");
    try {
      await clearWellnessVectors();
      await wellnessAll();
      setClearVectorsOpen(false);
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Xóa vector Qdrant thất bại"
      );
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteActivityVectors = async () => {
    if (!vectorDeleteTarget) return;
    setBusy(true);
    setActionError("");
    try {
      await deleteWellnessActivityVectors(vectorDeleteTarget.id);
      await wellnessAll();
      setVectorDeleteTarget(null);
      setMenuOpenId(null);
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Gỡ vector thất bại"
      );
    } finally {
      setBusy(false);
    }
  };

  const handleRefresh = () => {
    void refetchStats();
    void refetchActivities();
  };

  if (loading) {
    return (
      <div className="flex justify-center py-32">
        <Loader2 className="h-8 w-8 animate-spin text-serene-accent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-12 pb-12 pt-8">
      <div className="mb-10 flex flex-wrap items-end justify-between gap-6">
        <div>
          <h3 className="mb-2 font-serif text-3xl italic tracking-tight text-foreground">
            Wellness Activities
          </h3>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={statsFetching || activitiesFetching}
          >
            <RefreshCw
              className={`mr-1 h-4 w-4 ${statsFetching || activitiesFetching ? "animate-spin" : ""}`}
            />
            Làm mới
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void handleSeed()}
            disabled={busy}
          >
            <Database className="mr-1 h-4 w-4" />
            Đồng bộ từ seed
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setClearVectorsOpen(true)}
            disabled={busy}
          >
            <Trash2 className="mr-1 h-4 w-4" />
            Xóa vector Qdrant
          </Button>
          <Button size="sm" onClick={() => void handleReindex()} disabled={busy}>
            <Zap className="mr-1 h-4 w-4" />
            Lập chỉ mục Qdrant
          </Button>
        </div>
      </div>

      {actionError && (
        <p className="mb-6 text-sm text-destructive">{actionError}</p>
      )}

      {stats && (
        <div className="mb-10 grid grid-cols-12 gap-4">
          <div className="col-span-12 bg-[#f4f4ef] p-6 md:col-span-4">
            <p className="mb-2 text-xs font-medium uppercase tracking-widest text-muted-foreground opacity-60">
              Trong MongoDB
            </p>
            <p className="font-serif text-3xl italic text-serene-accent">
              {stats.db_total}
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              {stats.db_active} đang bật · {stats.db_implemented} đã triển khai
            </p>
          </div>
          <div className="col-span-12 bg-[#e9e8e4] p-6 md:col-span-4">
            <p className="mb-2 text-xs font-medium uppercase tracking-widest text-muted-foreground opacity-60">
              Catalog seed
            </p>
            <p className="font-serif text-3xl text-foreground">
              {stats.seed_catalog_count}
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              Bản mặc định trong code
            </p>
          </div>
          <div className="col-span-12 bg-white p-6 md:col-span-4">
            <p className="mb-2 text-xs font-medium uppercase tracking-widest text-muted-foreground opacity-60">
              Vector Qdrant
            </p>
            <p className="font-serif text-3xl text-foreground">
              {stats.vector_points}
            </p>
            <p className="mt-2 truncate text-xs text-muted-foreground">
              {stats.vector_collection}
            </p>
          </div>
        </div>
      )}

      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Sparkles className="h-5 w-5 text-serene-accent" />
          <h4 className="font-serif text-xl italic">
            Danh sách ({activities.length})
          </h4>
        </div>
        <Select
          value={filter}
          onValueChange={(v) => setFilter(v as FilterState)}
        >
          <SelectTrigger className="w-48 bg-white">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tất cả</SelectItem>
            <SelectItem value="active">Đang bật</SelectItem>
            <SelectItem value="implemented">Đã triển khai</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="border border-border/40 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border/40 bg-[#f4f4ef]/60 text-xs uppercase tracking-widest text-muted-foreground">
            <tr>
              <th className="px-6 py-4 font-medium">Hoạt động</th>
              <th className="px-4 py-4 font-medium">Loại</th>
              <th className="px-4 py-4 font-medium">Thời lượng</th>
              <th className="px-4 py-4 font-medium">Đánh giá</th>
              <th className="px-4 py-4 font-medium">Trạng thái</th>
              <th className="px-4 py-4 font-medium">Cập nhật</th>
              <th className="px-4 py-4 font-medium" />
            </tr>
          </thead>
          <tbody>
            {activities.map((activity, index) => {
              const menuOpensUpward = index >= activities.length - 2;
              return (
              <tr
                key={activity.id}
                className="border-b border-border/20 transition-colors hover:bg-[#f4f4ef]/30"
              >
                <td className="px-6 py-4">
                  <p className="font-medium text-foreground">
                    {activity.title.vi}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {activity.id} · {activity.ui_component}
                  </p>
                </td>
                <td className="px-4 py-4 text-muted-foreground">
                  {CONTENT_TYPE_LABELS[activity.content_type] ||
                    activity.content_type}
                </td>
                <td className="px-4 py-4">{activity.duration_min} phút</td>
                <td className="px-4 py-4">
                  <div className="flex items-center gap-1">
                    <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />
                    <span>{activity.avg_rating.toFixed(1)}</span>
                    <span className="text-xs text-muted-foreground">
                      ({activity.rating_count})
                    </span>
                  </div>
                </td>
                <td className="px-4 py-4">
                  <div className="flex flex-wrap gap-1.5">
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs",
                        activity.active
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-muted text-muted-foreground"
                      )}
                    >
                      {activity.active ? "Bật" : "Tắt"}
                    </span>
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs",
                        activity.implemented
                          ? "bg-blue-100 text-blue-800"
                          : "bg-muted text-muted-foreground"
                      )}
                    >
                      {activity.implemented ? "Triển khai" : "Chưa có UI"}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-4 text-xs text-muted-foreground">
                  {formatTime(activity.updated_at || activity.created_at)}
                </td>
                <td className="relative px-4 py-4 text-right">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() =>
                      setMenuOpenId(
                        menuOpenId === activity.id ? null : activity.id
                      )
                    }
                  >
                    <MoreVertical className="h-4 w-4" />
                  </Button>
                  {menuOpenId === activity.id && (
                    <>
                      <div
                        className="fixed inset-0 z-40"
                        onClick={() => setMenuOpenId(null)}
                      />
                      <div
                        className={cn(
                          "absolute right-4 z-50 min-w-[140px] rounded-md border bg-white py-1 shadow-lg",
                          menuOpensUpward ? "bottom-full mb-1" : "top-full mt-1"
                        )}
                      >
                        <button
                          type="button"
                          className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted"
                          onClick={() => openEdit(activity)}
                        >
                          <Pencil className="h-4 w-4" />
                          Chỉnh sửa
                        </button>
                        <button
                          type="button"
                          className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-destructive hover:bg-muted"
                          onClick={() => {
                            setVectorDeleteTarget(activity);
                            setMenuOpenId(null);
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                          Gỡ vector Qdrant
                        </button>
                      </div>
                    </>
                  )}
                </td>
              </tr>
            );
            })}
            {activities.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className="px-6 py-16 text-center text-muted-foreground"
                >
                  Không có hoạt động nào. Thử bấm &quot;Đồng bộ từ seed&quot; để
                  nạp catalog mặc định vào MongoDB.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Dialog open={dialogOpen} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-serif italic">
              Chỉnh sửa hoạt động
            </DialogTitle>
            <DialogDescription>
              {editing?.id} — thay đổi sẽ lưu vào MongoDB.
            </DialogDescription>
          </DialogHeader>

          {form && (
            <div className="space-y-4 py-2">
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Tiêu đề (VI)
                </label>
                <Input
                  value={form.title_vi}
                  onChange={(e) =>
                    setForm({ ...form, title_vi: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Tiêu đề (EN)
                </label>
                <Input
                  value={form.title_en}
                  onChange={(e) =>
                    setForm({ ...form, title_en: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Mô tả (VI)
                </label>
                <textarea
                  className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={form.description_vi}
                  onChange={(e) =>
                    setForm({ ...form, description_vi: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Mô tả (EN)
                </label>
                <textarea
                  className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={form.description_en}
                  onChange={(e) =>
                    setForm({ ...form, description_en: e.target.value })
                  }
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Thời lượng (phút)
                  </label>
                  <Input
                    type="number"
                    min={1}
                    value={form.duration_min}
                    onChange={(e) =>
                      setForm({ ...form, duration_min: e.target.value })
                    }
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Tags (phẩy)
                  </label>
                  <Input
                    value={form.tags}
                    onChange={(e) => setForm({ ...form, tags: e.target.value })}
                  />
                </div>
              </div>
              <div className="flex gap-6">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.active}
                    onChange={(e) =>
                      setForm({ ...form, active: e.target.checked })
                    }
                  />
                  Đang bật
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.implemented}
                    onChange={(e) =>
                      setForm({ ...form, implemented: e.target.checked })
                    }
                  />
                  Đã triển khai UI
                </label>
              </div>
              {actionError && (
                <p className="text-sm text-destructive">{actionError}</p>
              )}
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={closeDialog} disabled={busy}>
              Hủy
            </Button>
            <Button onClick={() => void handleSave()} disabled={busy}>
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Lưu
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={clearVectorsOpen} onOpenChange={setClearVectorsOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Xóa toàn bộ vector Qdrant?</AlertDialogTitle>
            <AlertDialogDescription>
              Chỉ xóa vector trong Qdrant — dữ liệu MongoDB không đổi. Sau đó
              bấm &quot;Lập chỉ mục Qdrant&quot; để embed lại sạch, không bị
              trùng.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Hủy</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                void handleClearAllVectors();
              }}
              disabled={busy}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Xóa vector
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={!!vectorDeleteTarget}
        onOpenChange={(open) => !open && setVectorDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Gỡ vector khỏi Qdrant?</AlertDialogTitle>
            <AlertDialogDescription>
              Xóa vector của &quot;{vectorDeleteTarget?.title.vi}&quot; (
              {vectorDeleteTarget?.id}) khỏi Qdrant. Hoạt động vẫn giữ trong
              MongoDB.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Hủy</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                void handleDeleteActivityVectors();
              }}
              disabled={busy}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Gỡ vector
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
