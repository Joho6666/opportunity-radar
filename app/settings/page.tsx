import { AppShell } from "@/components/app-shell";
import { PageHeader, Panel } from "@/components/ui";
export default function Settings(){return <AppShell><PageHeader title="设置" description="这些设置目前仅用于前端演示。"/><div className="max-w-3xl space-y-3">{["账户","通知","雷达默认设置","显示设置","数据设置"].map(x=><Panel className="flex items-center justify-between p-5" key={x}><span className="font-medium">{x}</span><span className="text-sm text-muted">即将支持</span></Panel>)}</div></AppShell>}
