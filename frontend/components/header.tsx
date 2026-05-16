"use client";

import { useState } from "react";
import Link from "next/link";
import { Menu, X, MessageCircle, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "./theme-toggle";
import { SignInButton } from "@/components/auth/sign-in-button";
import { useSession } from "@/lib/contexts/session-context";
import { LunaLogo } from "@/components/luna-logo";

export function Header() {
  const { isAuthenticated, logout, user } = useSession();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const navItems = [
    { href: "/features", label: "Features" },
    { href: "/about", label: "About Luna" },
  ];

  return (
    <div className="w-full fixed top-0 z-50 bg-serene-bg/90 backdrop-blur-sm">
      <nav className="relative max-w-7xl mx-auto px-6 md:px-8 py-5 flex items-center justify-between">
        <Link
          href="/"
          className="flex items-center gap-3 transition-colors hover:text-serene-accent"
        >
          <LunaLogo className="h-14 w-14" priority />
          <div className="flex flex-col">
            <span className="text-xl font-bold tracking-tight text-gray-800">
              Luna 2.0
            </span>
            <span className="text-[10px] uppercase tracking-widest text-serene-accent">
              Your mental health companion
            </span>
          </div>
        </Link>

        <div className="flex items-center gap-3 md:gap-6">
          <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-gray-600">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="hover:text-serene-accent transition-colors"
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <ThemeToggle />

          <Button
            asChild
            className="hidden md:flex items-center gap-2 px-5 py-2 h-auto rounded-full bg-[#E8F0E7] text-serene-accent border border-serene-green/20 hover:bg-[#DCE7DA] shadow-none"
          >
            <Link href="/dashboard">
              <MessageCircle className="w-4 h-4" />
              Start Chat
            </Link>
          </Button>

          {isAuthenticated ? (
            <>
              <span className="hidden md:inline text-sm text-gray-500">
                {user?.name}
              </span>
              <Button
                variant="ghost"
                onClick={logout}
                className="hidden md:flex items-center gap-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-full"
              >
                <LogOut className="w-4 h-4" />
                Sign out
              </Button>
            </>
          ) : (
            <div className="hidden md:block">
              <SignInButton />
            </div>
          )}

          <Button
            variant="ghost"
            size="icon"
            className="md:hidden text-gray-600"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
          >
            {isMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </Button>
        </div>
      </nav>

      {isMenuOpen && (
        <div className="md:hidden border-t border-gray-100 bg-white/80 backdrop-blur-sm px-6 py-4">
          <nav className="flex flex-col gap-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="py-3 text-sm font-medium text-gray-600 hover:text-serene-accent"
                onClick={() => setIsMenuOpen(false)}
              >
                {item.label}
              </Link>
            ))}
            <Button
              asChild
              className="mt-3 rounded-full bg-[#E8F0E7] text-serene-accent border border-serene-green/20 hover:bg-[#DCE7DA]"
            >
              <Link href="/dashboard" onClick={() => setIsMenuOpen(false)}>
                <MessageCircle className="w-4 h-4 mr-2" />
                Start Chat
              </Link>
            </Button>
            {!isAuthenticated && (
              <div className="mt-2">
                <SignInButton />
              </div>
            )}
          </nav>
        </div>
      )}
    </div>
  );
}
