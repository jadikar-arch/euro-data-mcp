# AIxona — AI directory (EN / UZ / RU)

One place to find AI models, tools, GitHub repositories, courses and useful websites.
The interface and every description exist in English, Uzbek (Latin) and Russian,
and search matches all three languages at once.

Plain static site: no build step, no server, no dependencies.

```
ai-hub/
  index.html   page skeleton
  styles.css   design (light + dark theme)
  i18n.js      interface text in en / uz / ru
  data.js      the catalogue — edit this to add resources
  app.js       search, category tabs, price filter, language switch
```

## Run locally

Open `index.html` in a browser, or:

```bash
cd ai-hub && python3 -m http.server 8000   # then open http://localhost:8000
```

## Add a resource

Copy any entry in `data.js` and fill it in:

```js
{ type: "tool",            // model | tool | repo | learn | site
  name: "Example", by: "Company", url: "https://example.com",
  price: "freemium",       // free | freemium | paid | open
  tags: ["chat", "code"],  // keys from i18n.js → tags
  d: { en: "…", uz: "…", ru: "…" } }
```

A new tag needs a label in all three languages in `i18n.js`.

## Features

- Language switch (EN / UZ / RU), remembered per browser; first visit follows the browser language
- Search across names, companies, tags and all three translations (`/` focuses search, `Esc` clears)
- Category tabs with live counts; links like `#models`, `#tools`, `#repos`, `#learning`, `#websites`
- Price filter: free, free plan, paid, open source
- Click a tag to search by it

## Publish

Any static host works: GitHub Pages (Settings → Pages, folder `/ai-hub`), Netlify, Cloudflare Pages or Vercel.
