# Homepage brand logos

Manage logos at **Oscar Dashboard → Homepage → Brand Logos**
(`/dashboard/homepage/brand-logos/`). Each direct child of the top-level category
whose slug is `brands` has an **Edit logo** action. Upload/replace its logo,
clear the file, or turn off **Use logo** to return to the text treatment.
Only active staff accounts can manage logos.

The `homepage.BrandPresentation` model is a one-to-one presentation record
attached to the existing Oscar category. It owns `logo` and `is_active`; it does
not replace or change Oscar's category image, name, slug, tree, visibility,
product assignments, search indexing, or URLs. The homepage retains its existing
public/menu-visible direct-child selection, path ordering and eight-brand limit.
The dashboard also lists unpublished brands so their logos can be prepared.

Uploads use Django's default MEDIA storage under `homepage/brands/`. Supported
formats are PNG, WebP and static self-contained SVG, up to 2 MB. Raster contents
are verified, and SVG validation excludes scripts, external resources, embedded
images and animation. Common vector paths, shapes, text, styles, gradients, masks,
clipping and local references are accepted; export unsupported SVGs as plain SVG
or transparent PNG/WebP. SVG is rendered through an image element, never inlined.
No official logos, template paths, or brand-specific styling are hard-coded.

Each logo area is a single keyboard-focusable catalogue link in an open grid,
with no borders, card backgrounds, descriptions or secondary labels. Four columns
on desktop and two on mobile keep consistent spacing between centered logos.
Artwork uses a common height (86px desktop / 64px mobile), constrained to available
width with `object-fit: contain` to retain its original proportions. Only opacity
changes subtly on hover; a short underline marks keyboard focus without a box.
The brand name appears when metadata or artwork is absent, the logo is inactive,
the storage file is missing, or an image request fails in the browser. Turning off
a logo does not hide its category. With JavaScript disabled, existing logo files
and server-side fallbacks still render; late network errors need JavaScript for
the visual text replacement.

The migration has been applied locally and CSS rebuilt. On another environment,
run `manage.py migrate` with that environment's interpreter and `npm run build:css`,
and serve MEDIA/static files through the normal deployment configuration.
Replacing/clearing files follows Django's default retention behavior: old files
are not automatically deleted from storage.

## Verification

- Django checks pass, with no pending model changes.
- Tests cover uploaded PNG/WebP/SVG, no logo, inactive/missing/unavailable images,
  preserved links/category images/tree selection/order/limits, dashboard upload,
  replacement/clearing/deactivation, permissions, CSRF, and invalid/unsafe files.
- Chromium tested wide PNG, tall WebP, SVG, text fallback, long brand names,
  inactive/missing/broken images and aborted image requests. Keyboard card links
  and an SVG upload through Oscar's dashboard were also exercised.
- At 1440, 768, 390 and 320px, both document and body width exactly matched the
  viewport, with no horizontal overflow. No JavaScript errors occurred. Testing used temporary artwork and
  a temporary database; official logos remain to be uploaded.

## Files changed for this update

- `homepage/models.py`
- `homepage/validators.py`
- `homepage/brands.py`
- `homepage/forms.py`
- `homepage/views.py`
- `homepage/test_brands.py`
- `homepage/migrations/0002_brandpresentation.py`
- `config/homepage.py`
- `config/dashboard.py`
- `config/settings.py`
- `templates/oscar/partials/home/brands.html`
- `templates/oscar/dashboard/homepage/brand_list.html`
- `templates/oscar/dashboard/homepage/brand_form.html`
- `assets/styles/homepage.css`
- `static/abdeen/js/homepage.js`
- `static/abdeen/css/tailwind.css` (generated, ignored by Git)
- `docs/homepage-brand-logos.md`
- `db.sqlite3` (local schema migration, ignored by Git)

Backend update regression result: **176 tests passed**. The subsequent borderless
showcase redesign passed **42 homepage tests** and browser checks at all four widths.
