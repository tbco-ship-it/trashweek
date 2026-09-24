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
// Richmond next_day with three consecutive holidays 11/25–27: the Wed pickup can't slide onto Thu (holiday) → kept on its
// regular day and flagged unconfirmed; a single Thanksgiving still moves Thu→Fri
setHol(["2026-11-25", "2026-11-26", "2026-11-27"], { policy: "next_day", dates: ["2026-11-25", "2026-11-26", "2026-11-27"] });
check("richmond wed unconfirmed", occurrences({ trash: ["Wed"] }, day("2026-11-22"), 7).map(o => [iso(o.d), o.unconfirmed]), [["2026-11-25", 1]]);
check("richmond mon unchanged", occurrences({ trash: ["Mon"] }, day("2026-11-22"), 7).map(o => [iso(o.d), o.unconfirmed]), [["2026-11-23", 0]]);
setHol(["2026-11-26"], { policy: "next_day", dates: ["2026-11-26"] });
check("thanksgiving thu→fri", occurrences({ trash: ["Thu"] }, day("2026-11-22"), 7).map(o => iso(o.d)), ["2026-11-27"]);
// Philadelphia: twice-weekly zones lose the second trash pickup in a holiday week (MLK Mon 01-19); primary day still slides
setHol(["2026-01-19"], { policy: "next_day", dates: ["2026-01-19"], drop2: true });
check("phila mon+thu holiday week", occurrences({ trash: ["Mon", "Thu"] }, day("2026-01-18"), 7).map(o => iso(o.d)), ["2026-01-20"]);
check("phila wed+sat holiday week", occurrences({ trash: ["Wed", "Sat"] }, day("2026-01-18"), 7).map(o => iso(o.d)), ["2026-01-22"]);
check("phila mon+thu normal week", occurrences({ trash: ["Mon", "Thu"] }, day("2026-01-25"), 7).map(o => iso(o.d)), ["2026-01-26", "2026-01-29"]);
// overrides: a listed holiday without a published make-up day is flagged, not shown as a normal pickup (Charlotte MLK)
setHol(["2026-01-19"], { policy: "overrides", dates: ["2026-01-19"], overrides: [] });
check("override no pair unconfirmed", occurrences({ trash: ["Mon"] }, day("2026-01-18"), 7).map(o => [iso(o.d), o.unconfirmed]), [["2026-01-19", 1]]);
// no_change (Roseville): holidays don't move anything
setHol([], { policy: "no_change", dates: [] });
check("no_change thanksgiving", occurrences({ trash: ["Thu"] }, day("2026-11-22"), 7).map(o => iso(o.d)), ["2026-11-26"]);
// pending (Detroit Christmas not posted yet): Fri 12/25 route stays on its day, flagged; Thu before it untouched
setHol(["2026-11-26"], { policy: "next_day", dates: ["2026-11-26"], pending: ["2026-12-25"] });
check("pending fri unconfirmed", occurrences({ trash: ["Fri"] }, day("2026-12-20"), 7).map(o => [iso(o.d), o.unconfirmed]), [["2026-12-25", 1]]);
check("pending thu untouched", occurrences({ trash: ["Thu"] }, day("2026-12-20"), 7).map(o => [iso(o.d), o.unconfirmed]), [["2026-12-24", 0]]);
// Madison: New Year's Eve Thu 12/31 slides Thursday onto Fri 1/1/2027, which is pending → unconfirmed, not a confirmed move
setHol(["2026-12-31"], { policy: "next_day", dates: ["2026-12-31"], pending: ["2027-01-01"] });
check("slide onto pending", occurrences({ trash: ["Thu"] }, day("2026-12-27"), 7).map(o => [iso(o.d), o.unconfirmed]), [["2026-12-31", 1]]);
// unknown: no shifting, no invented federal list
setHol([], null);
check("unknown labor day", occurrences({ trash: ["Mon"] }, day("2026-09-06"), 7).map(o => iso(o.d)), ["2026-09-07"]);
console.log(bad ? `${bad} failures` : "all date tests pass"); process.exit(bad ? 1 : 0);
