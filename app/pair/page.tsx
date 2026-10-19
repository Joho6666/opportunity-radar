import { redirect } from "next/navigation";

export default function PairPage() {
  redirect(process.env.NEXT_PUBLIC_APP_MODE === "local" ? "/dashboard" : "/login");
}
