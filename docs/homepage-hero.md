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

Wide desktop artwork around **2400 × 1000** works well. The desktop stage is
large and uses `object-fit: cover`, so artwork fills the stage without dark side
gaps; different aspect ratios crop the image around its center to fit.
Below **768px**, the mobile image is used when present, falling back to the
desktop version. Mobile artwork displays at its natural aspect ratio. The carousel
reserves the tallest artwork and optional-copy tracks across slides, so navigation
does not move the dots or the following homepage sections. Shorter images are
centered in the reserved space without stretching or cropping. Responsive images
are decoded before navigation is enabled; failed images do not block initialization.

Leave title, subtitle, button label and URL empty for artwork with embedded
text. No overlay or gradient is rendered for image-only campaigns. Use the
image description to communicate the artwork's content to screen readers.
Optional copy overlays the desktop stage and follows the image on mobile.
Buttons require both label and URL. Local absolute paths (`/catalogue/`) and
HTTP(S) links are supported; executable and protocol-relative URLs are rejected.

## Carousel behavior

Multiple slides provide translucent circular previous/next arrows centered at the
edges of the image, tight pagination dots directly below it, and a small pause/play
icon at the lower-right corner. All controls have accessible names and visible
keyboard focus states. There are no visible slide numbers or pause text labels.
Automatic rotation runs every six seconds. Hover pauses
rotation temporarily; keyboard focus, manual navigation, and touch interaction
stop it until explicitly restarted. Background tabs suspend the timer.
Reduced-motion preferences disable automatic rotation and hide its control.

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

## Build and verification

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
