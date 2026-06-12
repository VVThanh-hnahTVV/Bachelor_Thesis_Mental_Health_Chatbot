"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { AuthDialog } from "@/components/auth/auth-dialog";

interface SignInButtonProps {
  className?: string;
  onOpen?: () => void;
}

export function SignInButton({ className, onOpen }: SignInButtonProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        className={className}
        onClick={() => {
          setOpen(true);
          onOpen?.();
        }}
      >
        Đăng nhập
      </Button>
      <AuthDialog open={open} onOpenChange={setOpen} />
    </>
  );
}
