import type { NextConfig } from "next";

// The browser calls /api/*, which Next forwards to the Shelfsense API: same origin, so the API needs no CORS.
const API = process.env.SHELFSENSE_API ?? "http://localhost:8020";

const config: NextConfig = {
  // A self-contained server for the Docker image (apps/web/Dockerfile).
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/:path*` }];
  },
};

export default config;
