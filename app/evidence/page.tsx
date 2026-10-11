"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, ExternalLink, FileJson, Loader2, RefreshCw, Upload } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Button, EmptyState, PageHeader, Panel } from "@/components/ui";
import {
  EVIDENCE_CATEGORIES,
  fetchEvidence,
  parseEvidenceImport,
  uploadEvidence,
  type EvidenceCategory,
  type EvidenceRecord,
} from "@/lib/evidence-client";

const labels: Record<EvidenceCategory, string> = { buyer: "Buyer", content: "Content", market: "Market" };

function formatDate(value: string | null) {
  if (!value) return "Not provided";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function EvidenceCard({ record }: { record: EvidenceRecord }) {
  return (
    <article className="rounded-md border border-line bg-[#091b2d] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-indigo-400/40 bg-indigo-400/10 px-2 py-1 text-xs text-indigo-200">{labels[record.category]}</span>
            <span className="rounded-full border border-amber-400/40 bg-amber-400/10 px-2 py-1 text-xs text-amber-200">Unverified</span>
          </div>
          <p className="mt-3 text-sm font-medium text-mist">{record.source}</p>
        </div>
        <a className="inline-flex items-center gap-1 text-xs text-indigo-300 hover:text-white" href={record.url} target="_blank" rel="noreferrer">
          Open source <ExternalLink size={13} />
        </a>
      </div>
      <p className="mt-4 whitespace-pre-wrap text-sm leading-6 text-slate-200">{record.raw_text}</p>
      <dl className="mt-5 grid gap-3 border-t border-line pt-4 text-xs sm:grid-cols-3">
        <div><dt className="text-muted">Published</dt><dd className="mt-1 text-slate-300">{formatDate(record.published_at)}</dd></div>
        <div><dt className="text-muted">Captured</dt><dd className="mt-1 text-slate-300">{formatDate(record.captured_at)}</dd></div>
        <div><dt className="text-muted">Payment signal</dt><dd className="mt-1 text-signal">{record.payment_signal ?? "None recorded"}</dd></div>
      </dl>
    </article>
  );
}

function EvidenceInbox() {
  const [category, setCategory] = useState<EvidenceCategory>("buyer");
  const [records, setRecords] = useState<EvidenceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importText, setImportText] = useState("");
  const [importState, setImportState] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async (nextCategory = category) => {
    setLoading(true);
    setError(null);
    try { setRecords(await fetchEvidence(nextCategory)); }
    catch (reason) { setRecords([]); setError(reason instanceof Error ? reason.message : "Could not load evidence."); }
    finally { setLoading(false); }
  }, [category]);

  useEffect(() => { void load(); }, [load]);

  async function importEvidence() {
    setImportState(null);
    try {
      const items = parseEvidenceImport(importText);
      const result = await uploadEvidence(`frontend-${Date.now()}`, items);
      setImportText("");
      setImportState(`Imported ${result.inserted} record${result.inserted === 1 ? "" : "s"}; ${result.duplicates} duplicate${result.duplicates === 1 ? "" : "s"}.`);
      await load();
    } catch (reason) { setImportState(reason instanceof Error ? reason.message : "Could not import evidence."); }
  }

  async function readFile(file: File) {
    setImportState(null);
    try { setImportText(await file.text()); }
    catch { setImportState("Could not read that file."); }
  }

  return (
    <>
      <PageHeader title="Evidence inbox" description="Raw signals from the intelligence API. Every record is shown as unverified until reviewed." action={<Button variant="secondary" onClick={() => void load()} disabled={loading}><RefreshCw size={15} className={loading ? "animate-spin" : ""} /> Refresh</Button>} />
      <div className="mb-6 flex flex-wrap gap-2" role="tablist" aria-label="Evidence categories">
        {EVIDENCE_CATEGORIES.map((item) => <button key={item} role="tab" aria-selected={category === item} onClick={() => setCategory(item)} className={`rounded px-4 py-2 text-sm transition ${category === item ? "bg-ai text-white" : "bg-panel text-muted hover:text-mist"}`}>{labels[item]}</button>)}
      </div>
      <Panel className="mb-6 p-5">
        <div className="flex items-center gap-2"><FileJson size={17} className="text-indigo-300" /><h2 className="font-medium text-mist">Import evidence JSON</h2></div>
        <p className="mt-1 text-xs text-muted">Paste the API-shaped JSON array or load a .json file. Nothing is added until you submit it.</p>
        <textarea value={importText} onChange={(event) => setImportText(event.target.value)} placeholder='[{"source":"...","url":"https://...","raw_text":"..."}]' className="mt-4 min-h-28 w-full rounded border border-line bg-ink p-3 font-mono text-xs text-slate-200 outline-none focus:border-indigo-400" aria-label="Evidence JSON" />
        <div className="mt-3 flex flex-wrap items-center gap-3"><input ref={fileInput} type="file" accept="application/json,.json" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) void readFile(file); }} /><Button variant="secondary" onClick={() => fileInput.current?.click()}><Upload size={15} /> Load JSON file</Button><Button onClick={() => void importEvidence()} disabled={!importText.trim()}>Submit import</Button>{importState && <span className="text-sm text-muted">{importState}</span>}</div>
      </Panel>
      {loading && <Panel className="flex items-center justify-center gap-2 p-10 text-sm text-muted"><Loader2 className="animate-spin" size={18} /> Loading evidence…</Panel>}
      {!loading && error && <Panel className="border-red-400/30 p-6"><div className="flex items-start gap-3 text-red-200"><AlertCircle size={19} className="mt-0.5 shrink-0" /><div><p className="font-medium">Could not load evidence</p><p className="mt-1 text-sm text-red-200/80">{error}</p><Button className="mt-4" variant="secondary" onClick={() => void load()}>Try again</Button></div></div></Panel>}
      {!loading && !error && records.length === 0 && <EmptyState title={`No ${labels[category].toLowerCase()} evidence yet`}><p className="text-sm text-muted">The API returned no records for this category. Import verified source data above or try another category.</p></EmptyState>}
      {!loading && !error && records.length > 0 && <div className="space-y-4">{records.map((record) => <EvidenceCard key={record.evidence_id} record={record} />)}</div>}
    </>
  );
}

export default function Page() { return <AppShell><EvidenceInbox /></AppShell>; }
