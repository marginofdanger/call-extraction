# EDGAR Earnings Release Download

Download and parse earnings releases from SEC EDGAR for a company. Supplements BamSEC transcripts with official SEC filings (8-K press releases, financial supplements, and XBRL data).

**Argument:** `<args>` (format: `TICKER [QUARTER] [FLAGS]`, e.g., `JPM`, `JPM Q4_2025`, `PGR --monthly 48`)

## Instructions

1. **Parse arguments.** Split `<args>` into TICKER, optional QUARTER, and optional flags. If TICKER is missing, ask the user.

2. **Load the company config** from `companies/{{TICKER}}/config.yaml`. If the file doesn't exist, tell the user to run `/earnings-setup {{TICKER}}` first.

3. **Run the EDGAR download script:**
   ```bash
   cd /c/Users/AdrianOw/Projects/Call-extraction && python edgar_download.py {{TICKER}} {{QUARTER}} {{FLAGS}}
   ```
   If QUARTER is omitted, the script processes all quarters in the config.
   If `--monthly` is specified, it downloads ALL monthly result filings instead of quarterly.

4. **Report results** from the script output:
   - Number of quarters/months successfully processed
   - Number skipped (already downloaded)
   - Any failures with reasons
   - For each successful quarter: filing date, tables parsed, XBRL metrics found

5. **Suggest next steps:**
   - `"/earnings-extract {{TICKER}} {{QUARTER}}"` to extract guidance from a transcript
   - `"/earnings-generate {{TICKER}}"` to build HTML comparison pages
   - `"/edgar-download {{TICKER}} {{QUARTER}}"` to retry any failed quarters individually

## Flags

- `--discover-only`: Only find and record EDGAR filing accession numbers in config.yaml without downloading
- `--parse-only`: Re-parse already-downloaded HTML files without re-downloading from EDGAR
- `--monthly [N]`: Download ALL monthly result filings from the last N months (default 48). Used for companies like PGR that report monthly results via 8-K. Skips filings already downloaded as quarterly. Output files named `M_YYYY-MM-DD_*`.

## Output Files

For each quarter, the script creates in `companies/{{TICKER}}/edgar/`:
- `{{QUARTER}}_press_release.htm` -- Raw 8-K EX-99.1 HTML (earnings press release)
- `{{QUARTER}}_supplement.htm` -- Raw 8-K EX-99.2 HTML (financial supplement, if available)
- `{{QUARTER}}_financials.json` -- Parsed financial tables + XBRL data
- `{{QUARTER}}_earnings.md` -- Readable markdown summary

For monthly downloads (`--monthly`), files use `M_YYYY-MM-DD` as the ID instead of `{{QUARTER}}`.

## Company-Specific Notes

### Foreign Private Issuers (e.g., TSM)
- Foreign issuers file **6-K** instead of 8-K. Set `edgar_form_type: 6-K` in config.yaml.
- 6-K filings don't use Item numbers; matched purely by date proximity to `call_date`.
- Also searches **20-F** (annual report) in addition to 10-Q/10-K for XBRL data.

### Monthly Reporters (e.g., PGR)
- PGR reports monthly results via 8-K (Item 7.01 / Reg FD Disclosure).
- Use `--monthly 48` to download all monthly result filings.
- Some monthly filings use **EX-99** (without .1 suffix) as exhibit type -- handled automatically.
- Dividend announcements and non-results filings may also match Item 7.01 -- these download but produce 0 tables (expected).

### Image-Based Supplements (e.g., APO, APP)
- Some companies use Workiva/Wdesk slide format with JPEG images and hidden white text.
- The script automatically extracts hidden text from these supplements.
- Referenced images are downloaded alongside HTML exhibits.

## Important Notes

- **EDGAR is the ONLY data source.** Never try to supplement or replace EDGAR data with other sites (marketbeat, stocktitan, seekingalpha, etc.). If the script fails for a quarter, report the failure — do not attempt to find the data elsewhere.
- **No authentication needed.** EDGAR APIs are public, requiring only a User-Agent header.
- **Rate limited to ~10 req/sec.** The script handles this automatically.
- **Heavy filers (JPM, banks)** have thousands of non-earnings filings. The script efficiently searches overflow archives by date range.
- **XBRL data** comes from 10-Q/10-K/20-F filings and provides standardized, validated financial numbers.
- **Press release tables** vary by company format -- parsing is best-effort. Raw HTML is always saved.
- **Exhibit fallback chain:** EX-99.1 → EX-99 (no suffix) → primary document (8-K/6-K body).
