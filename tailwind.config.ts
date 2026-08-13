import type { Config } from "tailwindcss";
export default { content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./features/**/*.{ts,tsx}"], theme: { extend: { colors: { ink: "#051424", panel: "#0d1c2d", line: "#273647", mist: "#d4e4fa", muted: "#98a9bf", ai: "#818cf8", signal: "#4edea3" }, boxShadow: { glow: "0 0 22px rgb(129 140 248 / .16)" } } }, plugins: [] } satisfies Config;
