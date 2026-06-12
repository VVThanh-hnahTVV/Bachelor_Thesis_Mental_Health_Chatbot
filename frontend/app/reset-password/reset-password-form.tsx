"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Lock } from "lucide-react";
import { resetPassword } from "@/lib/api/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface ResetPasswordFormProps {
  token: string;
}

export function ResetPasswordForm({ token }: ResetPasswordFormProps) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Mật khẩu phải có ít nhất 8 ký tự.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Mật khẩu không khớp.");
      return;
    }
    setLoading(true);
    try {
      await resetPassword(token, password);
      setSuccess(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Không thể đặt lại mật khẩu. Vui lòng thử lại."
      );
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="text-center space-y-4 py-2">
        <p className="text-sm text-red-600 font-medium">
          Liên kết đặt lại không hợp lệ. Vui lòng yêu cầu liên kết mới.
        </p>
        <Button
          className="rounded-xl bg-serene-green hover:bg-serene-accent text-white"
          onClick={() => router.push("/")}
        >
          Về trang chủ
        </Button>
      </div>
    );
  }

  if (success) {
    return (
      <div className="text-center py-4 space-y-3">
        <p className="text-base font-semibold text-serene-accent">
          Đặt lại mật khẩu thành công!
        </p>
        <Button
          className="rounded-xl bg-serene-green hover:bg-serene-accent text-white"
          onClick={() => router.push("/")}
        >
          Đăng nhập
        </Button>
      </div>
    );
  }

  return (
    <form className="space-y-5" onSubmit={handleSubmit}>
      <div>
        <label
          htmlFor="password"
          className="block text-sm font-medium text-gray-700 mb-1.5"
        >
          Mật khẩu mới
        </label>
        <div className="relative">
          <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            id="password"
            type="password"
            placeholder="Nhập mật khẩu mới (tối thiểu 8 ký tự)"
            className="pl-10 rounded-xl border-serene-green/20 bg-white focus-visible:ring-serene-green/40"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
          />
        </div>
      </div>
      <div>
        <label
          htmlFor="confirmPassword"
          className="block text-sm font-medium text-gray-700 mb-1.5"
        >
          Xác nhận mật khẩu mới
        </label>
        <div className="relative">
          <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            id="confirmPassword"
            type="password"
            placeholder="Nhập lại mật khẩu mới"
            className="pl-10 rounded-xl border-serene-green/20 bg-white focus-visible:ring-serene-green/40"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            minLength={8}
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
        {loading ? "Đang xử lý..." : "Đặt lại mật khẩu"}
      </Button>
    </form>
  );
}
