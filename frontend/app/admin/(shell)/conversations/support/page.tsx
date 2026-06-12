"use client";

import Link from "next/link";
import { ArrowLeft, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SupportQueueSidebar } from "@/components/admin/support-queue-sidebar";

export default function AdminSupportIdlePage() {
  return (
    <div className="flex h-[calc(100vh-0px)] flex-col">
      <header className="flex shrink-0 items-center border-b border-border/40 bg-white px-6 py-4">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/admin/conversations">
            <ArrowLeft className="mr-1 h-4 w-4" />
            Quay lại
          </Link>
        </Button>
      </header>

      <div className="flex min-h-0 flex-1">
        <SupportQueueSidebar activeSessionId="" />

        <div className="flex min-h-0 min-w-0 flex-1 flex-col items-center justify-center bg-white px-6">
          <MessageSquare className="mb-4 h-12 w-12 text-muted-foreground/40" />
          <p className="text-center font-serif text-lg italic text-muted-foreground">
            Chọn phiên hỗ trợ tiếp theo
          </p>
          <p className="mt-2 max-w-sm text-center text-sm text-muted-foreground">
            Danh sách phiên đang chờ nằm ở cột bên trái.
          </p>
        </div>
      </div>
    </div>
  );
}
