import { AdminGuard } from "@/components/admin/admin-guard";
import { AdminSidebar } from "@/components/admin/admin-sidebar";
import { AdminTopbar } from "@/components/admin/admin-topbar";

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
      <div className="min-h-screen bg-serene-bg font-serif text-foreground">
        <AdminSidebar />
        <AdminTopbar />
        <main className="admin-scrollbar ml-72 min-h-screen overflow-y-auto pt-20">
          {children}
        </main>
      </div>
    </AdminGuard>
  );
}
