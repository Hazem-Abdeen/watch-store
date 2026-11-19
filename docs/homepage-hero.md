# Homepage hero slides

Manage campaigns in **Oscar Dashboard → Homepage → Hero Slides**, at
`/dashboard/homepage/hero-slides/`. Active staff accounts can manage slides;
customers and partner-only dashboard users cannot.

- **Add hero slide** uploads desktop artwork and an optional mobile version.
- Use **Edit** to replace artwork, change optional copy, or configure a button.
- Set order numbers and active checkboxes in the list, then select **Save order
  and active status**. Lower numbers come first; ties use creation order.
- **Delete** opens a confirmation page. Deletion removes the slide record; like
  Django's default file handling, old/replaced files remain in storage for
  separate media retention/cleanup. It does not delete shared files.

Campaign images use Django's default MEDIA storage (`MEDIA_ROOT` / `MEDIA_URL`
locally), never static assets. No sample campaign is installed or hard-coded.
The new `homepage` app owns the model and migration; `config.dashboard` extends
Oscar's dashboard routes without replacing its other applications.

## Artwork and copy

Desktop artwork fills the section width using `width: 100%; height: auto`.
Images keep their original proportions with no width or viewport-height cap,
so no side margins or cropping are introduced. Tall artwork may extend below
the first screen; a wider source image is needed for a shorter full-width hero.
Below **768px**, the mobile image is used when present, falling back to the
desktop version. Mobile artwork displays at its natural aspect ratio. Only the
visible slide determines the carousel height, so hidden taller images cannot
create blank space above or below it. Different image proportions change the
section height on navigation; use matching proportions across desktop campaigns
and matching proportions across mobile campaigns for consistent heights. Responsive images
are decoded before navigation is enabled; failed images do not block initialization.

To configure separate mobile artwork, open **Dashboard → Homepage → Hero Slides**,
edit the existing slide, choose the portrait file in **Mobile image**, and select
**Save slide**. Keep the wide image in **Desktop image**. The browser selects the
mobile file at widths up to 767px and the desktop file at 768px and above. This
is one slide with one destination URL; do not create a second slide for mobile.

Leave title, subtitle, button label and URL empty for artwork with embedded
text. No overlay or gradient is rendered for image-only campaigns. Use the
image description to communicate the artwork's content to screen readers.
Optional copy overlays the desktop stage and follows the image on mobile.
Buttons require both label and URL. Local absolute paths (`/catalogue/`) and
HTTP(S) links are supported; executable and protocol-relative URLs are rejected.

## Carousel behavior

Multiple slides provide translucent circular previous/next arrows centered at the
edges of the image and tight pagination dots directly below it. The play/pause
button has been removed. All remaining controls have accessible names and visible
keyboard focus states. There are no visible slide numbers or pause text labels.
Automatic rotation runs every six seconds. Hover pauses
rotation temporarily; keyboard focus, manual navigation, and touch interaction
stop it for the remainder of the visit. Background tabs suspend the timer.
Reduced-motion preferences disable automatic rotation.

Controls work with Tab and Enter/Space; Left/Right and Home/End navigate from
within the carousel. Horizontal mobile swipes change slides while vertical
scrolling and pinch zoom remain available. Hidden slides and their links leave
the focus order. Automatic changes are not announced; manual changes announce
the slide position. Without JavaScript the first campaign remains visible.
A single slide has no carousel controls; zero active slides produce no hero
markup or empty reserved space.

The homepage header has a compact 72px desktop / 64px mobile white navigation
row, with 44px action targets. Other storefront pages retain their header sizing.
Slide changes use a subtle 180ms reveal, disabled under reduced motion.

## Historical build and verification

For another environment, run `manage.py migrate` using that environment's Python
interpreter, then `npm run build:css`. Production must serve MEDIA uploads and
collect/serve static assets as usual. The migration is already applied locally.

Django coverage: `manage.py test homepage config` tests ordering/ties,
active/inactive and missing images, empty/single/multiple slides, actual desktop
and mobile uploads into temporary storage, image-only rendering, safe/unsafe
links, paired CTA fields, invalid uploads, dashboard CRUD, bulk ordering and
activation, permission boundaries, and CSRF protection alongside existing
storefront regressions.

Browser verification used an isolated database copy and temporary campaign
artwork (2400 × 1000 desktop and 750 × 1000 mobile). At **1440, 768, 390 and
320px**, the document/body/hero widths equaled the viewport, with no horizontal
overflow, for both image-only campaigns and optional copy/buttons. Desktop vs
mobile source selection, six-second rotation, hover/focus pause, pause/resume,
keyboard navigation, reduced motion and Chromium touch swipe were checked.
Actual campaign artwork should also be previewed after upload to assess its
composition and embedded-text legibility.

The full local regression suite passed: **161 tests**. Browser checks also passed
for dot selection, the no-JavaScript fallback, and the Oscar list/upload forms,
with no JavaScript errors.

## Header and controls refinement verification

The refinement changes only templates, CSS, carousel JavaScript, tests and docs.
No data model, dashboard, upload handling, ordering or catalogue logic changed.

Repeat the browser checks by starting `tests/browser/hero_preview.py` with the
project interpreter in one terminal. It uses a temporary database and MEDIA
directory, including mobile/desktop artwork with deliberately different aspect
ratios and a slide with optional copy. In another terminal, run
`node tests/browser/hero-controls.cjs` with Playwright available. If installed
elsewhere, set `PLAYWRIGHT_MODULE` to its module path; optionally set `CHROME_PATH`.
Stop the fixture server with Ctrl-C to clean up the temporary data.

