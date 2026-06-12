"use client";

import { useRouter } from "next/navigation";
import { AuthDialog } from "@/components/auth/auth-dialog";

export default function SignupPage() {
  const router = useRouter();

  return (
    <AuthDialog
      open
      initialView="signup"
      onOpenChange={(open) => {
        if (!open) router.push("/");
      }}
    />
  );
}
