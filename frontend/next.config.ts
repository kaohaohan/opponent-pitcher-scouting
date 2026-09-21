import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  agentRules: false,
  reactStrictMode: true,
  async rewrites() {
    const fastApiBaseUrl = process.env.FASTAPI_BASE_URL ?? "http://127.0.0.1:8000";

    return [
      {
        source: "/backend/:path*",
        destination: `${fastApiBaseUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
