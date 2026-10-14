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
// overrides + skips: the city lists the day as no-collection with no make-up day (Lexington Veterans Day Wed 11/11) — no pickup, not "unconfirmed"
setHol(["2026-11-11"], { policy: "overrides", dates: ["2026-11-11"], overrides: [], skips: ["2026-11-11"] });
check("skips wed no pickup", occurrences({ trash: ["Wed"] }, day("2026-11-08"), 7).map(o => [iso(o.d), o.unconfirmed]), []);
check("skips next wed normal", occurrences({ trash: ["Wed"] }, day("2026-11-08"), 14).map(o => [iso(o.d), o.unconfirmed]), [["2026-11-18", 0]]);
check("skips mon unchanged", occurrences({ trash: ["Mon"] }, day("2026-11-08"), 7).map(o => [iso(o.d), o.unconfirmed]), [["2026-11-09", 0]]);
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
// Partial coverage: only the exact confirmed holiday shifts; dates outside the findings stay on their regular day.
setHol([], { policy: "unknown", partial: true, dates: ["2026-11-26"], rules: [["2026-11-26", "next_day"]] });
check("partial confirmed thu→fri", occurrences({ trash: ["Thu"] }, day("2026-11-22"), 7).map(o => [iso(o.d), o.unconfirmed]), [["2026-11-27", 0]]);
check("partial earlier weekday unchanged", occurrences({ trash: ["Mon"] }, day("2026-11-22"), 7).map(o => [iso(o.d), o.unconfirmed]), [["2026-11-23", 0]]);
// Oxnard's Jan. 1 and Thanksgiving notices delay Thursday routes only; Friday routes stay on their normal date.
setHol(["2026-01-01"], { policy: "next_day", dates: ["2026-01-01"], rules: [["2026-01-01", "thursday_only"]] });
check("oxnard new year thu→fri only", occurrences({ trash: ["Thu"] }, day("2025-12-28"), 7).map(o => [iso(o.d), o.shifted, o.unconfirmed]), [["2026-01-02", 1, 0]]);
check("oxnard new year fri stays fri", occurrences({ trash: ["Fri"] }, day("2025-12-28"), 7).map(o => [iso(o.d), o.shifted, o.unconfirmed]), [["2026-01-02", 0, 0]]);
setHol(["2026-11-26"], { policy: "next_day", dates: ["2026-11-26"], rules: [["2026-11-26", "thursday_only"]] });
check("oxnard thanksgiving thu→fri only", occurrences({ trash: ["Thu"] }, day("2026-11-22"), 7).map(o => [iso(o.d), o.shifted, o.unconfirmed]), [["2026-11-27", 1, 0]]);
check("oxnard thanksgiving fri stays fri", occurrences({ trash: ["Fri"] }, day("2026-11-22"), 7).map(o => [iso(o.d), o.shifted, o.unconfirmed]), [["2026-11-27", 0, 0]]);
// San Francisco's listed TBD date stays scheduled but is not presented as a confirmed pickup change.
setHol([], { policy: "next_day", pending: ["2026-12-25"], rules: [["2026-12-25", "tbd"]] });
check("listed TBD date", occurrences({ trash: ["Fri"] }, day("2026-12-20"), 7).map(o => [iso(o.d), o.unconfirmed]), [["2026-12-25", 1]]);
// Explicit no-change dates do not inherit a city's other date-specific shift rule.
setHol([], { policy: "unknown", partial: true, rules: [["2026-11-11", "no_change"]], noChanges: ["2026-11-11"] });
check("partial explicit no-change", occurrences({ trash: ["Wed"] }, day("2026-11-08"), 7).map(o => [iso(o.d), o.unconfirmed]), [["2026-11-11", 0]]);
// An unresolved date is retained on the regular day and marked unconfirmed.
setHol([], { policy: "unknown", partial: true, rules: [["2026-12-25", "unverified"]], unverified: ["2026-12-25"] });
check("partial unverified date", occurrences({ trash: ["Fri"] }, day("2026-12-20"), 7).map(o => [iso(o.d), o.unconfirmed]), [["2026-12-25", 1]]);
// New Orleans Jan. 1 has a district exception that current weekday zones cannot represent: retain regular dates and flag the holiday week.
setHol([], { policy: "unknown", partial: true, rules: [["2026-01-01", "unverified"]], unverified: ["2026-01-01"] });
check("new-orleans thu stays unverified", occurrences({ trash: ["Thu"] }, day("2025-12-28"), 7).map(o => [iso(o.d), o.unconfirmed]), [["2026-01-01", 1]]);
check("new-orleans fri stays unshifted", occurrences({ trash: ["Fri"] }, day("2025-12-28"), 7).map(o => [iso(o.d), o.unconfirmed]), [["2026-01-02", 1]]);
// Richardson's confirmed no-service dates map to skip, while its explicit no-change date stays scheduled.
setHol([], { policy: "unknown", partial: true, rules: [["2026-12-25", "skip"], ["2026-11-11", "no_change"]], skips: ["2026-12-25"], noChanges: ["2026-11-11"] });
check("partial skip exact date", occurrences({ trash: ["Fri"] }, day("2026-12-20"), 7).map(o => [iso(o.d), o.unconfirmed]), []);
check("skip city no-change exception", occurrences({ trash: ["Wed"] }, day("2026-11-08"), 7).map(o => [iso(o.d), o.unconfirmed]), [["2026-11-11", 0]]);
console.log(bad ? `${bad} failures` : "all date tests pass"); process.exit(bad ? 1 : 0);
