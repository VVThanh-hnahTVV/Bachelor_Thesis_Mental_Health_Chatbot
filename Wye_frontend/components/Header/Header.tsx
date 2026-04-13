"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button, Drawer } from "antd";
import { MenuOutlined } from "@ant-design/icons";
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

  useEffect(() => {
    console.log("[Wye Header] mounted (client JS đang chạy)");
  }, []);

  useEffect(() => {
    console.log("[Wye Header] authOpen =", authOpen, "authMode =", authMode);
  }, [authOpen, authMode]);

  const openAuth = (mode: "login" | "register") => {
    console.log("[Wye Header] openAuth called, mode =", mode);
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
            <Button
              type="primary"
              htmlType="button"
              className="header__authBtn"
              onClick={(e) => {
                console.log("[Wye Header] Đăng nhập button onClick", e.type);
                openAuth("login");
              }}
            >
              Đăng nhập
            </Button>
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
      />
    </>
  );
}
