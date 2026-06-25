"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useSession } from "@/lib/contexts/session-context";

export function AdminGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, loading, isAuthenticated } = useSession();

  const canAccess =
    user?.role === "admin" || user?.role === "support";
  const isConversationsPath = pathname?.startsWith("/admin/conversations");

  useEffect(() => {
    if (loading) return;
    if (!isAuthenticated) {
      router.replace("/admin/login");
      return;
    }
    if (!canAccess) {
      router.replace("/");
      return;
    }
    if (user?.role === "support" && !isConversationsPath) {
      router.replace("/admin/conversations");
    }
  }, [loading, isAuthenticated, canAccess, user, isConversationsPath, router]);

  if (loading || !isAuthenticated || !canAccess) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-serene-bg">
        <Loader2 className="h-8 w-8 animate-spin text-serene-accent" />
      </div>
    );
  }

  if (user?.role === "support" && !isConversationsPath) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-serene-bg">
        <Loader2 className="h-8 w-8 animate-spin text-serene-accent" />
      </div>
    );
  }

  return <>{children}</>;
}
