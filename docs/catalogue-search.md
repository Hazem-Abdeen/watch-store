# Local catalogue search — 2026-09-22

The development catalogue now uses a local Whoosh index and Oscar 4.2's existing
catalogue/search views, forms and product index. The imported database and the
catalogue UI are unchanged. No Oscar or Haystack package files were edited.

## Root cause and investigation

Versions inspected: django-oscar 4.2, django-haystack 3.4.0, Django 5.2.16,
Python 3.12.3. Previously, `HAYSTACK_CONNECTIONS['default']['ENGINE']` was
`haystack.backends.simple_backend.SimpleEngine`.

Oscar's `catalogue.views` loads the catalogue/category views from `search.views`.
Their `BaseSearchView.get_queryset()` uses `search.facets.base_sqs()`, which adds
facets and the essential `is_public="true"` and
`structure__in=["standalone", "parent"]` filters. `CategoryForm` adds the selected
category and its descendants for category browsing; `SearchForm` handles text,
selected facets and sorting. The view uses Django's paginator, with 20 products
per page. Templates resolve each search result to its real Product object and
continue to obtain prices and availability from Oscar's request strategy.

SimpleEngine is not an index-backed search engine. Its unrestricted `*` query
reads all model rows. Its query builder discards field names/operators and turns
Oscar's required filters into `true ['standalone', 'parent']`, which its backend
treats as text to find in database string fields. It consequently returns zero
products rather than applying those filters.

| Check | Before: SimpleEngine | After: local Whoosh |
| --- | ---: | ---: |
| Database Product count | 731 | 731 |
| Database browsable count | 731 | 731 |
| `SearchQuerySet().all().count()` | 731 | 731 |
| Oscar `base_sqs().count()` | 0 | 731 |

`rebuild_index --noinput` was also tested before switching: despite printing
“Indexing 731 Products”, it warned that `clear` and `update` were unimplemented,
and Oscar still returned zero. Rebuilding cannot fix SimpleEngine. The same
command now creates a real index from Oscar's existing `ProductIndex`.

This agrees with [Haystack's Simple backend documentation](https://django-haystack.readthedocs.io/en/stable/tutorial.html#simple),
which says data preparation and advanced filtering do not work with it.

## Development solution

- `Whoosh-Reloaded==2.7.5` supplies the Python `whoosh` package; its
  [package metadata](https://pypi.org/project/Whoosh-Reloaded/2.7.5/) includes
  Python 3.12 support. `cached-property==2.0.1` pins its dependency.
- The index lives at `var/whoosh_index/`, excluded from Git. No service,
  container, Solr or Elasticsearch installation is needed.
- `config.search_backend.LocalWhooshEngine` inherits Haystack's standard engine
  and query class, with one offset correction in its backend.
- The product index, filters, URLs, database products, template presentation,
  pricing and availability implementations remain Oscar's own.

### Final-page correction

Real-data pagination testing exposed a separate Haystack 3.4 Whoosh adapter bug.
For the final page's requested slice `[720:731]`, the adapter calculated page 66
with length 11, beginning at offset 715. It repeated five products and omitted
the final five. A small local subclass detects unaligned slices, fetches a prefix
through the requested end offset and slices that result precisely. Aligned pages
keep Haystack's normal implementation, and hit counts, facets and sorting remain
intact. This modest prefix fetch is suitable for this development catalogue.

### Index refresh workflow

Install dependencies and build the index on a new checkout:

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py rebuild_index --noinput
.venv/bin/python manage.py runserver
```

Run `rebuild_index --noinput` again after imports or catalogue edits, including
stock, price, category assignment, publication, variant, or product deletion
changes. It rebuilds derived search data; it does not delete database products.
An already-running development server must reload the changed settings.

Indexing is explicitly manual via `BaseSignalProcessor`. Oscar's inherited
`RealtimeSignalProcessor` only updates a product on its save/delete signals;
related stock/category writes and bulk updates can otherwise leave a partially
updated index. A full rebuild captures the completed dataset consistently.
Displayed prices and availability always come from the current request strategy;
search matching, ordering and facets reflect the most recent index rebuild.

Whoosh supports the field facets used here but not query-facet counts. Oscar
already omits its price-range buckets for Whoosh. Haystack emits the corresponding
query-faceting warning; no fake range controls or replacement query behavior were
added.

## Validation

- `manage.py check`: no issues.
- `manage.py test --noinput`: **107 tests passed**, including seven new real-index
  integration tests and the existing catalogue presentation tests.
- `pip check`: no broken requirements. `git diff --check`: passed.
- All **731 distinct products** traversed across **37 catalogue pages**, with
  **20 products on page 1** and **11 on page 37**. No duplicates or omissions.
- All **24 menu-visible categories** traversed and compared against actual
  database assignments plus descendants. Examples: Men 456, Women 315, Brands
  731, Casio 118, G-SHOCK 31. Products can belong to multiple categories.
- `/search/?q=CASIO` returned **118** products. All offered sort options returned
  valid responses; regression tests verify actual price/title ordering and
  multiple selected field facets.
- Real product links, titles, image URLs, strategy JOD prices, stock state,
  product detail responses, unavailable stock and parent options verified.
- Live browser checks of the catalogue, Casio category and final catalogue page
  passed at 1440, 768, 390 and 320px, with no horizontal overflow. The real sort
  control submitted `sort_by=price-desc` and returned populated results. No
  document interception or substituted products were used for these checks.
- The configured test runner uses a temporary Whoosh directory. Development
  index files had identical checksums before and after the full test suite.

## Changed files

- `.gitignore`: excludes the generated local index.
- `requirements.txt`: pins Whoosh-Reloaded and its dependency.
- `config/settings.py`: selects the local engine, index directory, explicit
  rebuild policy and isolated test runner.
- `config/search_backend.py`: corrects Haystack's unaligned result slices.
- `config/test_runner.py`: keeps tests and their rebuilds off the development index.
- `config/test_search.py`: tests real indexing, visibility, categories, search,
  sorting, facets, pagination, card data and rebuilds after related data changes.
- `config/test_catalogue.py`: expects working sorting under Whoosh and still
  verifies the presentation guard for unsupported SimpleEngine sorting.
- `docs/catalogue-redesign.md`: marks the earlier backend limitation resolved.
- `docs/catalogue-search.md`: records this investigation, setup and validation.

The generated `var/whoosh_index/` is also present locally; it is rebuildable and
intentionally untracked. Other pre-existing working-tree changes are unrelated.
