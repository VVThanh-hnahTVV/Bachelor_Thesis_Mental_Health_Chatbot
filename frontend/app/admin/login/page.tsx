"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { AdminLoginForm } from "@/components/admin/admin-login-form";
import { useSession } from "@/lib/contexts/session-context";

export default function AdminLoginPage() {
  const router = useRouter();
  const { user, loading, isAuthenticated } = useSession();

  useEffect(() => {
    if (loading) return;
    if (isAuthenticated && user?.role === "admin") {
      router.replace("/admin");
    }
  }, [loading, isAuthenticated, user, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-serene-bg">
        <Loader2 className="h-8 w-8 animate-spin text-serene-accent" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-serene-bg">
      <div className="hidden w-1/2 flex-col justify-between bg-[#e9e8e4] p-16 lg:flex">
        <div>
          <h1 className="font-serif text-5xl italic tracking-tighter text-serene-accent">
            Helios
          </h1>
          <p className="mt-2 text-muted-foreground">Bảng điều khiển quản trị</p>
        </div>
        <blockquote className="max-w-md font-serif text-2xl italic leading-relaxed text-foreground/80">
          &ldquo;Giám sát hệ sinh thái sức khỏe tâm thần — dữ liệu, tri thức và
          trải nghiệm người dùng.&rdquo;
        </blockquote>
        <p className="text-sm text-muted-foreground">
          IT4995 — Bachelor Thesis
        </p>
      </div>

      <div className="flex flex-1 flex-col items-center justify-center px-6 py-12">
        <div className="w-full max-w-md rounded-xl border border-border/40 bg-white p-8 shadow-sm">
          <AdminLoginForm />
        </div>
        <p className="mt-8 text-sm text-muted-foreground">
          <Link href="/" className="hover:text-serene-accent hover:underline">
            ← Về trang chủ Helios
          </Link>
        </p>
      </div>
    </div>
  );
}
