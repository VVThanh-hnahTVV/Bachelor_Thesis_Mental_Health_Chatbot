"use client";

import { MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";

export function FixedChat() {
  const router = useRouter();

  const handleClick = () => {
    router.push("/therapy/new");
  };

  return (
    <div className="fixed bottom-6 right-6">
      <Button
        size="icon"
        className="h-14 w-14 rounded-full shadow-lg hover:scale-105 transition-transform"
        onClick={handleClick}
        aria-label="Start chat with Helios"
      >
        <MessageSquare className="h-6 w-6" />
      </Button>
    </div>
  );
}
