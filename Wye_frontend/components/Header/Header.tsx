"use client";

import { useState } from "react";
import Link from "next/link";
import { Button, Drawer } from "antd";
import { MenuOutlined } from "@ant-design/icons";
import "./Header.css";

const navItems = [
  { href: "/", label: "Home" },
  { href: "#", label: "Mood Tracker" },
  { href: "#", label: "Resources" },
  { href: "#", label: "Profile" },
];

export function Header() {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
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

        <Button
          type="text"
          className="header__menuBtn"
          aria-label="Open menu"
          icon={<MenuOutlined />}
          onClick={() => setDrawerOpen(true)}
        />

        <Drawer
          title="Menu"
          placement="right"
          className="header__drawer"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          width={280}
        >
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
  );
}
