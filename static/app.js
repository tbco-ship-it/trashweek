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
  const HOL = new Set(['2026-01-01','2026-05-25','2026-07-04','2026-09-07','2026-11-26','2026-12-25','2027-01-01']); // widely observed; city pages link the official list
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
    for (let i = 0; i < n; i++) {
      const d = addDays(from, i);
      for (const k of KINDS) if (sched[k] && on(sched[k], d)) { const s = holidayShift(d); out.push({ k, d: addDays(d, s), shifted: s, base: d }); }
    }
    return out;
  }
  function render(sched, name, root, link) {
    const occ = occurrences(sched, now, 14).sort((a, b) => a.d - b.d);
    const next = k => occ.find(o => o.k === k);
    const today = occ.filter(o => iso(o.d) === iso(now)), tomorrow = occ.filter(o => iso(o.d) === iso(addDays(now, 1)));
    const lbl = o => LABEL[o.k];
    let head, cls = 'balanced';
    if (tomorrow.length) head = 'Tomorrow: ' + [...new Set(tomorrow.map(lbl))].join(' + ');
    else if (today.length) head = 'Today: ' + [...new Set(today.map(lbl))].join(' + ');
    else { const nx = occ[0]; head = nx ? `Next: ${lbl(nx)} ${rel(nx.d)}` : 'No pickup scheduled'; cls = 'quiet'; }
    const sub = today.length ? `Today (${md(now)}): ${[...new Set(today.map(lbl))].join(' + ')} — have it out by 6–7 am.` : `Today (${md(now)}): no pickup.`;
    const upcoming = KINDS.filter(k => sched[k] && sched[k].length).map(k => { const o = next(k); return `<div class="item"><span class="dot" style="background:${COLOR[k]}"></span><span class="txt"><b>${LABEL[k]}</b><span class="tsub">${(sched[k] || []).map(x => LONG[x]).join(' & ')}${k === 'recycling' && sched.recycling_week ? ` · week ${sched.recycling_week}` : ''}</span>${o && o.shifted ? '<span class="tsub">holiday week: one day late</span>' : ''}</span><span class="when">${o ? rel(o.d) : '—'}</span></div>`; }).join('');
    const week = Array.from({ length: 7 }, (_, i) => { const d = addDays(now, i); const ks = [...new Set(occ.filter(o => iso(o.d) === iso(d)).map(o => o.k))]; return `<div class="day${i === 0 ? ' today' : ''}"><span class="dow">${i === 0 ? 'Today' : DAYS[d.getDay()]}</span><span class="dnum">${d.getDate()}</span><span class="dots">${ks.map(k => `<span class="tag" style="background:${TAG[k]}">${LABEL[k].split(' ')[0]}</span>`).join('')}</span></div>`; }).join('');
    if (root) root.innerHTML = `<section class="sheet ${cls}"><p class="sheet-label">${name}</p><div class="sheet-num"><span class="num small-num">${head}</span></div><p class="sheet-title">${sub}</p><div class="stack">${upcoming}</div><p class="sheet-actions"><a class="next" href="${link}">Zone page &amp; calendar file</a></p></section><div class="week">${week}</div>`;
    else { const sheet = $('today'); sheet.classList.remove('balanced', 'quiet'); sheet.classList.add(cls); $('headline').textContent = head; $('sub').textContent = sub; $('upcoming').innerHTML = upcoming; $('week').innerHTML = week; }
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
  if (sched) { const S = JSON.parse(sched.textContent); render(S.schedule, S.name, null); $('ics').href = ics(S.schedule, S.name); return; }

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
  function slugOf(cityState) { const s = (cityState || '').toLowerCase(); return cities.find(c => s.includes(c.city.toLowerCase().split(',')[0]) || s.includes(c.city.toLowerCase().replace(' county', '')))?.slug; }
  async function lookup() {
    const q = input.value.trim(); if (!q) return say('Type a street address first.');
    say('Locating…');
    try {
      const j = await jsonp('https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?benchmark=Public_AR_Current&format=jsonp&address=' + encodeURIComponent(q + (input.dataset.cityname && !/[a-z]{2}\s*$/i.test(q) ? ', ' + input.dataset.cityname : '')));
      const m = j.result?.addressMatches?.[0];
      if (!m) return say('No match from the Census geocoder. Add the city and state, e.g. "123 Main St, Seattle WA".');
      const { x: lng, y: lat } = m.coordinates;
      const slug = input.dataset.city || slugOf(m.matchedAddress);
      if (!slug) return say(`Found the address (${m.matchedAddress}) but that city isn't covered yet. Cities we have are listed below.`);
      const geo = await loadGeo(slug), z = findZone(geo, lng, lat);
      const cname = cities.find(c => c.slug === slug);
      if (!z) return say(`${m.matchedAddress} is outside ${cname.city}'s published collection zones (unincorporated area or private hauler).`);
      say(`Matched ${m.matchedAddress}`);
      render(z.s, `${cname.city} · zone ${z.z}`, out, `${base}${slug}/zone/${z.z.toLowerCase().replace(/ /g, '-')}/`);
      localStorage.setItem('trashweek.last', JSON.stringify({ slug, z: z.z }));
    } catch (e) { say('The geocoder did not answer. Try again in a moment.'); }
  }
  go.addEventListener('click', lookup); input.addEventListener('keydown', e => { if (e.key === 'Enter') lookup(); });
  const last = JSON.parse(localStorage.getItem('trashweek.last') || 'null');
  if (last && (!input.dataset.city || input.dataset.city === last.slug)) { const geo = await loadGeo(last.slug); const z = geo.zones.find(x => x.z === last.z); const c = cities.find(x => x.slug === last.slug); if (z && c) render(z.s, `${c.city} · zone ${z.z}`, out, `${base}${last.slug}/zone/${z.z.toLowerCase().replace(/ /g, '-')}/`); }
})();
