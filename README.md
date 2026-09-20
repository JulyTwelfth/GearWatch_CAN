# GearWatch Canada

GearWatch Canada is an MVP price and inventory tracker for Arc'teryx products sold by
Canadian retailers. It presents periodically checked data, preserves price and inventory
history, and directs shoppers to each retailer for final confirmation.

> Status: Stage 7C scheduled, containerized MVP. The project has a live-capable Arc'teryx Outlet Canada
> adapter for explicitly configured product pages, a network-disabled Sporting Life fixture
> adapter, a transactional collection command, PostgreSQL-backed APIs, and accessible search and
> product-detail pages covered by deterministic Playwright journeys. The FastAPI application and
> PostgreSQL run together in Docker Compose, with deterministic scheduled collection and complete
> quality/container checks defined in GitHub Actions.

## Screenshots

These screenshots show locally collected data from a dated check, not guaranteed current retailer
offers. Price and availability must always be confirmed on the retailer website.

### Filtered search and offer comparison

![Filtered GearWatch search results](docs/screenshots/search-results.png)

### Product detail

![GearWatch product detail and current offers](docs/screenshots/product-detail.png)

### Change-only price and inventory history

![GearWatch price and inventory history](docs/screenshots/price-history.png)

## MVP roadmap

1. Foundation (complete): FastAPI skeleton, configuration, health check, and test layout.
2. Data contract (complete): normalization utilities and a retailer adapter interface.
3. Persistence (complete): PostgreSQL models, Alembic migration, snapshot and deduplication rules.
4. Collection (complete): Arc'teryx Outlet and Sporting Life parsers, HTTP
   timeout/retry/rate limiting, adapter failure isolation, and the transactional one-shot command
   plus an explicitly enabled periodic scheduler.
5. Search API and server-rendered pages (complete): filtered offer-list, product detail, and
   change-history APIs plus search/detail HTML pages, freshness notices, and price charts.
6. Quality (complete for current features): unit, PostgreSQL integration, API, parser regression,
   and Playwright E2E coverage.
7. Delivery (complete locally): application/PostgreSQL/scheduler Compose services and GitHub
   Actions CI. The first hosted CI run requires pushing the repository to GitHub.

## Architecture boundaries

```text
app/
  adapters/       # One adapter per retailer; all return the same schema
  api/routes/      # FastAPI HTTP endpoints
  commands/        # One-shot and scheduled collection entry points
  core/            # Settings, logging, HTTP policy
  db/              # Engine and session lifecycle
  models/          # SQLAlchemy database models
  repositories/    # Persistence and deduplication operations
  schemas/         # Pydantic data contracts
  services/        # Search, collection, history, and scheduling workflows
  static/          # CSS and small JavaScript files
  templates/       # Jinja HTML templates
  web/             # Server-rendered page routes
docker/            # Container entrypoint and PostgreSQL initialization
docs/screenshots/  # Portfolio screenshots from locally collected data
tests/
  api/             # HTTP contract and error handling
  e2e/             # Playwright browser scenarios
  fixtures/        # Saved, non-sensitive retailer HTML
  integration/     # PostgreSQL and multi-layer tests
  unit/            # Parsers, normalization, calculations
```

Adapters will not write to the database. They will return a shared validated schema; services will
coordinate adapters, and repositories will own database writes. This keeps a third retailer from
requiring changes to search or persistence logic.

## Run with Docker Compose

Docker Desktop is the only runtime prerequisite for this path. The application container waits for
PostgreSQL, applies Alembic migrations, starts as a non-root user, and exposes a health check.

```powershell
Set-Location F:\GearWatch_CAN
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
```

Open `http://127.0.0.1:8000/` for the UI or `http://127.0.0.1:8000/docs` for the API docs. View
application startup and migration logs with:

```powershell
docker compose logs --tail 50 app
```

Stop the application and PostgreSQL without deleting the database volume:

```powershell
docker compose down
```

## Run directly on Windows PowerShell

```powershell
Set-Location F:\GearWatch_CAN
py -3.13 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/health` or `http://127.0.0.1:8000/docs`.
The user interface is available at `http://127.0.0.1:8000/`.

The execution-policy change above applies only to the current PowerShell window. If activation is
not desired, every command can instead use the virtual-environment interpreter directly, for
example `.\.venv\Scripts\python.exe -m pytest`.

Start PostgreSQL and apply migrations:

```powershell
Set-Location F:\GearWatch_CAN
docker compose up -d db
.\.venv\Scripts\Activate.ps1
alembic upgrade head
alembic current
```

Run the current tests:

