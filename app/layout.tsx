import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "机会雷达 | Opportunity Radar", description: "让机会主动找到你" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="zh-CN"><body>{children}</body></html>; }
