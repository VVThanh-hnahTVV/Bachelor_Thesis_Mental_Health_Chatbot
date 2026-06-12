"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  LayoutDashboard,
  MessageSquare,
  Settings,
  Sparkles,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAdminSidebar } from "@/lib/contexts/admin-sidebar-context";
import { cn } from "@/lib/utils";

type NavItem = {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  exact?: boolean;
  disabled?: boolean;
};

const NAV_ITEMS: NavItem[] = [
  { href: "/admin", label: "Tổng quan", icon: LayoutDashboard, exact: true },
  { href: "/admin/knowledge", label: "Tri thức", icon: BookOpen, exact: true },
  { href: "/admin/wellness", label: "Wellness", icon: Sparkles, exact: true },
  { href: "/admin/users", label: "Người dùng", icon: Users, exact: true },
  {
    href: "/admin/conversations",
    label: "Hội thoại",
    icon: MessageSquare,
  },
  { href: "/admin/analytics", label: "Phân tích", icon: BarChart3, disabled: true },
  { href: "/admin/settings", label: "Cài đặt", icon: Settings, exact: true },
];

function AdminSidebarBrand({ compact = false }: { compact?: boolean }) {
  const size = compact ? 28 : 44;

  return (
    <Link
      href="/admin"
      className={cn(
        "block shrink-0",
        compact ? "flex items-center justify-center" : "min-w-0"
      )}
      title="Helios Admin"
    >
      {compact ? (
        <Image
          src="/logo.png"
          alt="Helios"
          width={size}
          height={size}
          className="h-7 w-7 object-contain"
          priority
        />
      ) : (
        <div className="flex items-center gap-3">
          <Image
            src="/logo.png"
            alt=""
            width={size}
            height={size}
            className="h-11 w-11 shrink-0 object-contain"
            priority
            aria-hidden
          />
          <div className="min-w-0">
            <h1 className="font-serif text-3xl font-normal italic tracking-tighter text-serene-accent">
              Helios
            </h1>
            <p className="mt-0.5 text-sm text-muted-foreground opacity-80">
              Bảng điều khiển quản trị
            </p>
          </div>
        </div>
      )}
    </Link>
  );
}

export function AdminSidebar() {
  const pathname = usePathname();
  const { open, toggle } = useAdminSidebar();

  const isActive = (href: string, exact?: boolean) => {
    if (exact) return pathname === href;
    return pathname === href || pathname?.startsWith(`${href}/`);
  };

  if (!open) {
    return (
      <aside className="fixed left-0 top-0 z-50 flex h-screen w-11 flex-col items-center border-r border-border/20 bg-[#f4f4ef] py-4">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          onClick={toggle}
          title="Hiện menu admin"
          aria-label="Hiện menu admin"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>

        <div className="mt-3">
          <AdminSidebarBrand compact />
        </div>

        <nav className="admin-scrollbar mt-4 flex flex-1 flex-col items-center gap-1 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = !item.disabled && isActive(item.href, item.exact);

            if (item.disabled) {
              return (
                <div
                  key={item.href}
                  className="flex h-9 w-9 cursor-not-allowed items-center justify-center text-muted-foreground/40"
                  title={`${item.label} (sắp có)`}
                >
                  <Icon className="h-4 w-4" strokeWidth={1.5} />
                </div>
              );
            }

            return (
              <Link
                key={item.href}
                href={item.href}
                title={item.label}
                className={cn(
                  "flex h-9 w-9 items-center justify-center rounded-md transition-colors",
                  active
                    ? "bg-white text-serene-accent shadow-sm"
                    : "text-muted-foreground hover:bg-white/60 hover:text-serene-accent"
                )}
              >
                <Icon className="h-4 w-4" strokeWidth={active ? 2 : 1.5} />
              </Link>
            );
          })}
        </nav>

        <div
          className="mt-auto flex h-9 w-9 items-center justify-center rounded-md bg-serene-accent"
          title="Hệ thống hoạt động"
        >
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-200" />
        </div>
      </aside>
    );
  }

  return (
    <aside className="fixed left-0 top-0 z-50 flex h-screen w-72 flex-col bg-[#f4f4ef] px-6 py-8">
      <div className="mb-8 flex items-start justify-between gap-2">
        <AdminSidebarBrand />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          onClick={toggle}
          title="Ẩn menu admin"
          aria-label="Ẩn menu admin"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
      </div>

      <nav className="admin-scrollbar flex-1 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = !item.disabled && isActive(item.href, item.exact);

          if (item.disabled) {
            return (
              <div
                key={item.href}
                className="flex cursor-not-allowed items-center gap-4 px-4 py-3 text-muted-foreground/50"
                title="Sắp có"
              >
                <Icon className="h-5 w-5" strokeWidth={1.5} />
                <span className="text-sm tracking-tight">{item.label}</span>
              </div>
            );
          }

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-4 border-r-2 px-4 py-3 transition-colors duration-300",
                active
                  ? "border-serene-accent bg-white/60 font-bold text-serene-accent"
                  : "border-transparent text-muted-foreground opacity-80 hover:bg-white/40 hover:text-serene-accent"
              )}
            >
              <Icon className="h-5 w-5" strokeWidth={active ? 2 : 1.5} />
              <span className="text-sm tracking-tight">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto pt-8">
        <div className="flex w-full items-center justify-center gap-3 bg-serene-accent py-4 text-sm font-medium text-white">
          <span>Hệ thống</span>
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-200" />
        </div>
      </div>
    </aside>
  );
}
