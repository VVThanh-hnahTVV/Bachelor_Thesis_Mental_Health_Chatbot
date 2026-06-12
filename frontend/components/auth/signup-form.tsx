"use client";

import { useState } from "react";
import { Lock, Mail, User } from "lucide-react";
import { registerUser } from "@/lib/api/auth";
import { useSession } from "@/lib/contexts/session-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface SignupFormProps {
  onSuccess?: () => void;
  onBackToLogin?: () => void;
}

export function SignupForm({ onSuccess, onBackToLogin }: SignupFormProps) {
  const { checkSession } = useSession();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("Mật khẩu không khớp.");
      return;
    }
    setLoading(true);
    try {
      await registerUser(name, email, password);
      await checkSession();
      onSuccess?.();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Đăng ký thất bại. Vui lòng thử lại."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div className="space-y-3">
        <div>
          <label
            htmlFor="signup-name"
            className="block text-sm font-medium text-gray-700 mb-1.5"
          >
            Họ tên
          </label>
          <div className="relative">
            <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              id="signup-name"
              type="text"
              placeholder="Nhập họ tên"
              className="pl-10 rounded-xl border-serene-green/20 bg-white focus-visible:ring-serene-green/40"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
        </div>
        <div>
          <label
            htmlFor="signup-email"
            className="block text-sm font-medium text-gray-700 mb-1.5"
          >
            Email
          </label>
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              id="signup-email"
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
            htmlFor="signup-password"
            className="block text-sm font-medium text-gray-700 mb-1.5"
          >
            Mật khẩu
          </label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              id="signup-password"
              type="password"
              placeholder="Nhập mật khẩu"
              className="pl-10 rounded-xl border-serene-green/20 bg-white focus-visible:ring-serene-green/40"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
        </div>
        <div>
          <label
            htmlFor="signup-confirm-password"
            className="block text-sm font-medium text-gray-700 mb-1.5"
          >
            Xác nhận mật khẩu
          </label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              id="signup-confirm-password"
              type="password"
              placeholder="Nhập lại mật khẩu"
              className="pl-10 rounded-xl border-serene-green/20 bg-white focus-visible:ring-serene-green/40"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
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
        {loading ? "Đang đăng ký..." : "Đăng ký"}
      </Button>

      {onBackToLogin && (
        <p className="text-sm text-center text-gray-500">
          Đã có tài khoản?{" "}
          <button
            type="button"
            className="text-serene-accent font-semibold hover:underline"
            onClick={onBackToLogin}
          >
            Đăng nhập
          </button>
        </p>
      )}
    </form>
  );
}
