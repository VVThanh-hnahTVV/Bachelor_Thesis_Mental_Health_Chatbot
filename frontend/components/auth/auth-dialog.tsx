"use client";

import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmailLoginForm } from "@/components/auth/email-login-form";
import { ForgotPasswordForm } from "@/components/auth/forgot-password-form";
import { SignupForm } from "@/components/auth/signup-form";

export type AuthView = "login" | "forgot-password" | "signup";

const VIEW_META: Record<
  AuthView,
  { title: string; description: string }
> = {
  login: {
    title: "Đăng nhập",
    description:
      "Không bắt buộc — bạn có thể trò chuyện với Helios mà không cần tài khoản. Đăng nhập để lưu hồ sơ và liên kết phiên trên thiết bị này.",
  },
  "forgot-password": {
    title: "Quên mật khẩu",
    description: "Nhập email để nhận liên kết đặt lại mật khẩu.",
  },
  signup: {
    title: "Đăng ký",
    description: "Tạo tài khoản để bắt đầu hành trình cùng Helios.",
  },
};

interface AuthDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialView?: AuthView;
}

export function AuthDialog({
  open,
  onOpenChange,
  initialView = "login",
}: AuthDialogProps) {
  const [view, setView] = useState<AuthView>(initialView);

  useEffect(() => {
    if (open) setView(initialView);
  }, [open, initialView]);

  const meta = VIEW_META[view];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md rounded-2xl border-serene-green/20 bg-white p-6 sm:p-8 max-h-[90vh] overflow-y-auto">
        <DialogHeader className="text-center sm:text-center space-y-2">
          <DialogTitle className="text-2xl font-bold text-gray-800">
            {meta.title}
          </DialogTitle>
          <DialogDescription className="text-gray-500 text-sm leading-relaxed">
            {meta.description}
          </DialogDescription>
        </DialogHeader>

        {view === "login" && (
          <EmailLoginForm
            onSuccess={() => onOpenChange(false)}
            onForgotPassword={() => setView("forgot-password")}
            onSignup={() => setView("signup")}
          />
        )}
        {view === "forgot-password" && (
          <ForgotPasswordForm onBackToLogin={() => setView("login")} />
        )}
        {view === "signup" && (
          <SignupForm
            onSuccess={() => onOpenChange(false)}
            onBackToLogin={() => setView("login")}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
