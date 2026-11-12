# Flat delivery fee

Oscar previously loaded `oscar.apps.shipping.repository.Repository`, whose
`methods = (Free(),)` returned `free-shipping`, **Free shipping / 0 JOD**.
`homepage/views.py` did not implement shipping.

The project now registers `config.shipping.apps.ShippingConfig`. Its repository
returns `Delivery(FixedPrice)` with tax-inclusive and tax-exclusive charges of
`Decimal('2.00')`, code `jordan-delivery`, name **Delivery**, and description
**1–2 business days**. Oscar computes basket estimates, checkout totals, stored
order shipping and COD allocation from this method. Templates only format the
calculated values. No JavaScript price calculation was added.

Jordan is the only checkout destination, including saved-address selection.
There is one auto-selected method with no radio buttons. Every order has the
same delivery fee, without a threshold or city/weight calculation. Shipping
offers cannot reduce this fixed charge; merchandise vouchers/discounts remain
active. Cash on Delivery is still the only payment method.

## Verified amounts

| Scenario | Merchandise before discounts | Discount | Shipping | Order / COD due |
| --- | ---: | ---: | ---: | ---: |
| Requested single-product example | 189.00 | 0.00 | 2.00 | 191.00 |
| Three units at 125.50 | 376.50 | 0.00 | 2.00 | 378.50 |
| 125.50 item plus two 189.00 items | 503.50 | 0.00 | 2.00 | 505.50 |
| 10% voucher on 125.50 | 125.50 | 12.55 | 2.00 | 114.95 |

All amounts are JOD. COD allocation/balance includes delivery; amount debited
remains zero. Order history shows the shipping-inclusive total and order detail
shows the stored shipping separately. Thank-you pages read the persisted order.
Historical orders keep their original amounts.

## Files changed for this task

- Added `config/shipping/__init__.py`, `apps.py`, `methods.py`, `models.py`, and
  `repository.py`. Oscar's models/migration history are reused without package
  modifications or schema changes.
- `config/settings.py`: shipping app registration and migration-module mapping.
- `config/checkout/forms.py`, `config/checkout/views.py`: Jordan-only country and
  saved-address choices. Payment, order submission and notification hooks remain
  unchanged.
- `templates/oscar/checkout/cod.html`,
  `templates/oscar/checkout/partials/summary_totals.html`, and
  `templates/oscar/checkout/thank_you.html`: delivery description and two-decimal
  shipping presentation using actual calculated/stored amounts.
- Added `config/test_shipping.py`; updated `config/test_checkout.py`,
  `config/test_basket.py`, `config/test_accounts.py`,
  `config/test_sale_pricing.py`, and `config/test_order_notifications.py`.
  Notification changes are test expectations/fixtures only, including retained
  coverage for historical shipping-discount emails.
- `tests/browser/checkout_preview.py`, `tests/browser/checkout.cjs`, and
  `tests/browser/checkout-concurrency.cjs`: 189 JOD fixture and shipping/order/COD,
  confirmation, order history/detail and concurrency assertions.
- `docs/cod-checkout.md`, `docs/checkout-redesign.md`, and this report.

Existing uncommitted work was preserved. Email notification code and templates,
SMTP configuration, product imports, Oscar package files and production order
data were not changed by this task.

## Validation

- `manage.py check`: passed, no issues.
- `manage.py makemigrations --check --dry-run`: no changes detected.
- 104 tests passed across shipping, checkout, basket, cart drawer, account,
  sale-pricing and notification suites. Includes guest/account checkout,
  single/multiple products, quantities, voucher totals, stock allocation,
  country validation, stale/forged shipping selections, thank-you refresh,
  repeated submission and failed-order recovery.
- Browser checkout passed for both guests and accounts at 1440, 1024, 768, 390
  and 320px, including summary, confirmation, history/detail, refresh and replay.
  No horizontal overflow, duplicate element IDs or JavaScript errors. Screenshots
  were reviewed at all four requested widths. Checkout also passed with JavaScript
  disabled at 320px.
- Two simultaneous browser POSTs returned redirects and created one order with
  2.00 JOD shipping and 191.00 JOD COD due.
- Browser orders used the existing disposable database-copy fixture and in-memory
  email backend.
- The final broader regression run passed 296 of 300 tests, with four unrelated
  stock-label failures.
  All four also failed when run with Oscar's original free-shipping repository:
  `config.test_catalogue.CataloguePresentationTests.test_missing_image_and_unavailable_stock`,
  `config.test_catalogue.CataloguePresentationTests.test_real_card_links_to_product_with_compact_details`,
  `config.test_search.IndexedCatalogueTests.test_result_cards_keep_oscar_prices_availability_images_and_links`,
  `config.tests.HomepageTests.test_real_product_links_images_stock_and_jod`.
  They expect `In stock`/`Out of stock` text absent from current product cards.
