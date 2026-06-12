"use client";

import { useRouter } from "next/navigation";
import { AuthDialog } from "@/components/auth/auth-dialog";

export default function ForgotPasswordPage() {
  const router = useRouter();

  return (
    <AuthDialog
      open
      initialView="forgot-password"
      onOpenChange={(open) => {
        if (!open) router.push("/");
      }}
    />
  );
}
