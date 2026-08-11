import type { NextConfig } from "next";

const proxyTarget = process.env.NEXT_PROXY_TARGET || "http://localhost:8080";

const nextConfig: NextConfig = {
  /* config options here */
  reactCompiler: true,
  experimental: {
    proxyTimeout: 120_000, // 2 minutes — backend LLM calls can take >30s
  },
  async rewrites() {
    return {
      beforeFiles: [
        {
          source: "/api/:path*",
          destination: `${proxyTarget}/:path*`,
        },
        {
          source: "/demo/:path*",
          destination: `${proxyTarget}/demo/:path*`,
        },
        {
          source: "/ping/:path*",
          destination: `${proxyTarget}/ping/:path*`,
        },
      ],
    };
  },
};

export default nextConfig;
