import { AppShell } from "@/components/app-shell";
import { Dashboard } from "@/features/dashboard";
import LocalDashboard from "@/features/local-dashboard";
export default function Page() { return process.env.NEXT_PUBLIC_APP_MODE === "local" ? <LocalDashboard/> : <AppShell><Dashboard/></AppShell>; }
