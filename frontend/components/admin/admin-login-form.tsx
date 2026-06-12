"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Lock, Mail, Shield } from "lucide-react";
import { fetchCurrentUser, loginUser, logoutUser } from "@/lib/api/auth";
import { useSession } from "@/lib/contexts/session-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function AdminLoginForm() {
  const router = useRouter();
  const { checkSession } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await loginUser(email, password);
      const user = await fetchCurrentUser();
      if (!user || user.role !== "admin") {
        logoutUser();
        setError("Tài khoản này không có quyền quản trị.");
        return;
      }
      await checkSession();
      router.replace("/admin");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Email hoặc mật khẩu không đúng."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="space-y-6" onSubmit={handleSubmit}>
      <div className="mb-8 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-serene-green/15">
          <Shield className="h-7 w-7 text-serene-accent" />
        </div>
        <h1 className="font-serif text-3xl italic text-foreground">
          Đăng nhập Admin
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Chỉ dành cho quản trị viên Helios
        </p>
      </div>

      <div className="space-y-4">
        <div>
          <label
            htmlFor="admin-email"
            className="mb-1.5 block text-sm font-medium text-foreground"
          >
            Email
          </label>
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="admin-email"
              type="email"
              placeholder="admin@example.com"
              className="border-serene-green/20 bg-white pl-10 font-serif focus-visible:ring-serene-green/40"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
        </div>
        <div>
          <label
            htmlFor="admin-password"
            className="mb-1.5 block text-sm font-medium text-foreground"
          >
            Mật khẩu
          </label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="admin-password"
              type="password"
              placeholder="••••••••"
              className="border-serene-green/20 bg-white pl-10 font-serif focus-visible:ring-serene-green/40"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
        </div>
      </div>

      {error && (
        <p className="text-center text-sm font-medium text-destructive">{error}</p>
      )}

      <Button
        className="w-full bg-serene-accent font-semibold text-white hover:bg-serene-green"
        size="lg"
        type="submit"
        disabled={loading}
      >
        {loading ? "Đang xác thực..." : "Vào bảng điều khiển"}
      </Button>
    </form>
  );
}
