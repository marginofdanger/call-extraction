# EDGAR Earnings Release Download Skill — Design

**Date:** 2026-03-03
**Status:** Approved

## Overview

A single skill (`/edgar-download`) that discovers, downloads, parses, and structures earnings releases from SEC EDGAR. Supplements the existing BamSEC transcript pipeline with official SEC filings (8-K press releases, financial supplements, 10-Q/10-K, and XBRL data).

## Invocation

```
/edgar-download TICKER [QUARTER]
```

- If QUARTER omitted, download all quarters in config
- Skip quarters where `{QUARTER}_financials.json` already exists and is >100 bytes

## Architecture: Submissions API + Filing Index (Approach A)

Uses the SEC EDGAR REST APIs (no authentication, just User-Agent header):

1. **`data.sec.gov/submissions/CIK{padded}.json`** — Company filing history
2. **`data.sec.gov/api/xbrl/companyfacts/CIK{padded}.json`** — Structured XBRL financial data
3. **Filing index pages** — To discover exhibit files (EX-99.1, EX-99.2)
4. **Exhibit HTML** — The actual press release and financial supplement content

## Config Integration

Adds to existing `config.yaml`:

```yaml
company:
  edgar_cik: "0000019617"  # Discovered from ticker, saved once

quarters:
  - id: Q4_2025
    call_date: "January 14, 2026"
    bamsec_id: "f4dc1286-..."
    edgar_8k_accession: "0001628280-26-001902"    # Item 2.02 filing
    edgar_8k_supplement: "0001628280-26-001915"    # Item 7.01 filing (if separate)
```

## Output Directory

`companies/{TICKER}/edgar/` containing per quarter:

| File | Description |
|------|-------------|
| `{QUARTER}_press_release.htm` | Raw EX-99.1 HTML (earnings press release) |
| `{QUARTER}_supplement.htm` | Raw EX-99.2 HTML (financial supplement, if present) |
| `{QUARTER}_financials.json` | Parsed structured data (tables + XBRL) |
| `{QUARTER}_earnings.md` | Readable markdown summary |
| `{QUARTER}_10q.htm` / `{QUARTER}_10k.htm` | Quarterly/annual report primary document |

## Python Script

**File:** `edgar_download.py`
**Usage:** `python edgar_download.py TICKER [QUARTER] [--discover-only] [--parse-only]`
**Dependencies:** `requests`, `beautifulsoup4`, `pyyaml`

### Core Flow

```
CIK Lookup → Filing Discovery → Download Exhibits → Parse Tables → XBRL Enrichment → Markdown Generation
```

### Step 1: CIK Resolution

- Fetch `https://www.sec.gov/files/company_tickers.json`
- Look up ticker → CIK (e.g., `JPM` → `0000019617`)
- Save `edgar_cik` to config.yaml (one-time)

### Step 2: Filing Discovery

- Fetch `data.sec.gov/submissions/CIK{padded}.json`
- Scan `filings.recent` for `form=8-K` with `2.02` in `items` field
- For quarters whose `call_date` falls outside the recent filings' date range:
  - Check `filings.files[]` overflow metadata (`filingFrom`/`filingTo` ranges)
  - Fetch only the 1-2 overflow files whose date range covers the target quarter
- Also collect companion 8-Ks filed same day with Item `7.01` (financial supplement)
- Record 10-Q and 10-K accessions matched by `reportDate`

### Step 3: Quarter Matching

- Parse each config quarter's `call_date` into a date
- Find the 8-K with Item 2.02 whose `filingDate` is within **±3 days** of `call_date`
- If no match, widen to ±7 days and warn
- This handles press releases filed evening before the call, or same day

### Step 4: Download Exhibits

- Build filing index URL: `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_dashed}/{accession}-index.htm`
- Parse index to find EX-99.1 (press release) and EX-99.2 (supplement) filenames
- Download exhibit HTML files to `companies/{TICKER}/edgar/`

### Step 5: Parse HTML Tables → JSON

- Use BeautifulSoup to find all `<table>` elements in press release
- Identify financial tables by heuristics (dollar signs, percentage signs, common headers like "Revenue", "Net Income", "EPS")
- Extract each table as list of row objects with column headers as keys
- Handle formatting: parentheses for negatives, em-dashes for zero, footnote markers
- Group tables by detected type (Income Statement, Balance Sheet, Segment, etc.)

### Step 6: XBRL Enrichment

- Single call to `data.sec.gov/api/xbrl/companyfacts/CIK{padded}.json` (cached per run)
- Filter facts by `end` date matching the quarter's period end
- Merge key metrics (Revenue, Net Income, EPS, Assets, etc.) into JSON under `xbrl` key

### Step 7: Markdown Generation

- Header with company name, quarter, filing date
- Key financials from parsed tables
- Links to source filing on EDGAR
- Structured summary of reported actuals (not a full editorial extraction)

## JSON Output Structure

```json
{
  "ticker": "JPM",
  "quarter": "Q4_2025",
  "filing_date": "2026-01-13",
  "accession": "0001628280-26-001902",
  "tables": [
    {
      "title": "Consolidated Statements of Income",
      "headers": ["", "4Q25", "3Q25", "4Q24", "FY2025", "FY2024"],
      "rows": [
        {"label": "Net Revenue", "4Q25": "43736", "3Q25": "42654", "...": "..."}
      ]
    }
  ],
  "xbrl": {
    "Revenue": {"value": 182447000000, "period": "FY2025", "unit": "USD"},
    "EarningsPerShareDiluted": {"value": 20.02, "period": "FY2025", "unit": "USD/shares"}
  }
}
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| No CIK found for ticker | Exit with error, suggest checking ticker |
| No 8-K Item 2.02 for a quarter | Log warning, skip, continue |
| Overflow file fetch fails | Retry once, then skip with warning |
| Exhibit HTML has no tables | Save raw HTML anyway, warn |
| Already downloaded | Skip if `{QUARTER}_financials.json` exists (>100 bytes) |

## Rate Limiting

- 100ms sleep between HTTP requests (well under SEC's 10 req/sec limit)
- Proper `User-Agent` header on all requests (SEC requirement)

## Skill File

`.claude/commands/edgar-download.md` — Instructions for Claude to:
1. Parse arguments (TICKER, optional QUARTER)
2. Load config, determine which quarters need downloading
3. Run `python edgar_download.py TICKER [QUARTER]`
4. Report progress per quarter (filing found, exhibits downloaded, tables parsed)
5. Suggest next steps (`/earnings-extract`, `/earnings-generate`)

## Key Technical Notes

- JPMorgan has 64 overflow files (~2000 filings each, mostly 424B2 structured notes). The script only fetches overflow files whose date range covers the target quarter — typically 1-2 files per quarter.
- Simpler filers (CVNA, APP, etc.) have all 16 quarters in the `recent` array with zero or minimal overflow files.
- Item 2.02 = "Results of Operations and Financial Condition" — the canonical earnings press release filing.
- Item 7.01 = "Regulation FD Disclosure" — often contains the financial supplement (separate 8-K, same day).
- EX-99.1 is consistently the press release narrative; EX-99.2 is the financial supplement when present.
