"use client";

import "@ant-design/v5-patch-for-react-19";
import type { ReactNode } from "react";
import { useEffect } from "react";
import { AntdRegistry } from "@ant-design/nextjs-registry";
import { App, ConfigProvider } from "antd";

type AppProvidersProps = {
  children: ReactNode;
};

export function AppProviders({ children }: AppProvidersProps) {
  useEffect(() => {
    console.log("[Wye AppProviders] mounted, react-19 patch đã load trong chunk này");
  }, []);

  return (
    <AntdRegistry>
      <ConfigProvider
        theme={{
          token: {
            colorPrimary: "#466744",
            borderRadiusLG: 24,
            fontFamily: "var(--font-manrope), system-ui, sans-serif",
          },
        }}
      >
        <App>{children}</App>
      </ConfigProvider>
    </AntdRegistry>
  );
}
