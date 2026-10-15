/** Keep server extensions and historical metadata when a structured preview updates known fields. */
export function quoteObject(value: unknown): Record<string, unknown> | null {
 try { const parsed = typeof value === "string" ? JSON.parse(value) : value; return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : null; } catch { return null; }
}
export function mergeQuoteDraft(previous:unknown,next:Record<string,unknown>):Record<string,unknown> {
 const old=quoteObject(previous)??{};const result={...old,...next};
 for(const key of ["plans","payment_milestones"]){const items=Array.isArray(old[key])?old[key]:[];if(Array.isArray(next[key]))result[key]=next[key].map((item,i)=>({...quoteObject(items[i]),...quoteObject(item)}));}
 return result;
}
