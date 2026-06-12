"use client";

import { useState } from "react";
import { Lock, Mail } from "lucide-react";
import { loginUser } from "@/lib/api/auth";
import { useSession } from "@/lib/contexts/session-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface EmailLoginFormProps {
  onSuccess?: () => void;
  onForgotPassword?: () => void;
  onSignup?: () => void;
}

export function EmailLoginForm({
  onSuccess,
  onForgotPassword,
  onSignup,
}: EmailLoginFormProps) {
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
      await checkSession();
      onSuccess?.();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Email hoặc mật khẩu không đúng. Vui lòng thử lại."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="space-y-5" onSubmit={handleSubmit}>
      <div className="space-y-4">
        <div>
          <label
            htmlFor="login-email"
            className="block text-sm font-medium text-gray-700 mb-1.5"
          >
            Email
          </label>
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              id="login-email"
              type="email"
              placeholder="Nhập email"
              className="pl-10 rounded-xl border-serene-green/20 bg-white focus-visible:ring-serene-green/40"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
        </div>
        <div>
          <label
            htmlFor="login-password"
            className="block text-sm font-medium text-gray-700 mb-1.5"
          >
            Mật khẩu
          </label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              id="login-password"
              type="password"
              placeholder="Nhập mật khẩu"
              className="pl-10 rounded-xl border-serene-green/20 bg-white focus-visible:ring-serene-green/40"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
        </div>
      </div>

      {error && (
        <p className="text-sm text-red-600 text-center font-medium">{error}</p>
      )}

      <Button
        className="w-full rounded-xl font-semibold bg-serene-green hover:bg-serene-accent text-white"
        size="lg"
        type="submit"
        disabled={loading}
      >
        {loading ? "Đang đăng nhập..." : "Đăng nhập"}
      </Button>

      <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-sm text-center">
        <span className="text-gray-500">Chưa có tài khoản?</span>
        {onSignup ? (
          <button
            type="button"
            className="text-serene-accent font-semibold hover:underline"
            onClick={onSignup}
          >
            Đăng ký
          </button>
        ) : null}
        <span className="text-gray-400">·</span>
        {onForgotPassword ? (
          <button
            type="button"
            className="text-serene-accent hover:underline"
            onClick={onForgotPassword}
          >
            Quên mật khẩu?
          </button>
        ) : null}
      </div>
    </form>
  );
}
