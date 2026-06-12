"use client";

import Link from "next/link";
import { Bell, HelpCircle, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/contexts/session-context";
import { useAdminSidebar } from "@/lib/contexts/admin-sidebar-context";
import { cn } from "@/lib/utils";

interface AdminTopbarProps {
  title?: string;
}

export function AdminTopbar({ title = "Helios Admin" }: AdminTopbarProps) {
  const { user, logout } = useSession();
  const { open } = useAdminSidebar();

  return (
    <header
      className={cn(
        "fixed right-0 top-0 z-40 flex h-20 items-center justify-between border-b border-border/40 bg-serene-bg/80 px-12 backdrop-blur-md transition-[left] duration-300",
        open ? "left-72" : "left-11"
      )}
    >
      <div className="flex items-center gap-8">
        <h2 className="font-serif text-lg italic text-serene-accent">{title}</h2>
        <div className="hidden h-8 w-px bg-border/60 md:block" />
        <nav className="hidden gap-6 text-sm text-muted-foreground md:flex">
          <Link
            href="/admin/knowledge"
            className="transition-colors hover:text-serene-accent"
          >
            Tri thức
          </Link>
          <Link href="/" className="transition-colors hover:text-serene-accent">
            Trang chủ
          </Link>
        </nav>
      </div>

      <div className="flex items-center gap-4">
        <button
          type="button"
          className="text-muted-foreground transition-colors hover:text-serene-accent"
          aria-label="Thông báo"
        >
          <Bell className="h-5 w-5" />
        </button>
        <button
          type="button"
          className="text-muted-foreground transition-colors hover:text-serene-accent"
          aria-label="Trợ giúp"
        >
          <HelpCircle className="h-5 w-5" />
        </button>
        <div className="flex h-10 w-10 items-center justify-center rounded-full border border-border/40 bg-serene-green/20 font-serif text-sm font-bold text-serene-accent">
          {user?.name?.charAt(0)?.toUpperCase() || "A"}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            logout();
            window.location.href = "/admin/login";
          }}
          className="text-muted-foreground"
        >
          <LogOut className="mr-1 h-4 w-4" />
          Thoát
        </Button>
      </div>
    </header>
  );
}
