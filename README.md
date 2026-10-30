[English](README.md) | [简体中文](README_ZH.md)

> **Version note — 30 October 2026:** The documentation below preserves the information in the previous Chinese README, including historical release, test and packaging records. The currently verified application commit is `05a48bca901657e7b76faf696aabac78453e72b2`, and the latest source submission is `MarginGuard_COMP9001_Final_Source.zip`. For an extracted package without M5 data, use the environment settings in **Section 10** first. Inventory & Risk now supports direct inventory CSV upload and automatically matches and calculates confirmed stock; replacing user-edited assumptions still requires confirmation.

# MarginGuard — Retail Risk & Financial Decision Intelligence

MarginGuard provides demand forecasting, inventory-risk analysis and financial scenario support for small and medium-sized retailers, brand owners, purchasing managers and operations analysts. Python performs forecasting and statistical calculations; Flask provides the pages and APIs; HTML, CSS, vanilla JavaScript and local SVG charts handle interaction and presentation. Running the application does not require Node.js, an external chart CDN or a large language model API.

The application has two workspaces:

- **My Business:** the local `Explore Demo` workflow retains support for Walmart M5; the public website uses a separate **Synthetic Business Demo**. `Analyse My Business` provides bounded, temporary CSV analysis through anonymous sessions. Registration is not required, and long-term storage is not offered. The workflow is **Sales + Optional Inventory → Validate → Batch Forecast → Business Risk Overview → Review Product → Financial Decision**.
- **Market Intelligence:** presents official ABS industry statistics independently. These statistics do not alter product forecasts or financial assumptions.

