**Homepage presentation review — 21 September 2026**

Reference: `design-reference/abdeen-watches (1)/src/components/` and its styles. Existing homepage audited in Chrome before edits. Only Django templates, homepage styles, static assets and vanilla JavaScript were changed. No settings, views, catalogue queries, range membership, product data, imports, basket or checkout logic were changed.

**Audit before edits**

- The original gray header, separate Oscar account strip, text wordmark and basic navigation differed from the reference's compact white logo header, utility strip and mobile menu.
- The original hero photograph was externally hosted and overly dark. No dedicated media container existed for a future video.
- Live categories had placeholder artwork. Long brand names and mobile product cards needed deliberate sizing.
- Decorative hearts looked interactive but had no behavior. The newsletter was a disabled placeholder form.
- The editorial banner reused the hero photo. Footer content consisted only of the shop name.
- The reference contains demo inventory, storefront/contact details and commercial guarantees. These were not copied into the real shop.

**Result**

The homepage follows the reference's red/black palette, Plus Jakarta Sans typography, editorial Playfair headings, white cards, dark hero/promo and section rhythm. Real logo assets are used in a sticky responsive header and dark footer. Native details panels provide menu/search navigation even without JavaScript; JavaScript adds Escape/outside-click dismissal and focus management. Search submits to Oscar's existing search endpoint. Basket and account links use existing Oscar routes and the bag count comes from the existing request basket.

Photography and the two variable fonts are hosted locally. Category uploads take precedence; the two live departments have static editorial fallbacks. Brand names/links, category links, product titles/images/prices/availability, and both manually curated ranges still come from the existing context. Two Best Sellers and two New Arrivals were present during validation; their exact titles, URLs and prices matched the before-edit browser snapshot.

The hero has a separate media container and image poster suitable for a future video. When a video is supplied, add it to that container with the current image as its poster, a pause control, and reduced-motion/data-saving handling. No video is currently downloaded or played.

**Verification**

- Chrome: 1440 × 900, 768 × 900 (tablet), 390 × 900 and 320 × 900.
- All four: no horizontal or element overflow; every image decoded; no JavaScript exceptions; no broken section anchors; menu/search behavior and all three existing product filters passed.
- Product titles, product URLs, JOD prices and category destination URLs compared against the original rendered page. No changes to their underlying data.
- Reduced-motion styles verified. Full-page and section screenshots reviewed; screenshots retained under `/tmp/abdeen-final-{width}.png` and `/tmp/abdeen-{section}-{width}.png`.
- `npm run build:css`: passed.
- `node --check static/abdeen/js/homepage.js`: passed.
- `python manage.py test config --noinput`: all 11 existing homepage/Oscar integration tests passed using the isolated test database.
- `python manage.py check`: no issues.
- `git diff --check`: passed.
- Preview database opened using SQLite `mode=ro`. Before/after database SHA-256 remained `3c519e71314e865b1e0d8fcdb648b74dc4d200aec0d24f6d4a71b9787a696c47`.
- `config/homepage.py` hash remained `877a12088d5af756fd1d0fc1696e625df16aecc19c4569b8fe0eb199a7739b6e`.

**Every modified or added file in this task**

| File | Change |
| --- | --- |
| `assets/styles/homepage.css` | Homepage typography, header/footer, hero, section/card layouts and responsive styles |
| `static/abdeen/css/tailwind.css` | Rebuilt stylesheet (existing generated, Git-ignored output) |
| `static/abdeen/js/homepage.js` | Header panels, Escape/outside-click handling and focus management; existing filters retained |
| `templates/oscar/layout.html` | Two overridable header/footer blocks; default Oscar presentation preserved on other pages |
| `templates/oscar/home.html` | Homepage-only header/footer overrides and local hero preload |
| `templates/oscar/partials/home/header.html` | New real-logo desktop/mobile header with native search/menu panels |
| `templates/oscar/partials/home/footer.html` | New real-logo footer using existing destinations |
| `templates/oscar/partials/home/hero.html` | Local photograph, separate media layer and refreshed headline |
| `templates/oscar/partials/home/categories.html` | Responsive cards; existing category images/URLs preserved; static fallback art |
| `templates/oscar/partials/home/brands.html` | Avoid empty description spacing; retain real brands |
| `templates/oscar/partials/home/best_sellers.html` | Responsive real-data product grid and styled empty state |
| `templates/oscar/partials/home/new_arrivals.html` | Responsive real-data product grid and styled empty state |
| `templates/oscar/partials/home/product_card.html` | Removed nonfunctional decorative heart; all pricing/availability logic unchanged |
| `templates/oscar/partials/home/promo_banner.html` | Distinct local editorial photo and refreshed copy |
| `templates/oscar/partials/home/why_choose.html` | Consumer-facing copy without unverified delivery/payment/warranty claims |
| `templates/oscar/partials/home/newsletter.html` | Replaced disabled signup with a working catalogue invitation |
| `templates/oscar/partials/home/icon.html` | Search, menu and close icons |
| `static/abdeen/images/home/hero-watch.jpg` | Local hero photograph |
| `static/abdeen/images/home/category-classic.jpg` | Local category fallback photograph |
| `static/abdeen/images/home/editorial-watch.jpg` | Local editorial photograph |
| `static/abdeen/images/home/SOURCES.md` | Image sources and replacement guidance |
| `static/abdeen/fonts/plus-jakarta-sans-latin.woff2` | Local variable sans-serif font |
| `static/abdeen/fonts/playfair-display-latin.woff2` | Local variable editorial font |
| `static/abdeen/fonts/plus-jakarta-sans-OFL.txt` | Font redistribution license |
| `static/abdeen/fonts/playfair-display-OFL.txt` | Font redistribution license |
| `docs/homepage-polish.md` | Audit, validation, scope and complete file inventory |

The previously supplied `static/abdeen/images/black.png` and `white.png` are used unchanged. Pre-existing backend/import changes in the workspace were not touched.

**Remaining assets/content**

- No Abdeen campaign video was supplied; the image hero is complete and its media layer is ready for a future video.
- Abdeen-owned campaign and showroom photography has not been supplied. Locally hosted reference/editorial watch photography is used; none is labeled as an Abdeen store or specific in-stock product.
- Official individual brand logo assets are absent. The brand section uses the real brand names in typography, consistent with the reference's approach.
- Verified contact information, store locations and commercial policy copy have not been supplied. The footer uses only functioning shop/account links; no demo phone numbers, delivery promises or payment badges were added.
