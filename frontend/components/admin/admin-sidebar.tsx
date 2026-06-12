"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  BookOpen,
  Database,
  LayoutDashboard,
  MessageSquare,
  Settings,
  Sparkles,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/admin", label: "Tổng quan", icon: LayoutDashboard, exact: true },
  { href: "/admin/knowledge", label: "Tri thức", icon: BookOpen, exact: true },
  {
    href: "/admin/knowledge/vectors",
    label: "Vector DB",
    icon: Database,
    exact: true,
  },
  { href: "/admin/wellness", label: "Wellness", icon: Sparkles, disabled: true },
  { href: "/admin/users", label: "Người dùng", icon: Users, exact: true },
  {
    href: "/admin/conversations",
    label: "Hội thoại",
    icon: MessageSquare,
    disabled: true,
  },
  { href: "/admin/analytics", label: "Phân tích", icon: BarChart3, disabled: true },
  { href: "/admin/settings", label: "Cài đặt", icon: Settings, disabled: true },
] as const;

export function AdminSidebar() {
  const pathname = usePathname();

  const isActive = (href: string, exact?: boolean) => {
    if (exact) return pathname === href;
    return pathname === href || pathname?.startsWith(`${href}/`);
  };

  return (
    <aside className="fixed left-0 top-0 z-50 flex h-screen w-72 flex-col bg-[#f4f4ef] px-6 py-8">
      <div className="mb-12">
        <Link href="/admin" className="block">
          <h1 className="font-serif text-3xl font-normal italic tracking-tighter text-serene-accent">
            Helios
          </h1>
          <p className="mt-1 text-sm text-muted-foreground opacity-80">
            Bảng điều khiển quản trị
          </p>
        </Link>
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
                  ? "border-serene-accent font-bold text-serene-accent bg-white/60"
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
