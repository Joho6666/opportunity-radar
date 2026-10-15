import type { EvidenceCategory } from "./evidence-client";
import type { SortMode, StatusFilter } from "./evidence-view";
export type EvidenceQuery={category:EvidenceCategory;status:StatusFilter;q:string;sort:SortMode;source:string|null;selected:string|null};
export function parseEvidenceQuery(search:string):EvidenceQuery {
 const p=new URLSearchParams(search);
 const one=<T extends string>(key:string,allowed:T[],fallback:T):T=>allowed.includes(p.get(key) as T)?p.get(key) as T:fallback;
 return {category:one("category",["buyer","seller","job","content","market"],"buyer"),status:one("status",["pending","verified","invalidated","all"],"pending"),sort:one("sort",["lead","hot","grade","latest"],"lead"),q:p.get("q")??"",source:p.get("source"),selected:p.get("selected")};
}
