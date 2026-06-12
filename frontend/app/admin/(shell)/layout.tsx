import { AdminGuard } from "@/components/admin/admin-guard";
import { AdminShell } from "@/components/admin/admin-shell";

export const metadata = {
  title: "Admin",
};

export default function AdminShellLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AdminGuard>
      <AdminShell>{children}</AdminShell>
    </AdminGuard>
  );
}
