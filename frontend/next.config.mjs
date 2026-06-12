/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },

  experimental: {
    missingSuspenseWithCSRBailout: false,
    serverComponentsExternalPackages: [
      "@opentelemetry/api",
      "@opentelemetry/sdk-trace-base",
      "@opentelemetry/exporter-trace-otlp-proto",
      "tailwind-merge",
      "clsx",
      "class-variance-authority",
    ],
  },

  skipMiddlewareUrlNormalize: true,

  reactStrictMode: false,

  // Disable image optimization warnings
  images: {
    unoptimized: true,
  },

  // Ignore specific page extensions
  pageExtensions: ["tsx", "ts", "jsx", "js"].filter(
    (ext) => !ext.includes("spec")
  ),

  // Configure webpack
  webpack: (config, { dev, isServer }) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      sharp$: false,
      canvas$: false,
    };

    if (isServer) {
      config.externals = [
        ...(Array.isArray(config.externals) ? config.externals : []),
        "@opentelemetry/api",
        "@opentelemetry/sdk-trace-base",
        "@opentelemetry/exporter-trace-otlp-proto",
        "tailwind-merge",
        "clsx",
        "class-variance-authority",
      ];

      // Avoid stale vendor-chunk refs in dev (e.g. tailwind-merge.js missing)
      if (dev) {
        config.optimization = {
          ...config.optimization,
          splitChunks: false,
        };
      }
    }

    return config;
  },

  // Suppress specific console warnings
  onDemandEntries: {
    // Reduce console noise
    maxInactiveAge: 25 * 1000,
    pagesBufferLength: 2,
  },
};

export default nextConfig;
