"use client";

import { AdminSidebarProvider, useAdminSidebar } from "@/lib/contexts/admin-sidebar-context";
import { AdminSidebar } from "@/components/admin/admin-sidebar";
import { AdminTopbar } from "@/components/admin/admin-topbar";
import { cn } from "@/lib/utils";

function AdminMain({ children }: { children: React.ReactNode }) {
  const { open } = useAdminSidebar();

  return (
    <main
      className={cn(
        "admin-scrollbar min-h-screen overflow-y-auto pt-20 transition-[margin-left] duration-300",
        open ? "ml-72" : "ml-11"
      )}
    >
      {children}
    </main>
  );
}

export function AdminShell({ children }: { children: React.ReactNode }) {
  return (
    <AdminSidebarProvider>
      <div className="min-h-screen bg-serene-bg font-serif text-foreground">
        <AdminSidebar />
        <AdminTopbar />
        <AdminMain>{children}</AdminMain>
      </div>
    </AdminSidebarProvider>
  );
}
