# Capturing TopCV listings

TopCV is the only source this pipeline cannot fetch itself. DataDome fingerprints the TLS
handshake and header order, so it answers `requests` with **403** and ScraperAPI with
**500**; the premium proxy pool that would get through is not on the free plan. Verified
2026-06-16 and unchanged since.

A real browser gets **HTTP 200 and 50 cards a page** — verified 2026-08-09. So the browser
fetches and the pipeline loads, the same split `topcv_browser_merge.py` already uses for JD
enrichment.

This is a deliberately manual step. Automating a headless browser here would add a heavy
dependency to a pipeline that otherwise runs on `requests`, and it would still be defeated
by DataDome the moment it looked automated.

---

## 1. Capture (in your own Chrome)

Open <https://www.topcv.vn/tim-viec-lam-data-engineer>, press **F12 → Console**, paste:

```js
(async () => {
  const cats = ['ai-engineer','data-analyst','data-engineer','business-intelligence',
                'data-scientist','machine-learning','etl','big-data','data-analytics'];
  const out = {};
  for (const c of cats) {
    out[c] = [];
    for (let page = 1; page <= 3; page++) {
      const u = page === 1 ? `https://www.topcv.vn/tim-viec-lam-${c}`
                           : `https://www.topcv.vn/tim-viec-lam-${c}?page=${page}`;
      const r = await fetch(u, { credentials: 'include' });
      if (r.status !== 200) break;
      const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
      const cards = [...doc.querySelectorAll('.job-item-search-result')];
      if (!cards.length) break;
      for (const card of cards) {
        const a = [...card.querySelectorAll('a')]
          .find(x => (x.textContent || '').trim().length > 5);
        out[c].push({
          job_id: card.getAttribute('data-job-id'),
          title:   (a?.textContent || '').trim().replace(/\s+/g, ' '),
          company: (card.querySelector('.company-name, .company a')?.textContent || '')
                     .trim().replace(/\s+/g, ' '),
          city:    (card.querySelector('.address, .city-text')?.textContent || '')
                     .trim().replace(/\s+/g, ' '),
        });
      }
      if (cards.length < 50) break;
      await new Promise(s => setTimeout(s, 2000));   // same courtesy delay as the pipeline
    }
    await new Promise(s => setTimeout(s, 1500));
  }

  const payload = { captured_at: new Date().toISOString().slice(0, 10), categories: out };
  const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `topcv_listing_${payload.captured_at}.json`;
  a.click();
  console.log('captured', Object.values(out).reduce((n, v) => n + v.length, 0), 'postings');
})();
```

It saves `topcv_listing_<date>.json` to Downloads. A run on 2026-08-09 produced **236
postings**: ai-engineer 79, data-analyst 75, data-engineer 46, business-intelligence 15,
data-scientist 9, machine-learning 4, etl 4, big-data 2, data-analytics 2.

Run it on the same day you run `scrape`, so the snapshot dates line up and CDC compares
like with like.

## 2. Load

```bash
python -m pipeline import-topcv ~/Downloads/topcv_listing_2026-08-09.json
python -m pipeline load --run-date 2026-08-09
```

`import-topcv` writes `data/bronze/topcv/<run_date>.jsonl.gz` exactly like any connector,
so everything downstream — `load`, `silver`, `label`, `gold` — treats TopCV no differently.
Rows are tagged `extra.captured_via = "browser"` so their provenance stays visible.

## 3. Why the categories are what they are

`config/sources.yml` used to search the single word `data`. Measured 2026-08-09 that came
back **74% sales postings**: in a Vietnamese ad "data" usually means the lead list handed to
a salesperson — *"Data Nóng Từ MKT"*, *"Data Sẵn"*.

| category | postings | sales noise |
|---|---:|---:|
| `data` (old) | 447 | **74%** |
| `data-engineer` | 46 | 0% |
| `data-scientist` | 9 | 0% |
| `data-analyst` | 75 | 12% |
| `business-intelligence` | 15 | 20% |

The nine role slugs return **236 real postings against roughly 116** from `data`, for two
extra page fetches. `data-warehouse` is not in the list: it returns zero.
