"use client";

import { useCallback, useEffect, useState } from "react";
import { format, parseISO } from "date-fns";
import {
  ChevronLeft,
  ChevronRight,
  Loader2,
  MoreVertical,
  Pencil,
  Search,
  Shield,
  Trash2,
  UserPlus,
} from "lucide-react";
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
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  createAdminUser,
  deleteAdminUser,
  listAdminUsers,
  updateAdminUser,
  type AdminUser,
  type UserRole,
} from "@/lib/api/admin-users";
import { useSession } from "@/lib/contexts/session-context";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 10;

function initials(name: string) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() || "")
    .join("");
}

function formatJoined(iso: string | null) {
  if (!iso) return "—";
  try {
    return format(parseISO(iso), "dd MMM yyyy");
  } catch {
    return "—";
  }
}

type FormState = {
  name: string;
  email: string;
  password: string;
  role: UserRole;
};

const EMPTY_FORM: FormState = {
  name: "",
  email: "",
  password: "",
  role: "user",
};

export default function AdminUsersPage() {
  const { user: currentUser } = useSession();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [roleFilter, setRoleFilter] = useState<"" | UserRole>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<AdminUser | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await listAdminUsers({
        page,
        page_size: PAGE_SIZE,
        search: search || undefined,
        role: roleFilter || undefined,
      });
      setUsers(res.users);
      setTotal(res.total);
      setTotalPages(res.total_pages);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được danh sách");
    } finally {
      setLoading(false);
    }
  }, [page, search, roleFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  };

  const openEdit = (u: AdminUser) => {
    setEditing(u);
    setForm({
      name: u.name,
      email: u.email,
      password: "",
      role: u.role,
    });
    setDialogOpen(true);
    setMenuOpenId(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (editing) {
        await updateAdminUser(editing.id, {
          name: form.name,
          role: form.role,
          ...(form.password ? { password: form.password } : {}),
        });
      } else {
        await createAdminUser({
          name: form.name,
          email: form.email,
          password: form.password,
          role: form.role,
        });
      }
      setDialogOpen(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Thao tác thất bại");
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setBusy(true);
    setError("");
    try {
      await deleteAdminUser(deleteTarget.id);
      setDeleteTarget(null);
      if (users.length === 1 && page > 1) setPage(page - 1);
      else await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Xóa thất bại");
    } finally {
      setBusy(false);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setSearch(searchInput.trim());
  };

  const resetFilters = () => {
    setSearchInput("");
    setSearch("");
    setRoleFilter("");
    setPage(1);
  };

  const rangeStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(page * PAGE_SIZE, total);

  return (
    <div className="px-12 pb-20">
      {/* Header */}
      <section className="mb-12 mt-8 flex items-end justify-between">
        <div className="max-w-2xl">
          <h2 className="mb-4 font-serif text-3xl font-bold italic tracking-tight text-serene-accent">
            Quản lý người dùng
          </h2>
          <p className="leading-relaxed text-muted-foreground opacity-80">
            Quản lý tài khoản, phân quyền admin và thành viên Helios.
          </p>
        </div>
        <Button
          onClick={openCreate}
          className="bg-serene-accent text-white hover:bg-serene-green"
        >
          <UserPlus className="mr-2 h-4 w-4" />
          Thêm thành viên
        </Button>
      </section>

      {/* Search bar */}
      <form
        onSubmit={handleSearch}
        className="mb-8 flex items-center gap-4"
      >
        <div className="relative w-full max-w-md">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Tìm theo tên, email..."
            className="border-none bg-[#f4f4ef] pl-10 focus-visible:ring-serene-green/30"
          />
        </div>
        <Button type="submit" variant="outline" size="sm">
          Tìm
        </Button>
      </form>

      {/* Stats & filters */}
      <div className="mb-12 grid grid-cols-12 gap-6">
        <div className="col-span-12 flex h-36 flex-col justify-between rounded-lg bg-[#f4f4ef] p-8 md:col-span-3">
          <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
            Tổng người dùng
          </p>
          <h3 className="font-serif text-4xl font-bold text-serene-accent">
            {total.toLocaleString("vi-VN")}
          </h3>
        </div>

        <div className="col-span-12 flex items-center gap-8 rounded-lg bg-[#e3e3de] p-8 shadow-[0_32px_64px_rgba(26,28,26,0.04)] md:col-span-9">
          <div className="flex flex-grow flex-col gap-2">
            <label className="text-xs text-muted-foreground opacity-70">
              Vai trò
            </label>
            <Select
              value={roleFilter || "all"}
              onValueChange={(v) => {
                setRoleFilter(v === "all" ? "" : (v as UserRole));
                setPage(1);
              }}
            >
              <SelectTrigger className="border-0 border-b border-border/50 bg-transparent px-0 shadow-none focus:ring-0">
                <SelectValue placeholder="Tất cả vai trò" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tất cả vai trò</SelectItem>
                <SelectItem value="admin">Admin</SelectItem>
                <SelectItem value="user">User</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={resetFilters}
            className="self-end text-serene-accent"
          >
            Xóa bộ lọc
          </Button>
        </div>
      </div>

      {error && (
        <p className="mb-4 text-sm text-destructive">{error}</p>
      )}

      {/* Table */}
      <div className="mb-8 overflow-hidden rounded-xl bg-[#f4f4ef]">
        {loading ? (
          <div className="flex justify-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-serene-accent" />
          </div>
        ) : (
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="bg-[#e9e8e4]">
                {["Thành viên", "Vai trò", "Ngày tham gia", "Thao tác"].map(
                  (h) => (
                    <th
                      key={h}
                      className={cn(
                        "px-8 py-5 text-xs font-normal uppercase tracking-widest text-muted-foreground",
                        h === "Thao tác" && "text-right"
                      )}
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/10">
              {users.length === 0 && (
                <tr>
                  <td
                    colSpan={4}
                    className="px-8 py-12 text-center text-muted-foreground"
                  >
                    Không tìm thấy người dùng.
                  </td>
                </tr>
              )}
              {users.map((u) => (
                <tr
                  key={u.id}
                  className="group transition-colors hover:bg-[#efeeea]"
                >
                  <td className="px-8 py-5">
                    <div className="flex items-center gap-4">
                      <div
                        className={cn(
                          "flex h-10 w-10 items-center justify-center rounded-full text-sm font-bold",
                          u.role === "admin"
                            ? "bg-serene-green/25 text-serene-accent"
                            : "bg-secondary/30 text-muted-foreground"
                        )}
                      >
                        {initials(u.name)}
                      </div>
                      <div>
                        <p className="font-bold transition-colors group-hover:text-serene-accent">
                          {u.name}
                        </p>
                        <p className="text-sm text-muted-foreground opacity-70">
                          {u.email}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-8 py-5">
                    <span className="flex items-center gap-1.5 text-muted-foreground">
                      {u.role === "admin" && (
                        <Shield className="h-3.5 w-3.5 text-serene-accent" />
                      )}
                      {u.role === "admin" ? "Admin" : "User"}
                    </span>
                  </td>
                  <td className="px-8 py-5 text-muted-foreground">
                    {formatJoined(u.created_at)}
                  </td>
                  <td className="relative px-8 py-5 text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() =>
                        setMenuOpenId(menuOpenId === u.id ? null : u.id)
                      }
                    >
                      <MoreVertical className="h-4 w-4" />
                    </Button>
                    {menuOpenId === u.id && (
                      <>
                        <div
                          className="fixed inset-0 z-10"
                          onClick={() => setMenuOpenId(null)}
                        />
                        <div className="absolute right-8 top-12 z-20 min-w-[140px] rounded-lg border border-border/40 bg-white py-1 shadow-lg">
                          <button
                            type="button"
                            className="flex w-full items-center gap-2 px-4 py-2 text-sm hover:bg-muted"
                            onClick={() => openEdit(u)}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                            Sửa
                          </button>
                          <button
                            type="button"
                            className="flex w-full items-center gap-2 px-4 py-2 text-sm text-destructive hover:bg-muted disabled:opacity-40"
                            disabled={currentUser?.id === u.id}
                            onClick={() => {
                              setDeleteTarget(u);
                              setMenuOpenId(null);
                            }}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            Xóa
                          </button>
                        </div>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between px-2">
        <p className="text-sm italic text-muted-foreground opacity-70">
          Hiển thị {rangeStart}–{rangeEnd} / {total} thành viên
        </p>
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            <ChevronLeft className="mr-1 h-4 w-4" />
            Trước
          </Button>
          <span className="flex h-8 w-8 items-center justify-center rounded bg-serene-accent text-sm font-bold text-white">
            {page}
          </span>
          <Button
            variant="ghost"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >
            Sau
            <ChevronRight className="ml-1 h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Create / Edit dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="font-serif sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {editing ? "Sửa thành viên" : "Thêm thành viên"}
            </DialogTitle>
            <DialogDescription>
              {editing
                ? "Cập nhật thông tin hoặc đổi quyền admin."
                : "Tạo tài khoản mới cho Helios."}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium">Họ tên</label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Email</label>
              <Input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
                disabled={!!editing}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">
                {editing ? "Mật khẩu mới (để trống nếu giữ)" : "Mật khẩu"}
              </label>
              <Input
                type="password"
                value={form.password}
                onChange={(e) =>
                  setForm({ ...form, password: e.target.value })
                }
                required={!editing}
                minLength={8}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Vai trò</label>
              <Select
                value={form.role}
                onValueChange={(v) =>
                  setForm({ ...form, role: v as UserRole })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">User</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setDialogOpen(false)}
              >
                Hủy
              </Button>
              <Button
                type="submit"
                disabled={busy}
                className="bg-serene-accent text-white"
              >
                {busy ? "Đang lưu..." : editing ? "Cập nhật" : "Tạo"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Xóa thành viên?</AlertDialogTitle>
            <AlertDialogDescription>
              Xóa vĩnh viễn tài khoản{" "}
              <strong>{deleteTarget?.name}</strong> ({deleteTarget?.email}).
              Hành động này không thể hoàn tác.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Hủy</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void handleDelete()}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {busy ? "Đang xóa..." : "Xóa"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
