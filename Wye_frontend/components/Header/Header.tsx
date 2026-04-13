"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Avatar, Button, Drawer } from "antd";
import { MenuOutlined, UserOutlined } from "@ant-design/icons";
import { AuthModal } from "../AuthModal/AuthModal";
import "./Header.css";

const navItems = [
  { href: "/", label: "Home" },
  { href: "/chat", label: "Chat" },
  { href: "#", label: "Mood Tracker" },
  { href: "#", label: "Resources" },
  { href: "#", label: "Profile" },
];

export function Header() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const hasAccessToken = () =>
    document.cookie
      .split(";")
      .map((cookie) => cookie.trim())
      .some((cookie) => cookie.startsWith("accessToken="));

  useEffect(() => {
    setIsAuthenticated(hasAccessToken());
  }, []);

  const openAuth = (mode: "login" | "register") => {
    setAuthMode(mode);
    setAuthOpen(true);
    setDrawerOpen(false);
  };

  return (
    <>
      <header className="header">
        <div className="header__inner">
          <Link href="/" className="header__logo">
            <strong>Wye</strong>
          </Link>

          <nav className="header__nav" aria-label="Main">
            {navItems.map((item) => (
              <Link key={item.href + item.label} href={item.href} className="header__navLink">
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="header__actions">
            {isAuthenticated ? (
              <Avatar className="header__avatar" size={40}>
                <UserOutlined />
              </Avatar>
            ) : (
              <Button
                type="primary"
                htmlType="button"
                className="header__authBtn"
                onClick={() => openAuth("login")}
              >
                Đăng nhập
              </Button>
            )}
            <Button
              type="text"
              className="header__menuBtn"
              aria-label="Open menu"
              icon={<MenuOutlined />}
              onClick={() => setDrawerOpen(true)}
            />
          </div>

          <Drawer
            title="Menu"
            placement="right"
            className="header__drawer"
            open={drawerOpen}
            onClose={() => setDrawerOpen(false)}
            width={280}
          >
            <div className="header__drawerAuth">
              {isAuthenticated ? (
                <div className="header__drawerAvatarWrap">
                  <Avatar className="header__avatar" size={40}>
                    <UserOutlined />
                  </Avatar>
                </div>
              ) : (
                <>
                  <Button
                    type="primary"
                    htmlType="button"
                    block
                    className="header__authBtn"
                    onClick={() => openAuth("login")}
                  >
                    Đăng nhập
                  </Button>
                  <Button
                    type="default"
                    block
                    className="header__registerBtn"
                    onClick={() => openAuth("register")}
                  >
                    Tạo tài khoản
                  </Button>
                </>
              )}
            </div>
            {navItems.map((item) => (
              <Link
                key={item.href + item.label + "-drawer"}
                href={item.href}
                className="header__drawerLink"
                onClick={() => setDrawerOpen(false)}
              >
                {item.label}
              </Link>
            ))}
          </Drawer>
        </div>
      </header>

      <AuthModal
        open={authOpen}
        onClose={() => setAuthOpen(false)}
        mode={authMode}
        onModeChange={setAuthMode}
        onAuthSuccess={() => setIsAuthenticated(true)}
      />
    </>
  );
}
