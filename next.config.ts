import type { NextConfig } from "next";
// A production build must not overwrite the running development server's chunks.
const nextConfig: NextConfig = { distDir: process.env.NODE_ENV === "development" ? ".next-dev" : ".next" };
export default nextConfig;
