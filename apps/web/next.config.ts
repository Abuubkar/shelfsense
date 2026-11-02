import type { NextConfig } from "next";

// The browser calls /api/*, which Next forwards to the Shelfsense API: same origin, so the API needs no CORS.
const API = process.env.SHELFSENSE_API ?? "http://localhost:8020";

const config: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/:path*` }];
  },
};

export default config;
