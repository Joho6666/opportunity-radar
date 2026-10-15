import type { Config } from "tailwindcss";
export default { content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./features/**/*.{ts,tsx}"], theme: { extend: { colors: { ink: "#F6F7F9", panel: "#FFFFFF", line: "#E2E8F0", mist: "#111827", muted: "#526072", ai: "#4F46E5", signal: "#047857" }, transitionDuration: { DEFAULT: "150ms" } } }, plugins: [] } satisfies Config;