Business uploads, AUD/USD financial contexts and cross-page input drafts from Restructure B are implemented. No business account is connected, and the application does not place purchase orders. [MarginGuard Online](https://marginguard-lkno.onrender.com) is publicly accessible without installing Python or keeping a Mac or Codex running. The earlier bulk-inventory release, `36dfb6933bdf3b9974eb27b06583c1c2c7e8a442`, was deployed as Live; its scope, tests and public acceptance are recorded in [BULK_INVENTORY_RISK_REPORT.md](BULK_INVENTORY_RISK_REPORT.md). Initial deployment is documented in [PUBLIC_DEPLOYMENT_REPORT.md](PUBLIC_DEPLOYMENT_REPORT.md); earlier public CSV and security acceptance in [POST_DEPLOYMENT_UAT_REPORT.md](POST_DEPLOYMENT_UAT_REPORT.md); and earlier local handoff in [FINAL_QA_REPORT.md](FINAL_QA_REPORT.md). Results in these historical reports apply to their respective versions and do not mean every security check was repeated for a later release.

## 1. Run independently on a Mac

Open the current `MarginGuard` folder in VS Code, or change to that directory in macOS Terminal:

```sh
./start.command
```

The launcher changes to its own directory, creates `.venv` if needed, installs `requirements.txt` if Flask is unavailable, and listens at **http://127.0.0.1:5050**. If extraction did not preserve executable permissions, use `sh start.command`. Keep the server's Terminal window open and press Ctrl+C to stop it. Codex is not required: quitting Codex does not stop a server launched from an independent Terminal. Start it again after logging out or restarting the Mac.

You can also start it manually:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Existing local environments support Python 3.9 or later; new environments should use the project's pinned **Python 3.12.14**. Production dependencies and versions are described in Section 9. Check your interpreter with `python3 --version`. Do not copy another computer's `.venv`, and do not open HTML templates through `file://`. For the source package without M5 files, first apply the switches in Section 10.

If a connection fails, check that Terminal shows `Running on http://127.0.0.1:5050`. Restart the server, then select **Retry connection** or refresh. A browser can retain an old page after Python has stopped. To investigate a port conflict, run `lsof -nP -iTCP:5050 -sTCP:LISTEN`; identify the process before deciding whether to stop it. After updating code or an ABS snapshot, stop the old server in its Terminal and restart it.

## 2. Try the complete workflow after extracting a handoff package

The earlier package, `MarginGuard_COMP9001_Final.zip`, contains source, tests, documentation, configuration, lightweight ABS snapshots and clearly labelled synthetic CSV files. It **excludes raw M5 records, processed sales, backtest actuals, forecast JSON and old numerical M5 reports**. It is not a backup of uploaded business data. M5 files in the original local project remain intact. The latest source-package name and its additions are listed in Section 10.

You can try the workflow without restoring M5:

1. Start the application and open **http://127.0.0.1:5050/?mode=business**.
2. Select `examples/business_csv/synthetic_84_days.csv`. Choose AUD or USD, a business time zone and a consistent tax basis. Confirm that you have permission to analyse the data and that sales quantities are recorded separately from returns.
3. Select **Validate CSV**, review the preview, missing values and continuous periods, then confirm the selected 84-day history.
4. **Business Risk Overview** lists every uploaded combination. Eligible, selected histories receive batch forecasts. Insufficient histories, unselected histories and missing inventory are explicitly **Not assessed**.
5. Use the stock-snapshot upload panel to validate and confirm a separate inventory CSV. The earlier panel was labelled **Add or replace a stock snapshot**; the current Inventory page has a direct **Upload Inventory CSV** entry. Single-product manual inventory analysis remains available, with an explicit stock date or a hypothetical historical stock position.
6. In Financial Decision Lab, enter financial assumptions and compare Wait, Reorder and Discount. Review feasibility, recommendation reasons and the Purchasing Decision Summary.

Synthetic examples support interface testing and teaching. They are not Walmart, ABS or verified enterprise records, and their prediction errors are not evidence of real-world accuracy. `synthetic_multi_series.csv` also supports product/store switching and draft-isolation demonstrations; all its values are synthetic. Field rules and reproducible assumed scenarios are documented in [examples/business_csv/README.md](examples/business_csv/README.md).

## 3. Pages, data sources and input drafts

| Route | Page | Purpose |
|---|---|---|
| `/` | Business Risk Overview in upload mode; Business Overview in Demo | Upload mode prioritises batch stock risks and data issues, then links to individual sales, forecasts and manual scenarios |
| `/forecasting` | Demand Forecasting | Historical trends, both methods' MAE, and separate historical backtests and future forecasts |
| `/inventory` | Inventory & Risk | Stock coverage, delivery-time demand, inventory position, suggested additional orders and rule explanations |
| `/scenarios` | Financial Decision Lab | Three-strategy financial results, budget/MOQ/service constraints and a purchasing summary |
| `/market` | Market Intelligence | Five navigation sections and seven ABS analysis areas on one page |

Business pages carry the selected context between them. Demo URLs use product/store IDs. Uploaded-data URLs contain only the mode and opaque dataset/version/series identifiers, not private product names, amounts or authentication tokens. ABS remains separate and is not inserted into My Business KPIs.

Input drafts use the current tab's `sessionStorage`, separated by **data source, dataset, revision, product–store series, forecast origin and currency**. Inventory and financial inputs are stored separately. CSV records, authentication tokens and calculated results are not written to Web Storage. Restoring complete inputs triggers a new Python calculation; switching products or sources does not reuse another context's inputs. Manual analysis remains available when browser storage is blocked, but cross-page retention is then not guaranteed.

In upload mode, **Business Risk Overview** is the main entry; Demo retains its original overview. The list follows Python's risk ordering and supports risk/store filters, product search and sorting. KPIs always describe the complete dataset; filtering changes only the list. Counts refer to Product + Store combinations, not distinct products. `Products Analysed` counts successfully forecasted combinations, which can also be included in `Data Incomplete` when inventory is missing. Primary inventory categories are mutually exclusive, and `Reorder Attention` is reported separately; the five cards cannot simply be added together.

Opening an inventory or financial detail carries the dataset revision and exact series. Confirmed stock can be reviewed through **Review snapshot inputs → Apply reviewed inputs**, with the proposed order quantity confirmed separately; stock uploads do not replace prices, costs or budgets. Confirming a new snapshot creates a new revision, so earlier results cannot remain current. A manual single-product scenario does not change the confirmed snapshot in the batch overview. The current automatic Inventory import and preservation of edited drafts are explained in Section 10.

Inventory → Decision Lab offers **Use inventory assumptions** and **Use suggested quantity**. Both show the proposed replacements and wait for confirmation. **Proposed Order Quantity** is an inventory-rule result, not a globally optimal purchase. Positive on-order stock blocks automatic financial transfer because the model cannot schedule those existing deliveries. A separate manual scenario requires explicit confirmation that it excludes those units and their costs.

**Reset current assumptions** clears both inventory and financial drafts for the current context. Demo restores disclosed example assumptions; upload mode restores blank inputs. Deletion or expiry invalidates server data and clears related upload drafts. Changed inputs hide old results, and stale responses cannot overwrite a new context. Drafts are a convenience, not authentication or long-term storage. Tabs in the same browser may share a server-session cookie and should not be treated as independent user accounts.

## 4. Business CSV files and temporary-data protection

Public entry: [Analyse My Business](https://marginguard-lkno.onrender.com/?mode=business). The free service supports portfolio demonstrations and short-term analysis, not long-term storage of sensitive business data. Keep your original files and do not upload customer, payment or other personal information.

Required sales columns: `Date,Product,Store,Units Sold`; optional: `Unit Price,Unit Cost`. Files must use UTF-8 or UTF-8 BOM, with strict `YYYY-MM-DD` dates and one row per product/store/day.

- Negative or non-integer sales, duplicate keys, invalid dates, invalid amounts and invalid identifiers are rejected. Duplicate records are not automatically summed.
- An explicit `0` means zero sales. Missing dates and blank sales are unknown and are not filled with zero.
- Only gross sold units are supported. Keep returns separate. A declaration cannot prove that positive values have never had returns deducted; users must confirm the meaning of their quantities.
- Each forecast needs at least **42 consecutive valid dates**; **84 days or more** are recommended. Users may select a complete subperiod but cannot span unknown dates. Forecasts immediately follow the selected history, not automatically today's date.
- Blank prices/costs stay unknown. Historical references enter assumptions only when the user explicitly chooses them. Existing-stock cost and new-purchase cost are entered separately; one historical cost is not silently applied to both.
- One dataset uses either **AUD or USD**. Every amount must use the same currency and tax basis. There is no exchange-rate conversion or tax calculation. ABS figures remain AUD and cannot be directly combined with USD product amounts.

Limits differ by environment. Public configuration is more conservative; the upload panel displays the limits returned by the server:

| Item | Local defaults | Current conservative public configuration |
|---|---|---|
| CSV | 5 MiB, 50,000 rows, 100 combinations | 1 MiB, 10,000 rows, 20 combinations; maximum history span remains 1,096 days |
| Pending data | Expires after 15 minutes | Same |
| Anonymous session | Expires after 30 idle minutes or 2 hours total, whichever is earlier | Same; sleep/restarts may invalidate it earlier |
| Computation | 5-second timeout, 2 shared slots | 5 seconds, 1 shared slot; 128 MiB Linux child-process limit; processing is rejected if resource limits cannot be applied |
| Request frequency | Per session: 3 uploads per 10 minutes and 30 computations per minute | Same session rules, plus global per-minute admission limits of 240 requests, 20 session creations, 12 uploads and 60 computations |
| Private storage | SQLite outside the repository; 20 MiB per dataset and 500 MiB total payload | 2 MiB per dataset, 16 MiB total payload, at most 20 sessions; SQLite and journal files need additional space |

The server checks upload ownership against the session. POST/DELETE requests require CSRF and origin validation. Uploaded content is never executed as code. Arbitrary local paths are not accepted, and original uploaded files are not offered for download. Private responses use `no-store`. Business data is excluded from GitHub, static files and final ZIPs. These controls and quotas do not constitute an independent production-security audit.

Expiry is checked when requests arrive, and periodic background cleanup handles expired storage. Physical deletion is not promised at the exact expiry second. Restarts, deployments or temporary-disk loss may make data unavailable earlier. Deleted data, replaced datasets and expired sessions cannot be recovered. Do not use the application as your only backup or upload customer, payment or other personal information.

Main endpoints include `GET /api/business/session`, `POST /api/business/uploads`, confirmation endpoints, private catalog/analysis/inventory/scenarios endpoints and DELETE operations. API contracts, security tests and limits are documented in [PHASE5B_REPORT.md](PHASE5B_REPORT.md); pages and parameter retention in [PHASE5C_REPORT.md](PHASE5C_REPORT.md) and [RESTRUCTURE_B_REPORT.md](RESTRUCTURE_B_REPORT.md).

### Optional inventory CSV

Use `examples/business_csv/inventory_template.csv`. Its header is:

```csv
Product,Store,Stock As Of Date,Current Stock,Supplier Lead Time,Safety Stock,On-order Units
```

`On-order Units` is optional. The other headings are required; blank values remain unknown, and missing product/store identifiers cannot be matched. Current stock, backup stock and open orders must be non-negative whole units, at most 1,000,000. Delivery time must be a whole number from 0 to 365 days. Dates must be strict `YYYY-MM-DD` and refer to a completed business day. Only one row per product/store is allowed, even if dates differ.

`Stock As Of Date` is the closing-stock date and must exactly equal the **last day of that combination's selected sales history**. Incompatible dates are not rolled forward, back-calculated or silently combined. The row remains unassessed until an aligned snapshot is uploaded, or a single-product scenario explicitly uses hypothetical stock at the historical forecast origin. Unmatched rows and sales combinations without stock are reported separately. Missing on-order data is not assumed to be zero. Only an explicit no-open-orders declaration sets blank values to zero; recorded positive orders are unchanged. The excess-cover threshold is an explicit planning assumption, initially 30 days in the form, not an industry benchmark.

Inventory and sales CSVs share per-session upload frequency, file-size, temporary-storage and global-compute limits. Public inventory uploads are limited to 20 rows. There is no separate database or public download of uploaded records. Validation produces a preview, followed by atomic confirmation. Confirmation replaces only the inventory attachment and updates the revision, preserving sales history and forecasts. Deleting a sales dataset also deletes its linked inventory drafts. Restart and expiry rules are the same as for sales.

For the original three-combination synthetic example, first confirm the 84-day `synthetic_multi_series.csv`, then upload `synthetic_inventory_multi_series.csv`. With a 30-day excess threshold, the three combinations show one shortage, one excess and one with sufficient delivery-time demand and backup coverage. These are deliberately constructed demonstration records, not evidence of actual enterprise risk or forecast accuracy.

Additional private endpoints are `GET /api/business/datasets/<id>/inventory-risk` (revision required; risk/store/search/sort supported), `POST /api/business/datasets/<id>/inventory-uploads`, and the draft's `/confirm` and DELETE operations. The template has a fixed download path, `/api/business/inventory-template.csv`. Requests do not accept arbitrary file paths, client-supplied forecasts or another user's identifier. Implementation and that release's acceptance are in [BULK_INVENTORY_RISK_REPORT.md](BULK_INVENTORY_RISK_REPORT.md).

## 5. Forecasting, inventory and financial rules

The original formulas in `forecast.py` are unchanged. The final 14 observations form the chronological backtest. The 7-day Moving Average uses the last seven training days; Same-Weekday Average uses the four occurrences of each weekday in the last 28 training days. Both are evaluated on the same holdout using MAE. An exact tie selects moving average. The selected method is then refitted to all confirmed history for a separate forecast over the next 14 calendar days. Holdout actuals do not enter their corresponding training window.

`business_csv.py` validates data, and `business_forecast.py` adapts it to the existing forecasting interface. Its `financial_analysis_available=False` means only that **the forecast-adapter result itself** does not contain financial analysis. The complete website calculates financial results separately through `finance.py` and `scenario.py`; this flag does not mean that the site lacks financial functionality.

| Module | Main rules |
|---|---|
| `inventory.inventory_risk` | Average demand; days of cover = stock / average demand; inventory position = stock + open orders; target = lead-time demand + safety stock; suggested additional units = max(0, ceil(target − inventory position)) |
| `finance.procurement` | New-purchase cash = unit purchase cost × quantity + freight + other charges; unit landed cost = that amount / purchased quantity |
| `finance.gross_profit` | Revenue = price × units sold; existing and new stock have separate COGS; gross profit = revenue − COGS; margin = gross profit / revenue × 100 |
| `finance.lost_sales` | Potential lost revenue = unmet units × price; potential lost gross profit = unmet units × unit contribution |
| `scenario.simulate` | Inventory is consumed daily, existing stock first; new units can sell only after arrival |
| `scenario.compare_strategies` | Among the three tested strategies meeting MOQ, budget and any unmet-demand constraint, select the one with the highest unrounded gross profit |

With zero demand, days of cover is `None`. Delivery times beyond 14 days are explicitly extrapolated using the forecast's 14-day average. Status priority is shortage, reorder attention, excess attention, then sufficient inventory. The user sets the excess threshold; the default demonstration value is 30 days. Open orders reduce the replenishment gap but, without arrival dates, are not assumed to meet immediate demand.

A seven-day delivery time means arrival on day 8; zero means day 1; 14 or more means no arrival within the forecast period. Unmet demand is treated as lost sales, not backorders. New procurement cash is not all charged immediately to current-period COGS, and new freight does not change the cost of existing inventory. Zero purchase quantity with non-zero freight/other charges is invalid. Zero revenue gives a margin of `None`. Forecast demand remains a fractional expectation.

Discount price = price × (1 − discount/100); demand = forecast × (1 + assumed uplift/100). Uplift is a user assumption, not validated price elasticity. Exact recommendation ties prefer Wait → Reorder → Discount. If no strategy is feasible, none is recommended. Budget constrains new-purchase cash only. Without a service constraint, unmet demand is disclosed but does not automatically make a strategy infeasible. There is no tax, storage-cost, operating-expense or demand-uncertainty model, so actual profit and a globally optimal result are not guaranteed.

AUD/USD is carried in a consistent currency context through financial functions and API results, and the frontend formats amounts accordingly. Numerical formulas and rounding rules are consistent; changing a USD label to AUD is not presented as currency conversion. Background is in [AUD_USD_CURRENCY_DESIGN.md](AUD_USD_CURRENCY_DESIGN.md).

## 6. Restore the Walmart M5 Demo locally

The original development folder retains local M5 data; it does not need another download or rebuild. These instructions apply to an **extracted package without generated M5 files**. If results already exist, verify and back them up before replacing anything. Obtain the three CSVs legitimately, copy them to `data/raw/`, and preserve the download originals:

- `sales_train_validation.csv`
- `calendar.csv`
- `sell_prices.csv`

After activating the environment, run from the project root:

```sh
python scripts/audit_m5.py
python scripts/prepare_m5.py --raw-dir data/raw --items FOODS_3_586 FOODS_3_252 HOUSEHOLD_1_535 HOUSEHOLD_1_334 HOBBIES_1_147 --stores CA_1 --days 365
python run_phase1.py
python run_phase2.py
```

Restart the site and view the restored data through **Explore Demo**. The fixed five-series configuration supports the existing real-data regression checks. Other products need their own selection and validation; the original checks do not automatically cover a new configuration.

Generated local files include `source_audit.json`, `processed_sales.csv`, `processed_sales.validation.json`, `forecast_results.json` with backtests, a separate `forecast_results_future.json`, and Phase 2 simulation outputs. M5 preprocessing rejects missing dates, negative sales, duplicate keys and all-zero series while preserving explicit zero observations. The upload workflow has separate rules for unknown data and all-zero test histories; these validation paths must not be conflated.

The Phase 1/2 CLI uses the Python standard library and remains independently runnable. To change scenario assumptions, copy defaults to another local file and run:

```sh
python run_phase2.py --parameters /path/to/my_assumptions.json --output /path/to/my_result.json
```

M5 sourcing is described in [data/DATA_SOURCE.md](data/DATA_SOURCE.md). Public display and redistribution rights remain unconfirmed. Having legitimate local files does not itself authorise public upload. Final packaging excludes raw data, derived records and forecasts without deleting the original project files.

## 7. ABS Market Intelligence and offline reproduction

Open **http://127.0.0.1:5050/market**. The page reads processed snapshots in `data/abs/`; it does not parse Excel at request time. Restart Flask after updating a snapshot.

The fixed snapshots cover MHSI August 2026, Business Indicators Q2 2026 and Business Counts through June 2026. They are historical snapshots, **not an automatically updated live feed**. Each indicator retains its reference period, frequency, unit, classification, adjustment, release date and source. Tables and Series IDs are recorded in `data/abs/sources.json`, `market_catalog.json` and [PHASE4A_REPORT.md](PHASE4A_REPORT.md).

- Python calculates month/quarter-on-quarter and year-on-year changes as `(current / corresponding previous − 1) × 100`. Missing or non-positive comparison bases return `null`, not zero.
- Original, Seasonally Adjusted and Trend remain separate; Monthly, Quarterly and Financial Year are not mixed.
- MHSI Table 19 is always labelled **Experimental** and is not spliced to the discontinued Retail Trade series. COICOP and ANZSIC remain separate.
- ABS Business Gross Operating Profits is not product gross profit. The official inventory-to-sales ratio compares quarter-end stock with quarterly flow; it is not inventory days or a firm's risk score.
- Business counts are not store counts, exits are not a bankruptcy measure, and the two survival cohorts are explained separately.
- ABS monetary values are AUD. My Business uses the selected AUD/USD; there is no cross-source currency conversion or direct market benchmark.

Read-only APIs are `/api/market/catalog`, `overview`, `series`, `compare`, `business-counts` and `sources`. Parameters select existing catalogued series and statistical bases; arbitrary local paths are not accepted. Sources, filters and API details are in [PHASE4B_REPORT.md](PHASE4B_REPORT.md).

Rebuilding from already downloaded Excel files requires optional dependencies:

```sh
python -m pip install -r requirements-abs.txt
python scripts/prepare_abs.py --dataset all --research-dir ../../research/datasets --as-of 2026-10-28 --overwrite
```

Run this only when you have the original research files and explicitly need to rebuild. Workbooks are not included in the final ZIP. Point the research path to the parent directory of legitimately downloaded files. The generator verifies SHA-256 values in `sources.json` and does not download files automatically. `--overwrite` explicitly replaces selected ABS outputs; use a different `--output-dir` to retain earlier results. `--dataset market` or `counts` can rebuild each part independently. `--as-of` is a source-availability cutoff, not a reconstruction of another published vintage.

ABS content is attributed to the Australian Bureau of Statistics under its official [copyright and attribution terms](https://www.abs.gov.au/website-privacy-copyright-and-disclaimer). General CC BY 4.0 availability is subject to ABS exclusions. The project does not use the ABS logo or imply endorsement.

## 8. Tests and historical packaging

The full Python suite needs Flask and the ABS test dependencies:

```sh
python -m pip install -r requirements-abs.txt
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
python -m pip check
```

The earlier bulk-inventory release retained 348 Python and 29 Node tests and added 105 Python and 22 Node regressions. Its complete local result was **Python 453/453 and Node 51/51 passing**. The associated GitHub CI record reported 434 executed/passing Python methods and 19 methods requiring local M5 or ABS research files not executed. Its unittest summary was `Ran 437`, `skipped=5`, including class-level skips; those summary counts must not simply be treated as the number of individual methods passed. That release's environment and public evidence are in [BULK_INVENTORY_RISK_REPORT.md](BULK_INVENTORY_RISK_REPORT.md). [POST_DEPLOYMENT_UAT_REPORT.md](POST_DEPLOYMENT_UAT_REPORT.md) and [FINAL_QA_REPORT.md](FINAL_QA_REPORT.md) retain earlier evidence. Counts such as 61/109/141/348 describe historical stages, not the current total; historical security checks are not counted as later reruns. Current documented results are summarised in Section 10.

Frontend drafts have separate Node tests. Node is a development test runner, not an application runtime dependency. The original command was:

```sh
node --test tests/business_context.test.js tests/uat_business_ui.test.js tests/business_risk.test.js
```

When local M5 or original ABS workbooks are absent, their integration checks explicitly skip. A skip is not real-file validation. Synthetic tests verify software behaviour only. Browser interactions and mobile layout are recorded separately in QA reports; HTTP 200 alone is not interface acceptance.

The development repository's historical handoff packager can be run with:

```sh
python scripts/package_final.py
```

It writes `MarginGuard_COMP9001_Final.zip` beside the project (`outputs/` in the development layout). It refuses to overwrite an existing ZIP; select a new name with `--output /path/to/a/new-name.zip`. It uses an explicit file allowlist, writes per-file SHA-256 values in `MANIFEST.json` and `PACKAGE_SCOPE.md`, and preserves required directories. This is the older internal bundle, not the latest source submission; see Section 10 for its exclusion from the new ZIP.

Excluded content includes all M5 records/forecasts, real business uploads, temporary databases, secrets, logs, caches, environments, large research files, old ZIPs and unreviewed files. Only explicitly synthetic or ABS screenshots are permitted. Older Phase 1/3 packaging scripts and archives are retained for historical use in the original folder and should not build the current handoff.

## 9. Production operation and public deployment

Production files include `.python-version` (**3.12.14**), `requirements-production.txt`, `wsgi.py`, `gunicorn.conf.py`, `runtime_config.py` and `render.yaml`. GitHub uses the private `cici-rwei/MarginGuard` repository, whose root is this project directory. Render Root Directory is blank. Build command: `pip install -r requirements-production.txt`; start command: `gunicorn -c gunicorn.conf.py wsgi:app`; health check: `/api/features`. [BULK_INVENTORY_RISK_REPORT.md](BULK_INVENTORY_RISK_REPORT.md) documents the earlier bulk release; the latest application baseline is in Section 10. Initial deployment is in [PUBLIC_DEPLOYMENT_REPORT.md](PUBLIC_DEPLOYMENT_REPORT.md), with historical preparation in [DEPLOYMENT_REPORT.md](DEPLOYMENT_REPORT.md) and [DEPLOYMENT_EVIDENCE.md](DEPLOYMENT_EVIDENCE.md).

With Python 3.12.14 installed, create an independent production-check environment:

```sh
python3.12 -m venv .venv-production
.venv-production/bin/python -m pip install -r requirements-production.txt
.venv-production/bin/python -m pip check
.venv-production/bin/gunicorn -c gunicorn.conf.py wsgi:app
```

Gunicorn defaults to `0.0.0.0:8000`, configurable through `PORT`. This is a WSGI startup example, not a complete secure public deployment. Do not expose the Flask development server directly to the internet. Production should pin Python, use platform TLS, validate hosts and use a correctly configured trusted proxy topology.

| Environment variable | Purpose |
|---|---|
| `MARGINGUARD_PUBLIC=true` | Enables public-environment constraints, disables Debug and uses Secure cookies |
| `MARGINGUARD_SECRET_KEY` | Random secret of at least 32 characters, injected by the platform; never stored in the repository or reports |
| `ENABLE_BUSINESS_UPLOAD` | Defaults to `false` in public mode; the existing Render service explicitly enables it after controlled acceptance |
| `ENABLE_BUSINESS_UPLOAD_REVIEW` | `false` in the public configuration; the temporary acceptance gate is closed |
| `MARGINGUARD_UPLOAD_REVIEW_KEY_SHA256` / `MARGINGUARD_UPLOAD_REVIEW_DEADLINE` | Empty and `0`, respectively, in public configuration; no temporary review access is left active |
| `ENABLE_SYNTHETIC_DEMO` | Independent switch; enabled on Render, `false` by default locally |
| `ENABLE_M5_DEMO` | Defaults to `false` in public configuration |
| `M5_PUBLIC_LICENSE_CONFIRMED` | May be true only after actual display/redistribution rights are verified; the switch itself grants no licence |
| `MARGINGUARD_PRIVATE_DIR` | Private temporary directory outside the repository, static files and public mounts |
| `TRUST_REVERSE_PROXY` | Enable only behind a confirmed trusted TLS-terminating proxy |

The current Render configuration exposes the synthetic business demo, ABS and bounded temporary CSV analysis. M5 data APIs and the controlled-review gate remain closed. Upload safety and M5 licensing are separate gates: enabling user CSVs does not grant M5 display rights. Production access logs record status and duration only, excluding query strings, cookies, bodies and business sales details. Synthetic Demo does not create an upload session or SQLite record and does not persist a visitor's calculated results. Input drafts remain source-separated in the current tab. The free deployment is a single-instance portfolio service that may sleep or cold-start; no enterprise production SLA is promised.

Synthetic Demo reads the fixed `examples/business_csv/synthetic_84_days.csv`. Its history is 2024-01-01–2024-03-24 and its simulated forecast is 2024-03-25–2024-04-07. It is deliberately constructed teaching data, not real enterprise transactions. MAE from its repeating weekly pattern does not establish real-world generalisation. Currency is explicitly AUD and is passed into the existing financial engine without conversion. Stock, prices, costs, purchasing and promotional uplift are editable demonstration assumptions; the existing Python engines calculate their results.

To open that demo locally:

```sh
ENABLE_SYNTHETIC_DEMO=true ENABLE_M5_DEMO=false ENABLE_BUSINESS_UPLOAD=false python app.py
```

Visit `http://127.0.0.1:5050/?mode=synthetic`. This is a local functional check. Public operation still requires `MARGINGUARD_PUBLIC=true`, a platform-generated secret and HTTPS acceptance. Fixed-sample APIs are `/api/demo/catalog`, `/api/demo/analysis`, `/api/demo/inventory` and `/api/demo/scenarios`; they do not accept client file paths or custom forecast series.

For later code releases, run tests, review and stage necessary files against `deployment_files.json`, inspect `git diff --cached`, then commit and push. Do not use an unaudited `git add .`. GitHub Actions supplies CI without restricted M5/original Excel files. Render uses **After CI Checks Pass**, and that automatic update path has been verified. The free service is in Singapore at [MarginGuard Online](https://marginguard-lkno.onrender.com). Root Markdown and `deployment_files.json` changes are excluded by build filters and do not restart the application; code, dependencies, data and configuration still deploy after CI. For upload-security problems, close public upload and review access while retaining Synthetic Demo/ABS and the capacity, global-rate-limit and job-lease fixes. A rollback should retain those protections, or use a tested `git revert` followed by a push. Do not reopen uploads with earlier permissive settings or force-push over history.

Run cleanup as the same system user and with the same private storage directory as the service:

```sh
python scripts/cleanup_business_data.py --storage-root /absolute/private/directory
```

The official rubric, accepted Advanced Topics and AI-disclosure requirements still need checking against course documents. Historical materials are [COMP9001_COMPLIANCE.md](COMP9001_COMPLIANCE.md), [AI_USE_DECLARATION.md](AI_USE_DECLARATION.md), [PADLET_DRAFT.md](PADLET_DRAFT.md) and [DEMO_SCRIPT_3MIN.md](DEMO_SCRIPT_3MIN.md). Unverified points must not be described as approved by the course. The latest source package intentionally omits the AI draft and obsolete Padlet draft; current materials are described below.

## Historical post-deployment acceptance and public upload status

The earlier application commit `36dfb6933bdf3b9974eb27b06583c1c2c7e8a442` was deployed Live with **Business Risk Overview** and optional inventory CSV upload, retaining Synthetic Demo, single-product workflows and ABS. Its deployment, public checks and unverified areas are recorded in [BULK_INVENTORY_RISK_REPORT.md](BULK_INVENTORY_RISK_REPORT.md). This historical record does not supersede the newer application baseline in Section 10.

**Bounded temporary CSV analysis** remains publicly available without an acceptance credential. Public limits remain 1 MiB, 10,000 sales rows and 20 product–store combinations; inventory CSVs have at most 20 rows. Pending data expires after 15 minutes. Sessions expire after 30 idle minutes or 2 hours total, whichever is earlier. Restart, sleep or deployment can remove data earlier. Closing a tab is not deletion; use **Delete uploaded data** to remove it explicitly. Public M5 APIs remain closed.

Earlier Part A usability and Part B upload-release acceptance included 189/189 HTTPS checks on application `091dd76`, recorded in [POST_DEPLOYMENT_UAT_REPORT.md](POST_DEPLOYMENT_UAT_REPORT.md). That historical expiry, restart, isolation and race-condition evidence is not counted as a fresh check of each later version. The controlled gate remains closed. Claims about actual worker timeouts, total Render RSS/disk headroom or forensic cloud-media erasure must be limited to each report's stated scope. Historical passing checks or local unit tests are not proof of a new public verification. The free service is for portfolio display and short-term analysis, not long-term sensitive storage or an enterprise SLA.

## 10. Latest handoff: bilingual documentation, source package and demo — 30 October 2026

### Local startup without M5 data

In the extracted `MarginGuard` folder, use an installed Python 3.12 interpreter; the verified version is 3.12.14:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export MARGINGUARD_PUBLIC=false
export ENABLE_M5_DEMO=false
export ENABLE_SYNTHETIC_DEMO=true
export ENABLE_BUSINESS_UPLOAD=true
python app.py
```

If your Python 3.12 interpreter is called `python3`, use that name on the first line. Open `http://127.0.0.1:5050/` and keep Terminal running. These switches make the included demos work without missing M5 files; they do not change the data or upload anything publicly. After setting them, `sh start.command` is also available.

### Paired sales and inventory CSVs

The source ZIP includes `examples/business_csv/demo_sales_10_series.csv` and `demo_inventory_10_series.csv`. They are byte-for-byte copies of the previously verified files, renamed only for convenience: `01_先上传销售_Kaggle模拟.csv` and `02_再上传库存_情景假设.csv`. The renamed copies are supplied in the ZIP; this documentation update does not add them separately to the original development checkout.

1. In **Analyse My Business**, upload the sales file first. Select **USD** and `Australia/Sydney`, review the tax basis and declarations, validate and confirm the full history.
2. Open **Inventory & Risk → Upload Inventory CSV**. Upload the inventory file, review matches and dates, then confirm the snapshot. Do not put inventory in the sales uploader.
3. Valid stock is automatically populated and calculated; missing stock remains **Unknown**. Manual edits invalidate old results, and replacing edited inputs needs confirmation. Changed dataset versions cannot reuse old calculated results; manual inventory drafts are retained for review.
4. The ten demonstration combinations show four shortages, three excess-stock cases and three sufficient-stock cases. Suggested additional orders are **748** for `SIM_P0001 / SIM_S001` and **1032** for `SIM_P0002 / SIM_S002`, consistent across Overview, Inventory and the Decision Lab import. The integer boundary absorbs tiny floating-point residuals; genuine fractional requirements still round up.
5. In Decision Lab, separately review and confirm inventory and proposed-order imports. Enter prices, costs and budget explicitly. With a selling price of USD 10, existing/new unit costs of USD 2, zero freight/other charges, MOQ of 0, a seven-day delivery time, a USD 10,000 budget and zero discount/uplift, procurement cash is USD 1,496 and USD 2,064, respectively, with arrival on day 8. These are neither globally optimal orders nor verified enterprise results.

The sales file has 1,840 rows and inventory has ten. Each history runs from 2023-07-01 to 2023-12-31, with forecasts for 2024-01-01 to 2024-01-14. Sales are a subset of the explicitly synthetic, CC0 [Kaggle Retail Store Inventory Forecasting Dataset](https://www.kaggle.com/datasets/anirudhchauhan/retail-store-inventory-forecasting-dataset). Stock, delivery time, backup stock and USD denomination are separate test assumptions. Source beginning-of-day inventory is not relabelled as closing stock, and the source's precomputed demand forecast is not used. The ZIP's `examples/business_csv/DEMO_PAIR_SOURCE.md` records this distinction. No sensitive business records have been added.

### Source-package contents and verification boundaries

- `MarginGuard_COMP9001_Final_Source.zip` includes `README.md` in English, `README_ZH.md` in Chinese, the complete website runtime source, required assets, tests, ABS lightweight snapshots, permitted demonstration CSVs, Padlet materials and per-file hashes. M5 raw/derived records, private uploads, sessions, secrets, caches and earlier ZIPs are excluded.
- Program files match deployed application `05a48bc`. This bilingual update changes documentation and the submission package only. A newer documentation commit on GitHub is not a new running application version.
- During the previous handoff, the ZIP was extracted and started in a fresh Python 3.12 environment with `requirements.txt`; five pages, Synthetic Demo's 14-day forecast and eight reorder regressions were verified. This documentation update checks documentation, archive contents and program hashes only; it does not repeat a large test suite or production-security acceptance.
- The latest documented full local regression result is Python 465/465 and JavaScript 75/75. Its GitHub CI summary is `Ran 449 / skipped=5`, including skips for unavailable local M5/optional original ABS files. The preceding sequential HTTPS acceptance passed 50/50 checks. These are earlier acceptance records, not tests rerun for this translation.
- Free instances can sleep. Concurrent calculations may return `429 processing_busy`; wait for the active calculation before retrying instead of repeatedly clicking. Restarts can invalidate temporary data early.
- The development repository retains the old internal ZIP builder. The latest source ZIP excludes that builder and its packaging-only test, the obsolete Padlet draft and the AI declaration, as described in `SOURCE_PACKAGE.md`. Section 8's `scripts/package_final.py` builds the older handoff type and does not rebuild the latest source ZIP.
- Current presentation materials are in the ZIP's `padlet/PADLET_SUBMISSION.md` with three genuine public-site screenshots. No verifiable official COMP9001 rubric or original Padlet specification was found locally; confirm the word limit, image count, submission channel and identity details yourself. The package contains no AI Use Declaration, and none was generated for this update; the student must complete it separately. Nothing was posted to Padlet on the student's behalf.

Use `MarginGuard_COMP9001_Final_Source.zip` in the local `outputs/` handoff directory. Both README files link to each other at the top. Existing Render build filters ignore root Markdown; only these two README files are committed, without changing build configuration or the application.
