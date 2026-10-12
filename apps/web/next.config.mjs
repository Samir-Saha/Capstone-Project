/** @type {import('next').NextConfig} */
const API_URL = process.env.REPS_API_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: true },
  async rewrites() {
    // The browser only ever talks to this app; requests to /api are forwarded to FastAPI.
    return [
      { source: "/api/:path*", destination: `${API_URL}/api/:path*` },
      { source: "/health", destination: `${API_URL}/health` },
    ];
  },
};

export default nextConfig;
