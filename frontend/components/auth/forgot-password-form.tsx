"use client";

import { useState } from "react";
import { Mail } from "lucide-react";
import { requestPasswordReset } from "@/lib/api/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface ForgotPasswordFormProps {
  onBackToLogin?: () => void;
}

export function ForgotPasswordForm({ onBackToLogin }: ForgotPasswordFormProps) {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await requestPasswordReset(email);
      setSubmitted(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Không thể gửi yêu cầu. Vui lòng thử lại."
      );
    } finally {
      setLoading(false);
    }
  };

  if (submitted) {
    return (
      <div className="space-y-4 text-center py-2">
        <p className="text-base font-semibold text-serene-accent">
          Kiểm tra email của bạn!
        </p>
        <p className="text-sm text-gray-500">
          Nếu tài khoản tồn tại, chúng tôi đã gửi liên kết đặt lại mật khẩu.
        </p>
        {onBackToLogin && (
          <Button
            type="button"
            variant="ghost"
            className="text-serene-accent hover:text-serene-accent/80"
            onClick={onBackToLogin}
          >
            Quay lại đăng nhập
          </Button>
        )}
      </div>
    );
  }

  return (
    <form className="space-y-5" onSubmit={handleSubmit}>
      <div>
        <label
          htmlFor="forgot-email"
          className="block text-sm font-medium text-gray-700 mb-1.5"
        >
          Email
        </label>
        <div className="relative">
          <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            id="forgot-email"
            type="email"
            placeholder="Nhập email của bạn"
            className="pl-10 rounded-xl border-serene-green/20 bg-white focus-visible:ring-serene-green/40"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
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
        {loading ? "Đang gửi..." : "Gửi liên kết đặt lại"}
      </Button>

      {onBackToLogin && (
        <p className="text-sm text-center text-gray-500">
          Nhớ mật khẩu?{" "}
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