```powershell
Set-Location F:\GearWatch_CAN
.\.venv\Scripts\Activate.ps1
$env:GEARWATCH_TEST_DATABASE_URL = "postgresql+psycopg://gearwatch:gearwatch@localhost:5432/gearwatch_test"
python -m playwright install chromium
pytest
alembic check
ruff check .
```

The Chromium installation is a one-time download for each Playwright version. To run only the
browser journeys:

```powershell
Set-Location F:\GearWatch_CAN
.\.venv\Scripts\Activate.ps1
pytest tests\e2e -m e2e
```

## Continuous integration

`.github/workflows/ci.yml` runs for pushes to `main`, pull requests, and manual dispatches. The
quality job provisions PostgreSQL 17, installs Python 3.13 and Chromium, validates Alembic
migrations, runs Ruff, and executes the complete pytest suite with a 90% coverage floor. JUnit and
coverage XML reports are retained as workflow artifacts for 14 days.

A separate container job validates the Compose file, builds and starts the application and
PostgreSQL images, waits for both health checks, exercises the health and HTML endpoints, confirms
the active migration, and removes the ephemeral CI volumes. Neither CI job configures retailer
URLs, so automated builds cannot contact retailer websites.

## Persistence model

- `Product`: canonical Arc'teryx product identity and normalized searchable fields.
- `Retailer`: retailer metadata and stable slug.
- `Listing`: a retailer product URL and its most recent check time.
- `ProductVariant`: canonical product colour and size combination.
- `PriceSnapshot`: change-only price history for a listing and variant.
- `InventorySnapshot`: change-only three-state inventory history for a listing and variant.

The repository owns deduplication and database writes. Reprocessing the same variant at the same
timestamp does not duplicate products, listings, variants, or snapshots. A later check updates
`Listing.last_checked_at`, while a snapshot is appended only when its tracked value changes.

## HTTP and collection policy

`PoliteHttpClient` performs only HTTP/HTTPS GET requests and uses an identifying user agent. It
applies a request timeout, bounded retries for connection failures and HTTP 429/5xx responses,
exponential backoff, a capped `Retry-After`, and a minimum interval per retailer host. HTTP 4xx
responses such as 403 and 404 are not retried. Logs contain URL paths but omit query strings and
never contain response bodies.

`CollectionService` runs each adapter independently. If one adapter raises a timeout or parsing
error, the result records that retailer failure while retaining listings returned by other
adapters. No concurrent or high-volume third-party requests are implemented.

The HTTP defaults can be changed with:

- `GEARWATCH_HTTP_TIMEOUT_SECONDS`
- `GEARWATCH_HTTP_MAX_RETRIES`
- `GEARWATCH_HTTP_BACKOFF_SECONDS`
- `GEARWATCH_HTTP_MIN_INTERVAL_SECONDS`
- `GEARWATCH_HTTP_USER_AGENT`

## Run one collection cycle

No live URL is configured by default, so the command cannot accidentally contact a retailer.
Configure one or more query-free Canadian Outlet product pages in `.env`, separated by commas:

```dotenv
GEARWATCH_ARCTERYX_OUTLET_PRODUCT_URLS=https://outlet.arcteryx.com/ca/en/shop/mens/example-product
```

Apply migrations and run one cycle:

```powershell
Set-Location F:\GearWatch_CAN
.\.venv\Scripts\Activate.ps1
alembic upgrade head
python -m app.commands.collect
```

The command prints a JSON summary. A completed run exits with code `0`; a total collection or
database failure exits with `1`; missing/invalid configuration or a partial retailer failure exits
with `2`. Successful retailer rows are committed together. A persistence error rolls the entire
transaction back. Fixture rows are never included by this production command.

## Run scheduled collection

Scheduled collection is an opt-in Compose profile, so a normal `docker compose up` never contacts a
retailer. First configure one or more explicitly selected Outlet product URLs in `.env`:

```dotenv
GEARWATCH_ARCTERYX_OUTLET_PRODUCT_URLS=https://outlet.arcteryx.com/ca/en/shop/mens/example-product
GEARWATCH_COLLECTION_INTERVAL_SECONDS=21600
GEARWATCH_COLLECTION_RUN_ON_STARTUP=true
```

The default interval is six hours. The accepted range is 300 seconds through seven days. Start the
website, database, and scheduler with:

```powershell
Set-Location F:\GearWatch_CAN
docker compose --profile collection up -d --build
docker compose --profile collection ps
docker compose --profile collection logs --tail 50 collector
```

Stop scheduled collection without deleting the database:

```powershell
docker compose stop collector
```

The scheduler runs one cycle at a time and waits for the configured interval after completion, so
cycles cannot overlap. A failed or partially failed retailer cycle is logged and does not stop later
cycles. SIGINT/SIGTERM produces a graceful shutdown summary. Missing or invalid product URLs stop
the collector with configuration exit code `2`; the scheduler never falls back to fixture data.

