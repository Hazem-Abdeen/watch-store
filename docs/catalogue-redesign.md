# Catalogue presentation

The catalogue and category pages reuse the homepage header/footer, local fonts,
white/charcoal/red palette, shell width and card treatment. Catalogue CSS is
loaded only by browse templates. Shared navigation uses homepage section URLs
when rendered on catalogue pages. The mobile category tree uses native details.

Oscar still owns category/facet links, search forms, queries, product selection,
URLs, strategy pricing, availability and add-to-basket forms. Pagination uses
Oscar's `get_parameters` tag, retaining repeated facets and the other query
parameters. The product-card override falls back to the installed Oscar template
outside browse pages. Product detail, basket, checkout and package files were
not redesigned or modified by the UI task. The subsequent backend fix is
documented in [catalogue-search.md](catalogue-search.md).

## Original backend limitation — resolved 2026-09-22

**Resolved:** local Whoosh indexing now returns all 731 products, with real
category membership and complete pagination. See [catalogue-search.md](catalogue-search.md)
for the root cause, setup, index refresh workflow and 107-test validation.
The following describes the original state during the UI-only task.

The then-configured Haystack `SimpleEngine` returned **zero** results for Oscar's
`base_sqs()` although the database contains **731 browsable products**. The
backend does not interpret Oscar's indexed field filters or implement ordering.
This was confirmed independently of template rendering. Backend configuration
and catalogue query logic have been preserved within the requested scope.

The UI therefore showed its empty state on the live catalogue. An explicit
presentation capability check suppresses sorting controls for SimpleEngine;
other backends retain Oscar's existing sort form and event handler. Facets are
shown only when Oscar supplies them. There is no replacement filtering or
sorting implementation.

## Verification — 2026-09-21

- `manage.py check`: no issues.
- `manage.py test --noinput`: **100 tests passed**, including 8 new catalogue
  presentation tests. Haystack emits its existing SimpleEngine update warning.
- Django checks and the full 100-test suite were rerun successfully on
  2026-09-22 against the same implementation.
- `node --check static/abdeen/js/catalogue.js`: passed.
- `git diff --check`: passed.
- Headless Chrome at **1440, 768, 390 and 320px**: no horizontal overflow for
  the live empty state, a populated catalogue, and a populated Casio category.
  Populated layouts have **4, 2, 2 and 1 columns**, respectively. Image containers
  remain square. Category panels, mobile menus and search panels do not overflow;
  search focus and Escape dismissal were exercised. No JavaScript exceptions.

Because the live search backend returns no products, populated browser checks
used temporary HTML rendered by the actual Django templates with real database
products, images, strategy prices and availability. Chrome's document-response
interception supplied that HTML only to the isolated verification browser; no
preview routes, products, or backend overrides were added to the application.
These checks validate presentation, not a working search backend.

The new tests cover original basket form fields, parent-product options,
unavailable stock, image fallback, full titles and JOD prices, category metadata,
query/sort/multiple-facet pagination parameters, shared navigation, empty states,
and retained Oscar markup outside the catalogue.

Browser screenshots and measurements were inspected in the temporary verification
session. Its `/tmp` artifacts were cleared between sessions and are not retained
in the repository.

## Files changed in this task

- `templates/oscar/catalogue/browse.html`
- `templates/oscar/catalogue/category.html`
- `templates/oscar/catalogue/partials/product.html`
- `templates/oscar/catalogue/partials/browse_pagination.html`
- `templates/oscar/partials/home/header.html`
- `templates/oscar/partials/home/footer.html`
- `static/abdeen/css/catalogue.css`
- `static/abdeen/js/catalogue.js`
- `catalogue_import/templatetags/__init__.py`
- `catalogue_import/templatetags/storefront_tags.py`
- `config/test_catalogue.py`
- `docs/catalogue-redesign.md`

Other pre-existing working-tree changes are outside this task.
