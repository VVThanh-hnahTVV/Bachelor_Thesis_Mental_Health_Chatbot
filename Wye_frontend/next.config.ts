import type { NextConfig } from "next";
import path from "path";
import { fileURLToPath } from "url";

/** Thư mục Wye_frontend — tránh Next coi /home/vvt là root khi có nhiều package-lock (webpack tracing + cảnh báo). */
const appDir = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  outputFileTracingRoot: appDir,

  /**
   * Tránh chặn /_next/* khi host khác localhost (ví dụ 127.0.0.1).
   * Mở bằng IP LAN: thêm host vào đây (ví dụ "192.168.1.249").
   */
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
