import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lets the dev server be opened as http://127.0.0.1:3000 as well as localhost.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
