# M5 source and usage record

Updated 28 October 2026 (Australia/Sydney).

Source identified by the user: [Kaggle M5 Forecasting — Accuracy](https://www.kaggle.com/competitions/m5-forecasting-accuracy/data). Files were supplied from the user's local download folder and copied into `data/raw/`. No scraping, credential collection or access bypass was used. The earlier API HTTP 401 blocker was resolved by the user's supplied downloads.

Actual headers and contents were audited. The sales validation file contains `id`, `item_id`, `dept_id`, `cat_id`, `store_id`, `state_id`, and exactly `d_1` through `d_1913`. Calendar and price headers, complete row counts, selection details and SHA-256 hashes are recorded in `source_audit.json`. Original product/store IDs are preserved. Daily sales run from 2011-01-29 to 2016-04-24; calendar and prices extend beyond that sales file. Only dates in the selected sales period are joined; no price or calendar field is used to predict demand.

The [official competitors' guide](https://storage.googleapis.com/kaggle-forum-message-attachments/772349/15032/M5-Competitors-Guide-Final-10-March-2020.pdf) describes sales units, calendar joins and weekly average selling prices. M5 observations are aggregate daily product-store sales, not individual transaction records. The course implementation labels prices USD as specified by the PRD; currency is not encoded in the CSV column name. No currency conversion or financial analysis occurs in Phase 1.

The processed subset has five CA_1 series and 365 days each, 2015-04-26–2016-04-24. It joins prices by `item_id`, `store_id`, and `wm_yr_wk`, maps `cat_id` to `category_id` and `dept_id` to `department_id`, and preserves zero sales. All 1,825 selected records have positive prices. Missing prices remain blank if encountered in another selection.

## Usage and redistribution

The [official competition rules](https://www.kaggle.com/competitions/m5-forecasting-accuracy/rules) were checked again. The page exposed no readable rule text to the available web tool. Search results contain differing third-party licensing descriptions, which are not treated as authoritative permission for these files. Applicable redistribution rights therefore remain **unverified**, not confirmed or definitively denied.

The reviewed final ZIP and deployment allowlist exclude all M5 raw files, processed historical records, source-audit/result JSON, backtest actual observations, derived future forecasts and Phase 2 results calculated from those records. Older Phase 1–3 numerical reports and historical M5 screenshots are also excluded. These files remain available in the original local project; they are not copied to the public server or deployment repository. Source code, non-record documentation, official ABS lightweight snapshots and explicitly synthetic CSV examples may be distributed through the reviewed allowlist.

To reproduce the local M5 analysis, each user should obtain the original files legitimately and run the README preprocessing and forecasting commands. Verify applicable terms before sharing historical data or derived results. Access to a file does not itself prove redistribution rights. The synthetic public demo does not establish permission to redistribute M5.

No Downloads source file was modified by this work. After copying, calendar.csv and sell_prices.csv ceased to be visible at their original Downloads paths; only the project copies could be audited for those files. Source SHA-256 hashes identify the project copies; they do not independently authenticate a Kaggle download or prove licensing. See the Phase 1 report for this limitation.