The checks passed at 1440/768/390/320px: header heights, zero horizontal overflow,
stable hero height across slides, arrow positioning, dots immediately below the
image, previous/next, direct dot navigation, six-second autoplay, hover/focus and
touch pause, explicit resume, keyboard controls, focus indicators, actual Chromium
touch swipe, reduced motion, no-JavaScript fallback and header search/menu controls.
The browser reported no JavaScript errors.

Screenshots of the existing uploaded campaigns:

- [1440px desktop](screenshots/header-hero-1440.png)
- [768px tablet](screenshots/header-hero-768.png)
- [390px mobile](screenshots/header-hero-390.png)
- [320px mobile](screenshots/header-hero-320.png)

## Banner destinations

Edit a slide under Dashboard → Homepage → Hero Slides. Destination URL (optional)
reuses the existing button_url column. Paste the Jaguar product page's path
(from its storefront URL), save, and click the banner to verify it.
Leave the button label empty for artwork with an embedded Shop Now button.
A blank destination disables navigation; HTTP(S) and store-relative absolute
paths are accepted. A label still requires a destination.
Existing configured button URLs now also link the whole banner.
No database migration is required. Build CSS with npm run build:css, run
manage.py collectstatic --noinput using the production environment, then restart
the application using the deployment's existing service procedure.

## Historical clickable-banner restoration verification (2026-11-19)

Restored the committed full-width design, desktop image height
`clamp(420px, 46vw, 780px)`, mobile natural aspect ratio, and pause/resume control.
Banner links sit beneath independent controls and do not wrap optional CTA links.
Dragging more than 10px suppresses pointer clicks until the next pointer gesture;
keyboard activation remains available. This also protects single-slide banners.

`manage.py test homepage.tests --noinput`: 22 tests passed, including URL safety,
independent destinations, blank destinations, accessible names, sibling links,
dashboard editing/clearing, CRUD, ordering, permissions, and CSRF.
`manage.py makemigrations --check --dry-run`: no changes detected.
`npm run build:css`: passed.
`tests/browser/hero-controls.cjs`: passed at 1440/768/390/320px, including original
dimensions, stable layout, controls, pause/resume, keyboard links, real mouse
clicks, touch swipes, vertical scrolling, touch taps, reduced motion, and the
no-JavaScript fallback. No JavaScript errors occurred. Existing Jaguar artwork
was also checked in desktop and mobile screenshots using a temporary database.

The broader `manage.py test homepage config --noinput` run is not clean:
47 failures and 8 errors. A separate temporary source copy with the committed
hero implementation reproduced the identical 55 failing test identifiers.
These existing catalogue/search/brand issues were left outside this hero fix.

IDE analysis: working analysis of the eight source files listed below. No new
diagnostics were introduced or fixed. Seven existing warnings remain: four SVG
self-closing-path warnings and three Python type warnings in existing upload,
logo-storage, and order-form code. The IDE build completed with limited build
diagnostic support.

Changed source files: `assets/styles/hero.css`, `homepage/forms.py`,
`homepage/models.py`, `homepage/tests.py`, `static/abdeen/js/hero.js`,
`templates/oscar/partials/home/hero.html`, `tests/browser/hero-controls.cjs`,
and `tests/browser/hero_preview.py`. Documentation: `docs/homepage-hero.md`.

## Historical complete artwork and removal of play/pause button

That update removed the play/pause control and its JavaScript/CSS, centers
the hero within 1280px, and replaces cropped desktop images with proportional
artwork capped by the viewport height. Existing banner images need no editing.
Arrows, dots, autoplay, hover/focus pause, links and swipe protection remain.

Validation: 22 hero/dashboard tests passed; browser checks passed at
1440/768/390/320px with no JavaScript errors; CSS build and JavaScript syntax
checks passed. Desktop and mobile Jaguar artwork were visually inspected.
IDE working analysis covered hero CSS, JavaScript, template, Django tests and
browser checks. Three existing warnings remain (two SVG-path warnings and an
upload-test type warning); no new diagnostics were introduced. No migration.

## Full-width artwork correction

Removed the 1280px width cap and viewport-height caps. Images now fill the
section width at their natural aspect ratio on desktop and mobile. This keeps
the full image without side gaps; artwork may be taller than the viewport.
The play/pause control remains removed. No Python, model, or migration changes.

CSS build and JavaScript syntax checks passed. IDE working analysis covered
`assets/styles/hero.css` and `tests/browser/hero-controls.cjs`; no diagnostics
were reported or required fixing. IDE build succeeded with limited diagnostics.
Browser checks passed at 1920/1440/768/390/320px, including full-width natural
image proportions, controls, links, swipe protection, and no JavaScript errors.
The actual Jaguar artwork was visually checked at 1840px: its image spans the
full 1840px width with a proportional height of 1036px and no horizontal inset.

## Gap above mixed-aspect banners

Removed the rule that kept hidden slides in the grid layout. Previously, a
hidden taller campaign reserved a 920px image row and centered the visible
766.5px Jaguar artwork within it, leaving 76.75px above the image. The visible
image now starts directly at the header bottom and defines its own row height.

Validation: browser checks passed at 1920/1440/768/390/320px with deliberately
different slide proportions, verifying zero space above the artwork or before
the dots, mobile image selection, desktop fallback, links and carousel input.
Actual uploaded artwork was also measured and visually checked. CSS build and
JavaScript syntax checks passed. IDE working analysis of `assets/styles/hero.css`,
`static/abdeen/js/hero.js`, `tests/browser/hero-controls.cjs` and
`tests/browser/hero_preview.py` reported no diagnostics; none required fixing.
The IDE build succeeded with limited build diagnostic support. No migration.
