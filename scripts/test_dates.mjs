// Holiday-engine regression: OKC Labor Day 09-07 → 09-09; Seattle Thu→Fri on 2026-01-02 (query on the moved day); Miami-Dade skips to next regular day; unknown = no shifting.
import { readFileSync } from "node:fs";
const src = readFileSync(new URL("../static/app.js", import.meta.url), "utf8");
const body = src.slice(src.indexOf("const DAYS"), src.indexOf("// Home: the first result"));
const env = { document: { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [] } };
const fn = new Function("document", body + "\nreturn { setHol, occurrences, iso };");
const { setHol, occurrences, iso } = fn(env.document);
const day = s => new Date(s + "T00:00:00");
let bad = 0;
const check = (name, got, want) => { const g = JSON.stringify(got), w = JSON.stringify(want); if (g !== w) { bad++; console.log("FAIL", name, g, "expected", w); } };
// OKC overrides
setHol(["2026-09-07"], { policy: "overrides", dates: ["2026-09-07"], overrides: [["2026-09-07", "2026-09-09"]] });
check("okc labor day", occurrences({ trash: ["Mon"] }, day("2026-09-06"), 7).map(o => iso(o.d)), ["2026-09-09"]);
check("okc tuesday unchanged", occurrences({ trash: ["Tue"] }, day("2026-09-06"), 7).map(o => iso(o.d)), ["2026-09-08"]);
// Seattle next_day, queried on the moved day itself
setHol(["2026-01-01"], { policy: "next_day", dates: ["2026-01-01"] });
check("seattle thu→fri seen on fri", occurrences({ trash: ["Thu"] }, day("2026-01-02"), 3).map(o => iso(o.d)), ["2026-01-02"]);
check("seattle fri→sat", occurrences({ trash: ["Fri"] }, day("2025-12-28"), 8).map(o => iso(o.d)), ["2026-01-03"]);
// Miami-Dade skip
setHol(["2026-12-25"], { policy: "skip", dates: ["2026-12-25"] });
check("miami skip fri", occurrences({ trash: ["Tue", "Fri"] }, day("2026-12-21"), 10).map(o => iso(o.d)), ["2026-12-22", "2026-12-29"]);
// unknown: no shifting, no invented federal list
setHol([], null);
check("unknown labor day", occurrences({ trash: ["Mon"] }, day("2026-09-06"), 7).map(o => iso(o.d)), ["2026-09-07"]);
console.log(bad ? `${bad} failures` : "all date tests pass"); process.exit(bad ? 1 : 0);
