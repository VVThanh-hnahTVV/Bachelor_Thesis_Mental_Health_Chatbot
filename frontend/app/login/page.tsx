"use client";

import { useRouter } from "next/navigation";
import { AuthDialog } from "@/components/auth/auth-dialog";

export default function LoginPage() {
  const router = useRouter();

  return (
    <AuthDialog
      open
      initialView="login"
      onOpenChange={(open) => {
        if (!open) router.push("/");
      }}
    />
  );
}
