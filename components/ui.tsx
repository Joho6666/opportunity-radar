"use client";
import { cn } from "@/lib/utils";
import { useRef, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
export function Button({ children, className, variant = "primary", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" }) {
  const variants = { primary: "bg-ai text-white hover:bg-indigo-700", secondary: "border border-line bg-white text-mist hover:bg-slate-50", ghost: "text-muted hover:bg-slate-100 hover:text-mist" };
  return <button type="button" className={cn("inline-flex min-h-10 items-center justify-center gap-2 rounded-md px-3 text-sm font-medium transition-colors disabled:opacity-50", variants[variant], className)} {...props}>{children}</button>;
}
export function Panel({ children, className }: { children: ReactNode; className?: string }) { return <section className={cn("rounded-lg border border-line bg-panel", className)}>{children}</section>; }
export function PageHeader({ title, description, action, compact = false }: { title: string; description?: string; action?: ReactNode; compact?: boolean }) { return <div className={cn("flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between",compact?"mb-3":"mb-5")}><div className="min-w-0"><h1 className="text-2xl font-semibold tracking-tight text-mist">{title}</h1>{description && <p className="mt-1 text-sm leading-6 text-muted">{description}</p>}</div>{action && <div className="shrink-0">{action}</div>}</div>; }
export function MetricCard({ label, value, hint, tone = "default" }: { label: string; value: string | number; hint?: string; tone?: "default" | "ai" | "good" }) { return <Panel className="p-4"><p className="text-xs font-medium text-muted">{label}</p><p className={cn("mono mt-2 text-2xl font-semibold", tone === "ai" && "text-ai", tone === "good" && "text-signal")}>{value}</p>{hint && <p className="mt-1 text-xs leading-5 text-muted">{hint}</p>}</Panel>; }
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) { return <Panel className="p-8 text-center"><p className="font-medium text-mist">{title}</p>{children && <div className="mt-3 text-sm text-muted">{children}</div>}</Panel>; }
export function DetailDrawer({ open, onClose, title, children, className }: { open: boolean; onClose: () => void; title: string; children: ReactNode; className?: string }) {
  const previousFocus=useRef<HTMLElement|null>(null);
  return <Dialog.Root open={open} onOpenChange={v=>{if(!v)onClose();}}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-slate-900/30"/><Dialog.Content onOpenAutoFocus={()=>{previousFocus.current=document.activeElement as HTMLElement;}} onCloseAutoFocus={e=>{e.preventDefault();previousFocus.current?.focus({preventScroll:true});}} aria-describedby={undefined} className={cn("fixed inset-y-0 right-0 z-50 flex w-full flex-col overflow-y-auto bg-white shadow-xl sm:max-w-xl",className)}><div className="sticky top-0 z-10 flex min-h-14 items-center justify-between gap-3 border-b border-line bg-white px-4"><Dialog.Title className="font-semibold">{title}</Dialog.Title><Dialog.Close asChild><Button variant="ghost" aria-label="关闭详情"><X size={18}/></Button></Dialog.Close></div>{children}</Dialog.Content></Dialog.Portal></Dialog.Root>;
}
