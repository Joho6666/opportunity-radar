import type { NextConfig } from "next";
// A production build must not overwrite the running development server's chunks.
const nextConfig: NextConfig = { distDir: process.env.NODE_ENV === "development" ? (process.env.NEXT_DEV_DIST_DIR ?? ".next-dev") : ".next" };
export default nextConfig;
