import { expect, it } from "vitest";
import { mergeQuoteDraft, quoteObject } from "../lib/quote-draft";
it("keeps legacy fields when a calculated preview updates a quote",()=>{
 const old={customTerms:"retain me",plans:[{name:"基础版",price:10,customLicense:"A"}]};
 expect(mergeQuoteDraft(JSON.stringify(old),{plans:[{name:"基础版",price:20}],valid_until:"2030-01-01"})).toEqual({customTerms:"retain me",plans:[{name:"基础版",price:20,customLicense:"A"}],valid_until:"2030-01-01"});
});
it("handles unsupported historical drafts without destroying their raw content",()=>{
 expect(quoteObject("legacy text")).toBeNull();expect(quoteObject("[]")).toBeNull();expect(quoteObject('{"legacy":"value"}')).toEqual({legacy:"value"});
});
it("preserves extension fields on existing payment nodes",()=>{
 expect(mergeQuoteDraft({payment_milestones:[{label:"deposit",percent:30,invoice:"retain"}]},{payment_milestones:[{label:"deposit",percent:40}]})).toEqual({payment_milestones:[{label:"deposit",percent:40,invoice:"retain"}]});
});
