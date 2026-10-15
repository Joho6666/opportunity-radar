import { expect, it } from "vitest";
import { parseEvidenceQuery } from "../lib/evidence-query";
it("restores shareable filters and selection without putting private drafts in state",()=>{
 expect(parseEvidenceQuery("?category=job&status=all&source=github&sort=latest&selected=e123&q=Word&notes=private")).toEqual({category:"job",status:"all",source:"github",sort:"latest",selected:"e123",q:"Word"});
});
it("rejects unknown filter values while preserving encoded search text",()=>{
 expect(parseEvidenceQuery("?category=bad&status=bad&sort=bad&q=%E6%8E%92%E7%89%88")).toEqual({category:"buyer",status:"pending",sort:"lead",q:"排版",source:null,selected:null});
});