## Search API

`GET /api/products` returns one row per retailer, colour, and size using the latest price and
inventory snapshots. Supported query parameters are:

- `q`: partial normalized product name or model search
- `model`: exact normalized model number
- `size` and `color`: normalized variant filters
- `min_discount`: `0` through `100`
- `stock_status`: `Available`, `Out of Stock`, or `Unknown`
- `limit`: `1` through `100`; `offset`: zero or greater

Example from Windows PowerShell while the app is running:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/products?q=Beta%20AR&size=M&stock_status=Available&min_discount=20"
```

An empty search is a successful `200` response with `items: []`. Invalid parameters return `422`.
Database failures return a sanitized `503` response without exposing driver messages.

## Product detail and history APIs

`GET /api/products/{product_id}` returns the canonical product and its current retailer/variant
offers. Each offer includes stable `listing_id` and `variant_id` values, the latest price and stock
state, the retailer link, and `last_checked_at`. The product-level `last_checked_at` is the newest
check across its active offers.

`GET /api/products/{product_id}/history` returns change-only price and inventory timelines grouped
by retailer listing, colour, and size. Optional `listing_id` and `variant_id` parameters narrow the
result. `limit_per_offer` defaults to `50`, accepts `1` through `200`, keeps the most recent points,
and returns them in chronological order for charting.

```powershell
$product = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/products/1"
$history = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/products/1/history?limit_per_offer=50"
$product.offers
$history.offers[0].price_history
```

These endpoints read saved snapshots and do not trigger retailer requests. Unknown product IDs
return `404`; invalid IDs or filters return `422`; database failures return a sanitized `503`.

## Server-rendered pages

`GET /` renders the search and comparison page. It supports product/model text, size, colour,
minimum discount, and three-state inventory filters. Each result links to
`GET /products/{product_id}`, which shows current retailer offers and the saved price/inventory
history for every colour and size. A small local JavaScript file progressively renders the price
points as SVG; the underlying history table remains visible without JavaScript.

Every normal, empty, and error page displays a Last checked area and explains that data is
periodically collected rather than real-time. Retailer links open in a new tab and remind the user
to confirm final price and availability. No external CSS, font, analytics, or chart dependency is
loaded by these pages.

### Playwright E2E policy

The browser suite starts a temporary local FastAPI server with deterministic service stubs. It
tests search, combined size/colour/discount/inventory filters, product navigation, the JavaScript
history chart, retailer-link clicks, no-result content, out-of-stock content, and 404/503 pages.
The synthetic retailer URL is intercepted and fulfilled inside Playwright, so E2E runs do not send
requests to third-party retailers. PostgreSQL behavior is covered separately by integration tests.

## Confirmed first data sources

- **Arc'teryx Outlet Canada**: first live-capable source for this personal, non-commercial project.
  The adapter accepts only explicitly configured Canadian HTTPS product pages. It reads standard
  JSON-LD for each colour/size price and availability, then matches the embedded application data by
  SKU for the original price. It does not crawl search results or discover URLs automatically.
- **Sporting Life**: second source, fixture-backed only. Its synthetic fixture exercises prices,
  sizes, colours, and the three-state inventory contract without accessing the retailer website.

No collector will bypass CAPTCHAs, authentication, bot protection, or other access restrictions.
If either source does not permit or reliably support polite HTTP access, its adapter will remain
fixture/mock based and the live-source choice will be revisited.

The Arc'teryx Outlet terms permit personal, non-commercial viewing/downloading, and its published
`robots.txt` does not disallow `/ca/en/shop/` product paths. This is a project-specific access
decision, not permission for commercial deployment. Re-check both documents before deployment or
changing the collection scope.

### Arc'teryx Outlet fixture policy

The committed Outlet fixture is synthetic and contains fictional product names, model numbers,
SKUs, prices, and stock states. It preserves only the JSON-LD and `__NEXT_DATA__` field shapes needed
for repeatable parser regression tests. Tests never call the live website.

### Sporting Life fixture policy

The committed Sporting Life fixtures are synthetic parser contracts, not copies of retailer HTML.
They contain fictional product names, model numbers, prices, and inventory states and must never be
displayed as current retailer data. The adapter makes no network requests. This keeps parser and
persistence development repeatable without copying site content or depending on third-party uptime.

## Known limitations

- The Sporting Life adapter is fixture-only; it does not collect real retailer data.
- Arc'teryx Outlet collection requires an explicit product URL list; automatic product discovery is
  not implemented.
- UI pagination is not implemented.
- The optional Chrome extension is not part of this MVP.
- Inventory will be periodic and may be stale; users must verify price and stock with the retailer.
