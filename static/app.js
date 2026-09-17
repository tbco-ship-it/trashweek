(async function () {
  const cssHref = document.querySelector('link[href*="static/style.css"]').getAttribute('href');
  const v = (cssHref.match(/\?v=([^&]+)/) || [])[1] || '';
  const base = cssHref.replace(/static\/style\.css.*$/, '');
  const $ = id => document.getElementById(id);
  const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const LONG = { Mon: 'Monday', Tue: 'Tuesday', Wed: 'Wednesday', Thu: 'Thursday', Fri: 'Friday', Sat: 'Saturday', Sun: 'Sunday' };
  const KINDS = ['trash', 'recycling', 'yard', 'bulk'];
  const LABEL = { trash: 'Trash', recycling: 'Recycling', yard: 'Yard waste', bulk: 'Bulk items' };
  const COLOR = { trash: '#3182f6', recycling: '#00b06f', yard: '#8b5cf6', bulk: '#ff7a00' };
  const TAG = { ...COLOR, recycling: '#00885a', bulk: '#d95d00' };
  const DEFAULT_HOL = ['2026-01-01','2026-05-25','2026-07-04','2026-09-07','2026-11-26','2026-12-25','2027-01-01']; // fallback when a city's observed list is unknown
  let HOL = new Set(DEFAULT_HOL);
  const setHol = list => { HOL = new Set(list && list.length ? list : DEFAULT_HOL); };
  const now = new Date(); now.setHours(0, 0, 0, 0);
  const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const md = d => `${DAYS[d.getDay()]} ${d.getMonth() + 1}/${d.getDate()}`;
  const rel = d => { const n = Math.round((d - now) / 864e5); return n === 0 ? 'Today' : n === 1 ? 'Tomorrow' : md(d); };
  // holiday slide: if a widely observed holiday falls earlier in the same week (Mon..that day), pickup is one day later
  function holidayShift(d) {
    const dow = d.getDay(); if (dow === 0) return 0;
    for (let i = 1; i <= dow; i++) { const x = addDays(d, -(dow - i)); if (HOL.has(iso(x))) return 1; }
    return 0;
  }
  const on = (days, d) => (days || []).includes(DAYS[d.getDay()]);
  function occurrences(sched, from, n) {
    const out = [];
    if (sched.__events) { const end = addDays(from, n); return sched.__events.filter(o => o.d >= from && o.d < end).map(o => ({ k: o.k, d: o.d, shifted: 0, base: o.d })); }
    for (let i = 0; i < n; i++) {
      const d = addDays(from, i);
      for (const k of KINDS) if (sched[k] && on(sched[k], d)) { const s = holidayShift(d); out.push({ k, d: addDays(d, s), shifted: s, base: d }); }
    }
    return out;
  }
  // Home: the first result ends the landing state — hero + card glide up from centre (FLIP on padding-top) while the hidden sections below are armed to reveal.
  function leaveLanding() {
    const html = document.documentElement; if (!html.classList.contains('landing')) return;
    const stage = $('stage'), hero = stage.firstElementChild;
    const y0 = hero.getBoundingClientRect().top;
    html.classList.remove('landing');
    const dy = y0 - hero.getBoundingClientRect().top;
    if (dy > 0 && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      stage.style.transition = 'none'; stage.style.paddingTop = dy + 'px'; void stage.offsetHeight;
      stage.style.transition = 'padding-top 1s cubic-bezier(.16,1,.3,1)'; stage.style.paddingTop = '0px';
      stage.addEventListener('transitionend', () => { stage.style.transition = ''; stage.style.paddingTop = ''; }, { once: true });
    }
    if (window.__reveal) window.__reveal($('more'), true, 500);
  }
  // In-page links into the hidden part (nav "Cities", the hint) end the landing state first so the anchor jump has a target.
  document.addEventListener('click', e => { const a = e.target.closest('a[href*="#"]'); if (!a || a.origin !== location.origin || a.pathname !== location.pathname) return; const t = document.getElementById(a.hash.slice(1)); if (t && t.closest('#more')) leaveLanding(); });
  function render(sched, name, root, link) {
    const occ = occurrences(sched, now, 14).sort((a, b) => a.d - b.d);
    const occFar = occurrences(sched, now, 60).sort((a, b) => a.d - b.d);
    const next = k => occFar.find(o => o.k === k);
    const KINDS_SHOWN = KINDS.filter(k => sched[k] && (sched[k].length || (sched.__events || []).some(o => o.k === k)));
    const today = occ.filter(o => iso(o.d) === iso(now)), tomorrow = occ.filter(o => iso(o.d) === iso(addDays(now, 1)));
    const lbl = o => LABEL[o.k];
    let head, cls = 'balanced';
    if (tomorrow.length) head = 'Tomorrow: ' + [...new Set(tomorrow.map(lbl))].join(' + ');
    else if (today.length) head = 'Today: ' + [...new Set(today.map(lbl))].join(' + ');
    else { const nx = occ[0]; head = nx ? `Next: ${lbl(nx)} ${rel(nx.d)}` : 'No pickup scheduled'; cls = 'quiet'; }
    const sub = today.length ? `Today (${md(now)}): ${[...new Set(today.map(lbl))].join(' + ')} — have it out by 6–7 am.` : `Today (${md(now)}): no pickup.`;
    const upcoming = KINDS_SHOWN.map(k => { const o = next(k); return `<div class="item"><span class="dot" style="background:${COLOR[k]}"></span><span class="txt"><b>${LABEL[k]}</b><span class="tsub">${(sched[k] || []).map(x => LONG[x]).join(' & ')}${k === 'recycling' && sched.recycling_week ? ` · week ${sched.recycling_week}` : ''}</span>${o && o.shifted ? '<span class="tsub">holiday week: one day late</span>' : ''}</span><span class="when">${o ? rel(o.d) : '—'}</span></div>`; }).join('');
    const week = Array.from({ length: 7 }, (_, i) => { const d = addDays(now, i); const ks = [...new Set(occ.filter(o => iso(o.d) === iso(d)).map(o => o.k))]; return `<div class="day${i === 0 ? ' today' : ''}"><span class="dow">${i === 0 ? 'Today' : DAYS[d.getDay()]}</span><span class="dnum">${d.getDate()}</span><span class="dots">${ks.map(k => `<span class="tag" style="background:${TAG[k]}">${LABEL[k].split(' ')[0]}</span>`).join('')}</span></div>`; }).join('');
    if (root) {
      leaveLanding();
      root.innerHTML = `<section class="sheet ${cls}"><p class="sheet-label">${name}</p><div class="sheet-num"><span class="num small-num">${head}</span></div><p class="sheet-title">${sub}</p><div class="stack">${upcoming}</div><p class="sheet-actions"><a class="next" href="${link}">Zone page &amp; calendar file</a></p></section><div class="week">${week}</div>`;
      // Result rises in Toss-style: label → headline → sub → items → link → week, 90ms apart.
      root.classList.remove('is-in'); root.classList.add('reveal');
      [root.querySelector('.sheet'), ...root.querySelector('.sheet').children, root.querySelector('.week')].forEach((el, i) => { el.classList.add('rv'); el.style.setProperty('--d', (i * 90) + 'ms'); });
      void root.offsetHeight; root.classList.add('is-in');
    } else { const sheet = $('today'); sheet.classList.remove('balanced', 'quiet'); sheet.classList.add(cls); $('headline').textContent = head; $('sub').textContent = sub; $('upcoming').innerHTML = upcoming; $('week').innerHTML = week; }
  }
  function ics(sched, name) {
    const L = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//TrashWeek//EN', 'CALSCALE:GREGORIAN', `X-WR-CALNAME:${name} pickup days`];
    for (const o of occurrences(sched, now, 120)) { const y = iso(o.d).replace(/-/g, ''), n = iso(addDays(o.d, 1)).replace(/-/g, ''); L.push('BEGIN:VEVENT', `UID:${y}-${o.k}@trashweek`, `DTSTAMP:${y}T000000Z`, `DTSTART;VALUE=DATE:${y}`, `DTEND;VALUE=DATE:${n}`, `SUMMARY:${LABEL[o.k]} pickup${o.shifted ? ' (holiday delay)' : ''}`, `DESCRIPTION:${name}`, 'END:VEVENT'); }
    L.push('END:VCALENDAR');
    return 'data:text/calendar;charset=utf-8,' + encodeURIComponent(L.join('\r\n'));
  }
  // holiday tables: fill weekday column
  document.querySelectorAll('td.hday').forEach(td => { const d = new Date(td.dataset.d + 'T00:00:00'); td.textContent = LONG[DAYS[d.getDay()]]; });

  const sched = $('sched');
  if (sched) { const S = JSON.parse(sched.textContent); setHol(S.holidays); render(S.schedule, S.name, null); $('ics').href = ics(S.schedule, S.name); return; }

  const input = $('addr'); if (!input) return;
  const out = $('result'), msg = $('msg'), go = $('go');
  const say = t => { msg.hidden = false; msg.textContent = t; };
  const cities = await (await fetch(base + 'static/cities.json?v=' + v)).json();
  // Census geocoder has no CORS headers but supports JSONP
  const jsonp = url => new Promise((res, rej) => { const cb = 'tw' + Date.now(); const s = document.createElement('script'); window[cb] = d => { delete window[cb]; s.remove(); res(d); }; s.onerror = () => { delete window[cb]; s.remove(); rej(new Error('jsonp')); }; s.src = url + '&callback=' + cb; document.head.appendChild(s); setTimeout(() => { if (window[cb]) { delete window[cb]; s.remove(); rej(new Error('timeout')); } }, 20000); });
  const geoCache = {};
  const loadGeo = async slug => geoCache[slug] || (geoCache[slug] = await (await fetch(base + `static/geo/${slug}.json?v=` + v)).json());
  function inRing(pt, ring) { let inside = false; for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) { const [xi, yi] = ring[i], [xj, yj] = ring[j]; if (((yi > pt[1]) !== (yj > pt[1])) && (pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi)) inside = !inside; } return inside; }
  function findZone(geo, lng, lat) { for (const z of geo.zones) { let hits = 0; for (const r of z.r) if (inRing([lng, lat], r)) hits++; if (hits % 2 === 1) return z; } return null; }
  function slugOf(cityState) { const s = (cityState || '').toLowerCase(); return cities.find(c => s.includes(c.city.toLowerCase().split(',')[0]) || s.includes(c.city.toLowerCase().replace(' county', '')) || (c.aliases || []).some(al => s.includes(al)))?.slug; }
  const API = 'https://api.trashweek.com';
  const DAYNAME = { sunday: 'Sun', monday: 'Mon', tuesday: 'Tue', wednesday: 'Wed', thursday: 'Thu', friday: 'Fri', saturday: 'Sat' };
  async function lookupRecollect(c, q) {
    say('Looking up with ' + c.city + '\u2019s schedule service…');
    const sug = await (await fetch(`${API}/recollect/suggest?area=${encodeURIComponent(c.area)}&q=${encodeURIComponent(q)}`)).json();
    const p = Array.isArray(sug) ? sug.find(x => x.place_id) : null;
    if (!p) return say(`No address match in ${c.city}\u2019s schedule service. Try the house number and street only, e.g. "10000 Leeway Tr".`);
    const after = iso(now), before = iso(addDays(now, 42));
    const ev = await (await fetch(`${API}/recollect/events?area=${encodeURIComponent(c.area)}&place=${p.place_id}&service=${c.service}&after=${after}&before=${before}`)).json();
    const events = ev.events || [];
    if (!events.length) return say(`${p.name}: found, but the service returned no pickups for this address (may be a non-residential or private-hauler address).`);
    // derive weekday lists per kind from the returned events
    const sched = {}; const kindOf = f => /recycl/i.test(f) ? 'recycling' : /yard|organic|compost|brush|trimming/i.test(f) ? 'yard' : /bulk|junk|heavy|noncarted/i.test(f) ? 'bulk' : /garbage|trash|refuse|waste/i.test(f) ? 'trash' : null;
    for (const e of events) { const d = new Date(e.day + 'T00:00:00'); for (const f of (e.flags || [])) { const k = kindOf(f.name || f.subject || ''); if (!k) continue; (sched[k] = sched[k] || new Set()).add(DAYS[d.getDay()]); } }
    const s = {}; for (const k in sched) s[k] = [...sched[k]];
    // ReCollect already returns real dates (holiday shifts and monthly bulk included) — use them as-is
    s.__events = []; for (const e of events) { const d = new Date(e.day + 'T00:00:00'); for (const f of (e.flags || [])) { const k = kindOf(f.name || f.subject || ''); if (k && !s.__events.some(o => o.k === k && iso(o.d) === e.day)) s.__events.push({ k, d }); } }
    say(`Matched ${p.name}`);
    render(s, `${c.city} · ${p.name.split(',')[0]}`, out, `${base}${c.slug}/`);
    localStorage.setItem('trashweek.last', JSON.stringify({ slug: c.slug, q }));
  }
  async function lookup() {
    const q = input.value.trim(); if (!q) return say('Type a street address first.');
    const rc = input.dataset.kind === 'recollect' ? cities.find(c => c.slug === input.dataset.city) : cities.find(c => c.kind === 'recollect' && (new RegExp('\\b' + c.city.split(' ')[0] + '\\b', 'i').test(q) || (c.aliases || []).some(al => q.toLowerCase().includes(al))));
    if (rc) { try { return await lookupRecollect(rc, q.replace(new RegExp(',?\\s*' + rc.city + '.*$', 'i'), '')); } catch (e) { return say('The schedule service did not answer. Try again in a moment.'); } }
    say('Locating…');
    try {
      const j = await jsonp('https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?benchmark=Public_AR_Current&format=jsonp&address=' + encodeURIComponent(q + (input.dataset.cityname && !/[a-z]{2}\s*$/i.test(q) ? ', ' + input.dataset.cityname : '')));
      const m = j.result?.addressMatches?.[0];
      if (!m) return say('No match from the Census geocoder. Add the city and state, e.g. "123 Main St, Seattle WA".');
      const { x: lng, y: lat } = m.coordinates;
      const slug = input.dataset.city || slugOf(m.matchedAddress);
      if (!slug) return say(`Found the address (${m.matchedAddress}) but that city isn't covered yet. Cities we have are listed below.`);
      const geo = await loadGeo(slug), z = findZone(geo, lng, lat); setHol(geo.holidays);
      const cname = cities.find(c => c.slug === slug);
      if (!z) return say(`${m.matchedAddress} is outside ${cname.city}'s published collection zones (unincorporated area or private hauler).`);
      say(`Matched ${m.matchedAddress}`);
      render(z.s, `${cname.city} · zone ${z.z}`, out, `${base}${slug}/zone/${z.u}/`);
      localStorage.setItem('trashweek.last', JSON.stringify({ slug, z: z.z }));
    } catch (e) { say('The geocoder did not answer. Try again in a moment.'); }
  }
  const goIdle = go.textContent;
  const busy = on => { go.disabled = on; go.classList.toggle('busy', on); go.textContent = on ? 'Locating…' : goIdle; };
  const run = async () => { if (go.disabled) return; busy(true); try { await lookup(); } finally { busy(false); } };
  go.addEventListener('click', run); input.addEventListener('keydown', e => { if (e.key === 'Enter') run(); });
  const last = JSON.parse(localStorage.getItem('trashweek.last') || 'null');
  if (last && last.z && (!input.dataset.city || input.dataset.city === last.slug)) {
    const geo = await loadGeo(last.slug); setHol(geo.holidays); const z = geo.zones.find(x => x.z === last.z); const c = cities.find(x => x.slug === last.slug);
    if (z && c) {
      const show = () => render(z.s, `${c.city} · zone ${z.z}`, out, `${base}${last.slug}/zone/${z.u}/`);
      const chip = $('last');
      // Home: nothing pre-filled — the remembered zone is offered as a one-tap chip. City pages show it right away as before.
      if (chip) { $('last-name').textContent = `${c.city} · zone ${z.z}`; chip.hidden = false; chip.addEventListener('click', show); } else show();
    }
  }
})();
