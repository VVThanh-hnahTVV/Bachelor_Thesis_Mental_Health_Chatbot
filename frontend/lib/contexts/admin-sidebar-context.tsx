"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

const STORAGE_KEY = "admin-main-sidebar-open";

type AdminSidebarContextValue = {
  open: boolean;
  toggle: () => void;
};

const AdminSidebarContext = createContext<AdminSidebarContextValue | null>(null);

export function AdminSidebarProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored !== null) setOpen(stored === "true");
    } catch {
      /* ignore */
    }
  }, []);

  const toggle = useCallback(() => {
    setOpen((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, String(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  return (
    <AdminSidebarContext.Provider value={{ open, toggle }}>
      {children}
    </AdminSidebarContext.Provider>
  );
}

export function useAdminSidebar() {
  const ctx = useContext(AdminSidebarContext);
  if (!ctx) {
    throw new Error("useAdminSidebar must be used within AdminSidebarProvider");
  }
  return ctx;
}
