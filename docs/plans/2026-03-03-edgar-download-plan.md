# EDGAR Download Skill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build `edgar_download.py` and `/edgar-download` skill to discover, download, parse, and structure earnings releases from SEC EDGAR.

**Architecture:** Python script using SEC EDGAR REST APIs (submissions + company-facts + filing index). No auth needed, just User-Agent header. Reuses existing config.yaml quarter definitions. Outputs raw HTML, structured JSON, and markdown summaries.

**Tech Stack:** Python 3, requests, beautifulsoup4, pyyaml (requests and pyyaml already installed)

---

### Task 1: Install beautifulsoup4

**Files:**
- None (pip install only)

**Step 1: Install the dependency**

Run: `pip install beautifulsoup4`
Expected: Successfully installed beautifulsoup4

**Step 2: Verify import works**

Run: `python -c "from bs4 import BeautifulSoup; print('OK')"`
Expected: `OK`

**Step 3: Commit**

No commit needed — this is a local dependency install.

---

### Task 2: EDGAR HTTP client and CIK resolution

**Files:**
- Create: `edgar_download.py`

**Step 1: Write the EDGAR HTTP client and CIK lookup**

Create `edgar_download.py` with:
- `EdgarClient` class: wraps `requests.Session` with User-Agent header, 100ms rate limiting
- `resolve_cik(ticker)`: fetches `https://www.sec.gov/files/company_tickers.json`, finds CIK for ticker
- `load_config(ticker)` / `save_config(ticker, config)`: YAML config I/O (reuse pattern from `download_transcript.py`)
- CLI entry point that takes `TICKER [QUARTER]` args

```python
#!/usr/bin/env python3
"""Download earnings releases from SEC EDGAR.

Usage:
  python edgar_download.py TICKER [QUARTER] [--discover-only] [--parse-only]
  python edgar_download.py JPM
  python edgar_download.py JPM Q4_2025
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

import requests
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = SCRIPT_DIR
USER_AGENT = "CallExtraction admin@example.com"
SEC_BASE = "https://data.sec.gov"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"


class EdgarClient:
    """HTTP client for SEC EDGAR APIs with rate limiting."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._last_request = 0

    def get(self, url, **kwargs):
        elapsed = time.time() - self._last_request
        if elapsed < 0.1:
            time.sleep(0.1 - elapsed)
        self._last_request = time.time()
        r = self.session.get(url, timeout=30, **kwargs)
        r.raise_for_status()
        return r

    def get_json(self, url):
        return self.get(url).json()


def load_config(ticker):
    path = os.path.join(PROJECT_ROOT, "companies", ticker, "config.yaml")
    if not os.path.exists(path):
        print(f"Error: Config not found at {path}")
        print(f"Run /earnings-setup {ticker} first.")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(ticker, config):
    path = os.path.join(PROJECT_ROOT, "companies", ticker, "config.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def resolve_cik(client, ticker):
    """Look up CIK from ticker via SEC company_tickers.json."""
    data = client.get_json("https://www.sec.gov/files/company_tickers.json")
    ticker_upper = ticker.upper()
    for entry in data.values():
        if entry.get("ticker", "").upper() == ticker_upper:
            return str(entry["cik_str"]).zfill(10)
    return None
```

**Step 2: Test CIK resolution manually**

Run: `python -c "import edgar_download as e; c = e.EdgarClient(); print(e.resolve_cik(c, 'JPM'))"`
Expected: `0000019617`

Run: `python -c "import edgar_download as e; c = e.EdgarClient(); print(e.resolve_cik(c, 'CVNA'))"`
Expected: `0001690820`

**Step 3: Commit**

```bash
git add edgar_download.py
git commit -m "feat: add edgar_download.py with EDGAR HTTP client and CIK resolution"
```

---

### Task 3: Filing discovery — find earnings 8-Ks

**Files:**
- Modify: `edgar_download.py`

**Step 1: Add filing discovery functions**

Add these functions to `edgar_download.py`:

```python
def parse_call_date(date_str):
    """Parse config call_date like 'April 13, 2022' to datetime.date."""
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {date_str}")


def find_earnings_8ks(filings_data):
    """Extract all 8-K filings with Item 2.02 or 7.01 from a filings dict.

    Returns list of dicts: {filing_date, accession, items, form, report_date}
    """
    results = []
    forms = filings_data.get("form", [])
    dates = filings_data.get("filingDate", [])
    accessions = filings_data.get("accessionNumber", [])
    items = filings_data.get("items", [])
    report_dates = filings_data.get("reportDate", [])

    for i in range(len(forms)):
        if forms[i] == "8-K" and ("2.02" in items[i] or "7.01" in items[i]):
            results.append({
                "filing_date": dates[i],
                "accession": accessions[i],
                "items": items[i],
                "form": forms[i],
                "report_date": report_dates[i] if i < len(report_dates) else "",
            })
    return results


def find_10q_10k(filings_data):
    """Extract 10-Q and 10-K filings from a filings dict."""
    results = []
    forms = filings_data.get("form", [])
    dates = filings_data.get("filingDate", [])
    accessions = filings_data.get("accessionNumber", [])
    primary_docs = filings_data.get("primaryDocument", [])
    report_dates = filings_data.get("reportDate", [])

    for i in range(len(forms)):
        if forms[i] in ("10-Q", "10-K"):
            results.append({
                "filing_date": dates[i],
                "accession": accessions[i],
                "form": forms[i],
                "primary_doc": primary_docs[i] if i < len(primary_docs) else "",
                "report_date": report_dates[i] if i < len(report_dates) else "",
            })
    return results


def discover_filings(client, cik, config):
    """Discover earnings 8-K filings for all quarters in config.

    Returns dict mapping quarter_id -> {accession_2_02, accession_7_01, filing_date}
    """
    padded_cik = cik.zfill(10)
    submissions_url = f"{SEC_BASE}/submissions/CIK{padded_cik}.json"
    data = client.get_json(submissions_url)

    recent = data.get("filings", {}).get("recent", {})
    overflow_files = data.get("filings", {}).get("files", [])

    # Collect all earnings 8-Ks from recent filings
    all_8ks = find_earnings_8ks(recent)
    all_periodic = find_10q_10k(recent)

    # Determine date range covered by recent filings
    recent_dates = recent.get("filingDate", [])
    recent_min = recent_dates[-1] if recent_dates else "9999-99-99"
    recent_max = recent_dates[0] if recent_dates else "0000-00-00"

    # Check which quarters need overflow files
    quarters = config.get("quarters", [])
    needed_ranges = set()
    for q in quarters:
        try:
            call_date = parse_call_date(q["call_date"])
        except ValueError:
            continue
        call_str = call_date.isoformat()
        # If call_date is outside recent range, we need overflow
        if call_str < recent_min or call_str > recent_max:
            needed_ranges.add(call_str)

    # Fetch only needed overflow files
    if needed_ranges:
        for of in overflow_files:
            of_from = of.get("filingFrom", "")
            of_to = of.get("filingTo", "")
            # Check if any needed date falls within ±7 days of this overflow's range
            dominated = False
            for nd in needed_ranges:
                nd_date = datetime.fromisoformat(nd).date()
                of_from_date = datetime.fromisoformat(of_from).date() - timedelta(days=7)
                of_to_date = datetime.fromisoformat(of_to).date() + timedelta(days=7)
                if of_from_date <= nd_date <= of_to_date:
                    dominated = True
                    break
            if dominated:
                of_url = f"{SEC_BASE}/submissions/{of['name']}"
                try:
                    of_data = client.get_json(of_url)
                    all_8ks.extend(find_earnings_8ks(of_data))
                    all_periodic.extend(find_10q_10k(of_data))
                except Exception as e:
                    print(f"  Warning: Failed to fetch overflow {of['name']}: {e}")

    # Match 8-Ks to quarters
    results = {}
    for q in quarters:
        qid = q["id"]
        try:
            call_date = parse_call_date(q["call_date"])
        except ValueError:
            print(f"  Warning: Cannot parse call_date for {qid}: {q.get('call_date')}")
            continue

        # Find Item 2.02 within ±3 days, then ±7
        match_2_02 = None
        match_7_01 = None
        for window in (3, 7):
            if match_2_02:
                break
            for filing in all_8ks:
                try:
                    fd = datetime.fromisoformat(filing["filing_date"]).date()
                except ValueError:
                    continue
                delta = abs((fd - call_date).days)
                if delta <= window and "2.02" in filing["items"]:
                    match_2_02 = filing
                if delta <= window and "7.01" in filing["items"]:
                    match_7_01 = filing
            if match_2_02 and window == 7:
                print(f"  Note: {qid} matched 8-K at ±{abs((datetime.fromisoformat(match_2_02['filing_date']).date() - call_date).days)}d (widened window)")

        if match_2_02:
            results[qid] = {
                "accession_2_02": match_2_02["accession"],
                "filing_date": match_2_02["filing_date"],
                "accession_7_01": match_7_01["accession"] if match_7_01 and match_7_01["accession"] != match_2_02["accession"] else None,
            }
        else:
            print(f"  Warning: No earnings 8-K (Item 2.02) found for {qid} (call_date={q['call_date']})")

    return results
```

**Step 2: Test discovery manually against JPM**

Run: `python -c "
import edgar_download as e
c = e.EdgarClient()
cfg = e.load_config('JPM')
filings = e.discover_filings(c, '0000019617', cfg)
for qid, info in sorted(filings.items()):
    print(f'{qid}: {info[\"filing_date\"]} | {info[\"accession_2_02\"]}')
"`

Expected: 16 quarters matched, each with a filing_date close to the config's call_date. Q4_2025 should show accession `0001628280-26-001902` with filing_date `2026-01-13`.

**Step 3: Test against a simpler filer (CVNA)**

Run: `python -c "
import edgar_download as e
c = e.EdgarClient()
cfg = e.load_config('CVNA')
cik = e.resolve_cik(c, 'CVNA')
filings = e.discover_filings(c, cik, cfg)
print(f'Matched {len(filings)}/16 quarters')
"`

Expected: ~14-16 quarters matched (all within recent filings, no overflow needed).

**Step 4: Commit**

```bash
git add edgar_download.py
git commit -m "feat: add EDGAR filing discovery with overflow file support"
```

---

### Task 4: Download filing exhibits (EX-99.1, EX-99.2)

**Files:**
- Modify: `edgar_download.py`

**Step 1: Add exhibit download functions**

```python
def fetch_filing_exhibits(client, cik, accession):
    """Fetch the filing index and return exhibit info.

    Returns dict: {ex_99_1: filename, ex_99_2: filename, all_docs: [...]}
    """
    acc_dashed = accession.replace("-", "")
    # Use the JSON filing index (more reliable than HTML parsing)
    index_url = f"{SEC_ARCHIVES}/{int(cik)}/{acc_dashed}/{accession}-index.json"
    try:
        data = client.get_json(index_url)
    except requests.HTTPError:
        # Fallback to HTML index parsing
        index_url = f"{SEC_ARCHIVES}/{int(cik)}/{acc_dashed}/{accession}-index.htm"
        return _parse_html_index(client, index_url, cik, acc_dashed)

    result = {"ex_99_1": None, "ex_99_2": None, "primary": None, "all_docs": []}
    for item in data.get("directory", {}).get("item", []):
        name = item.get("name", "")
        doc_type = item.get("type", "")
        result["all_docs"].append({"name": name, "type": doc_type})
        if "EX-99.1" in doc_type.upper() or "EX-99.1" in name.upper():
            result["ex_99_1"] = name
        elif "EX-99.2" in doc_type.upper() or "EX-99.2" in name.upper():
            result["ex_99_2"] = name
        elif doc_type in ("8-K", "10-Q", "10-K"):
            result["primary"] = name

    # If JSON didn't have type info, try matching by exhibit naming patterns
    if not result["ex_99_1"]:
        for doc in result["all_docs"]:
            name_lower = doc["name"].lower()
            if "ex99" in name_lower.replace("-", "").replace("_", "") and name_lower.endswith((".htm", ".html")):
                if "1" in name_lower.split("ex99")[-1][:3]:
                    result["ex_99_1"] = doc["name"]
                elif "2" in name_lower.split("ex99")[-1][:3]:
                    result["ex_99_2"] = doc["name"]

    return result


def download_exhibit(client, cik, accession, filename, output_path):
    """Download a single exhibit file."""
    acc_dashed = accession.replace("-", "")
    url = f"{SEC_ARCHIVES}/{int(cik)}/{acc_dashed}/{filename}"
    r = client.get(url)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(r.content)
    return len(r.content)


def download_quarter_exhibits(client, cik, ticker, quarter_id, filing_info):
    """Download all exhibits for a quarter. Returns dict of downloaded files."""
    edgar_dir = os.path.join(PROJECT_ROOT, "companies", ticker, "edgar")
    os.makedirs(edgar_dir, exist_ok=True)

    downloaded = {}
    accession = filing_info["accession_2_02"]

    # Get exhibit filenames from filing index
    exhibits = fetch_filing_exhibits(client, cik, accession)

    # Download EX-99.1 (press release)
    if exhibits["ex_99_1"]:
        path = os.path.join(edgar_dir, f"{quarter_id}_press_release.htm")
        size = download_exhibit(client, cik, accession, exhibits["ex_99_1"], path)
        downloaded["press_release"] = path
        print(f"    EX-99.1: {size:,} bytes -> {os.path.basename(path)}")
    else:
        print(f"    Warning: No EX-99.1 found for {accession}")

    # Download EX-99.2 (supplement)
    if exhibits["ex_99_2"]:
        path = os.path.join(edgar_dir, f"{quarter_id}_supplement.htm")
        size = download_exhibit(client, cik, accession, exhibits["ex_99_2"], path)
        downloaded["supplement"] = path
        print(f"    EX-99.2: {size:,} bytes -> {os.path.basename(path)}")

    # Download supplement from companion 7.01 filing if separate
    if filing_info.get("accession_7_01"):
        supp_acc = filing_info["accession_7_01"]
        supp_exhibits = fetch_filing_exhibits(client, cik, supp_acc)
        for key in ("ex_99_1", "ex_99_2"):
            if supp_exhibits[key] and "supplement" not in downloaded:
                path = os.path.join(edgar_dir, f"{quarter_id}_supplement.htm")
                size = download_exhibit(client, cik, supp_acc, supp_exhibits[key], path)
                downloaded["supplement"] = path
                print(f"    7.01 supplement: {size:,} bytes -> {os.path.basename(path)}")
                break

    return downloaded
```

**Step 2: Test exhibit download for one JPM quarter**

Run: `python -c "
import edgar_download as e
c = e.EdgarClient()
info = {'accession_2_02': '0001628280-26-001902', 'accession_7_01': '0001628280-26-001915', 'filing_date': '2026-01-13'}
files = e.download_quarter_exhibits(c, '0000019617', 'JPM', 'Q4_2025', info)
print(files)
"`

Expected: Downloads `Q4_2025_press_release.htm` and `Q4_2025_supplement.htm` to `companies/JPM/edgar/`. Prints file sizes.

**Step 3: Verify downloaded HTML has financial tables**

Run: `python -c "
from bs4 import BeautifulSoup
with open('companies/JPM/edgar/Q4_2025_press_release.htm') as f:
    soup = BeautifulSoup(f, 'html.parser')
tables = soup.find_all('table')
print(f'Found {len(tables)} tables')
for i, t in enumerate(tables[:3]):
    text = t.get_text()[:200]
    print(f'Table {i}: {text[:100]}...')
"`

Expected: Multiple tables found, content includes financial terms.

**Step 4: Commit**

```bash
git add edgar_download.py
git commit -m "feat: add EDGAR exhibit discovery and download"
```

---

### Task 5: HTML table parsing

**Files:**
- Modify: `edgar_download.py`

**Step 1: Add HTML table parser**

```python
from bs4 import BeautifulSoup


def clean_cell_text(text):
    """Clean a table cell: handle parens for negatives, strip whitespace and symbols."""
    text = text.strip()
    text = text.replace("\xa0", " ").replace("\u2014", "—").replace("\u2013", "–")
    # Remove footnote markers like (1), (a), *
    text = re.sub(r"\s*\(\d+\)\s*$", "", text)
    text = re.sub(r"\s*\*+\s*$", "", text)
    # Handle parentheses as negatives: (123) -> -123
    m = re.match(r"^\$?\s*\(([0-9,.]+)\)\s*$", text)
    if m:
        text = "-" + m.group(1)
    # Remove leading $ but keep the number
    text = re.sub(r"^\$\s*", "", text)
    return text.strip()


def is_financial_table(table_soup):
    """Heuristic: does this table look like a financial statement?"""
    text = table_soup.get_text(" ", strip=True)
    indicators = ["$", "revenue", "income", "loss", "earnings", "assets", "margin",
                   "diluted", "eps", "operating", "net", "total", "per share"]
    count = sum(1 for ind in indicators if ind.lower() in text.lower())
    return count >= 2


def parse_html_tables(html_content):
    """Parse financial tables from press release HTML.

    Returns list of table dicts: {title, headers, rows}
    """
    soup = BeautifulSoup(html_content, "html.parser")
    tables = []

    for table in soup.find_all("table"):
        if not is_financial_table(table):
            continue

        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # Try to find header row (first row with <th> elements, or first row)
        parsed_rows = []
        headers = []

        for row in rows:
            cells = row.find_all(["th", "td"])
            cell_texts = [clean_cell_text(c.get_text(" ", strip=True)) for c in cells]

            # Skip completely empty rows
            if not any(cell_texts):
                continue

            if not headers and (row.find("th") or not parsed_rows):
                headers = cell_texts
            else:
                parsed_rows.append(cell_texts)

        if not headers or not parsed_rows:
            continue

        # Convert rows to dicts using headers
        row_dicts = []
        for row_cells in parsed_rows:
            row_dict = {}
            for j, val in enumerate(row_cells):
                key = headers[j] if j < len(headers) else f"col_{j}"
                if not key:
                    key = "label" if j == 0 else f"col_{j}"
                row_dict[key] = val
            if any(v for v in row_dict.values()):
                row_dicts.append(row_dict)

        # Try to find table title from preceding element
        title = ""
        prev = table.find_previous(["p", "b", "strong", "h1", "h2", "h3", "h4"])
        if prev:
            prev_text = prev.get_text(strip=True)
            if len(prev_text) < 200 and any(kw in prev_text.lower() for kw in
                    ["statement", "results", "summary", "supplement", "data", "financial", "consolidated"]):
                title = prev_text

        tables.append({
            "title": title,
            "headers": headers,
            "rows": row_dicts,
        })

    return tables
```

**Step 2: Test parsing on a real JPM press release**

Run: `python -c "
import edgar_download as e
with open('companies/JPM/edgar/Q4_2025_press_release.htm', 'r', encoding='utf-8') as f:
    html = f.read()
tables = e.parse_html_tables(html)
print(f'Parsed {len(tables)} financial tables')
for t in tables[:3]:
    print(f'  \"{t[\"title\"]}\" - {len(t[\"rows\"])} rows, headers: {t[\"headers\"][:4]}')
"`

Expected: Multiple financial tables parsed with recognizable headers and row data.

**Step 3: Commit**

```bash
git add edgar_download.py
git commit -m "feat: add HTML financial table parser with BeautifulSoup"
```

---

### Task 6: XBRL enrichment

**Files:**
- Modify: `edgar_download.py`

**Step 1: Add XBRL fact extraction**

```python
# Key XBRL concepts to extract
XBRL_CONCEPTS = {
    "Revenues": "Revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "Revenue",
    "NetIncomeLoss": "Net Income",
    "EarningsPerShareDiluted": "Diluted EPS",
    "EarningsPerShareBasic": "Basic EPS",
    "Assets": "Total Assets",
    "StockholdersEquity": "Stockholders Equity",
    "OperatingIncomeLoss": "Operating Income",
    "CashAndCashEquivalentsAtCarryingValue": "Cash & Equivalents",
    "NetCashProvidedByUsedInOperatingActivities": "Cash from Operations",
}


def fetch_xbrl_facts(client, cik):
    """Fetch all XBRL company facts. Returns the full JSON (cache externally)."""
    padded = cik.zfill(10)
    url = f"{SEC_BASE}/api/xbrl/companyfacts/CIK{padded}.json"
    return client.get_json(url)


def extract_xbrl_for_quarter(xbrl_data, quarter_end_date):
    """Extract key XBRL facts for a specific quarter end date.

    quarter_end_date: str like "2025-12-31"
    Returns dict: {label: {value, period, unit, form}}
    """
    results = {}
    us_gaap = xbrl_data.get("facts", {}).get("us-gaap", {})

    for concept, label in XBRL_CONCEPTS.items():
        if concept not in us_gaap:
            continue
        facts = us_gaap[concept]
        for unit_key, unit_facts in facts.get("units", {}).items():
            for fact in unit_facts:
                if fact.get("end") == quarter_end_date:
                    # Prefer 10-K/10-Q over 8-K, and quarterly over annual
                    existing = results.get(label)
                    if not existing or fact.get("form") in ("10-K", "10-Q"):
                        results[label] = {
                            "value": fact["val"],
                            "period": f"{fact.get('fp', '?')}",
                            "unit": unit_key,
                            "form": fact.get("form", ""),
                            "end": fact.get("end", ""),
                        }

    return results
```

**Step 2: Test XBRL extraction for JPM Q4 2025**

Run: `python -c "
import edgar_download as e
c = e.EdgarClient()
xbrl = e.fetch_xbrl_facts(c, '0000019617')
facts = e.extract_xbrl_for_quarter(xbrl, '2025-12-31')
for label, data in facts.items():
    print(f'  {label}: {data[\"value\"]} ({data[\"unit\"]}, {data[\"form\"]})')
"`

Expected: Key financial metrics for JPM FY2025 (Revenue ~$182B, EPS ~$20).

**Step 3: Commit**

```bash
git add edgar_download.py
git commit -m "feat: add XBRL company-facts enrichment"
```

---

### Task 7: JSON and Markdown output generation

**Files:**
- Modify: `edgar_download.py`

**Step 1: Add output generation functions**

```python
def build_financials_json(ticker, quarter_id, filing_info, tables, xbrl_facts):
    """Build the structured JSON output."""
    return {
        "ticker": ticker,
        "quarter": quarter_id,
        "filing_date": filing_info["filing_date"],
        "accession": filing_info["accession_2_02"],
        "tables": tables,
        "xbrl": xbrl_facts,
    }


def generate_earnings_markdown(ticker, quarter_id, company_name, filing_info, tables, xbrl_facts):
    """Generate a readable markdown summary from parsed data."""
    lines = []
    lines.append(f"# {company_name} {quarter_id} Earnings Release")
    lines.append(f"**Filing Date:** {filing_info['filing_date']} | **Accession:** {filing_info['accession_2_02']}")
    acc = filing_info['accession_2_02']
    acc_dashed = acc.replace('-', '')
    lines.append(f"**Source:** [SEC EDGAR](https://www.sec.gov/Archives/edgar/data/{ticker}/{acc_dashed}/{acc}-index.htm)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # XBRL key metrics
    if xbrl_facts:
        lines.append("## Key Metrics (XBRL)")
        lines.append("")
        for label, data in xbrl_facts.items():
            val = data["value"]
            unit = data["unit"]
            if unit == "USD" and abs(val) >= 1e9:
                formatted = f"${val / 1e9:.1f}B"
            elif unit == "USD" and abs(val) >= 1e6:
                formatted = f"${val / 1e6:.0f}M"
            elif unit == "USD/shares":
                formatted = f"${val:.2f}"
            else:
                formatted = f"{val:,}"
            lines.append(f"- **{label}:** {formatted} ({data['period']}, {data['form']})")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Table summaries
    if tables:
        lines.append("## Financial Tables")
        lines.append("")
        for i, table in enumerate(tables):
            title = table.get("title") or f"Table {i + 1}"
            lines.append(f"### {title}")
            lines.append("")
            if table["headers"]:
                lines.append("| " + " | ".join(table["headers"]) + " |")
                lines.append("| " + " | ".join(["---"] * len(table["headers"])) + " |")
                for row in table["rows"][:20]:  # Limit rows in markdown
                    cells = [str(row.get(h, "")) for h in table["headers"]]
                    lines.append("| " + " | ".join(cells) + " |")
            lines.append("")

    return "\n".join(lines)


def save_quarter_outputs(ticker, quarter_id, company_name, filing_info, tables, xbrl_facts):
    """Save JSON and markdown outputs for a quarter."""
    edgar_dir = os.path.join(PROJECT_ROOT, "companies", ticker, "edgar")
    os.makedirs(edgar_dir, exist_ok=True)

    # JSON
    financials = build_financials_json(ticker, quarter_id, filing_info, tables, xbrl_facts)
    json_path = os.path.join(edgar_dir, f"{quarter_id}_financials.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(financials, f, indent=2, ensure_ascii=False)
    print(f"    JSON: {os.path.getsize(json_path):,} bytes -> {os.path.basename(json_path)}")

    # Markdown
    md = generate_earnings_markdown(ticker, quarter_id, company_name, filing_info, tables, xbrl_facts)
    md_path = os.path.join(edgar_dir, f"{quarter_id}_earnings.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"    MD:   {len(md):,} chars -> {os.path.basename(md_path)}")
```

**Step 2: Test end-to-end on the already-downloaded JPM Q4_2025 press release**

Run: `python -c "
import json
import edgar_download as e
c = e.EdgarClient()
# Parse already-downloaded HTML
with open('companies/JPM/edgar/Q4_2025_press_release.htm', 'r', encoding='utf-8') as f:
    tables = e.parse_html_tables(f.read())
# Get XBRL
xbrl_data = e.fetch_xbrl_facts(c, '0000019617')
xbrl_facts = e.extract_xbrl_for_quarter(xbrl_data, '2025-12-31')
# Save outputs
info = {'accession_2_02': '0001628280-26-001902', 'filing_date': '2026-01-13'}
e.save_quarter_outputs('JPM', 'Q4_2025', 'JPMorgan Chase & Co.', info, tables, xbrl_facts)
"`

Expected: Creates `Q4_2025_financials.json` and `Q4_2025_earnings.md` in `companies/JPM/edgar/`.

**Step 3: Commit**

```bash
git add edgar_download.py
git commit -m "feat: add JSON and markdown output generation"
```

---

### Task 8: Main CLI and full pipeline integration

**Files:**
- Modify: `edgar_download.py`

**Step 1: Add the main pipeline function and CLI**

```python
def quarter_end_date(quarter_id, fiscal_year_type, fy_end_month=12):
    """Estimate the quarter-end date from quarter ID and fiscal year config.

    For calendar year: Q1=Mar 31, Q2=Jun 30, Q3=Sep 30, Q4=Dec 31
    For offset fiscal year: shifted by fy_end_month
    """
    m = re.match(r"Q(\d)_(?:FY)?(\d{4})", quarter_id)
    if not m:
        return None
    q_num = int(m.group(1))
    year = int(m.group(2))

    if fiscal_year_type == "calendar":
        end_months = {1: (year, 3, 31), 2: (year, 6, 30), 3: (year, 9, 30), 4: (year, 12, 31)}
    else:
        # Offset fiscal year: Q1 starts after FY end month
        # e.g., FY end Sep (9): Q1=Oct-Dec, Q2=Jan-Mar, Q3=Apr-Jun, Q4=Jul-Sep
        quarter_offsets = {1: 3, 2: 6, 3: 9, 4: 0}  # months after FY start
        fy_start_month = (fy_end_month % 12) + 1
        end_month = (fy_start_month + quarter_offsets[q_num] + 2) % 12
        if end_month == 0:
            end_month = 12
        end_year = year if q_num < 4 or fy_end_month == 12 else year
        # Simplified: just use the month-end
        import calendar
        last_day = calendar.monthrange(end_year, end_month)[1]
        return f"{end_year:04d}-{end_month:02d}-{last_day:02d}"

    y, mo, d = end_months[q_num]
    return f"{y:04d}-{mo:02d}-{d:02d}"


def process_ticker(ticker, quarter_filter=None, discover_only=False, parse_only=False):
    """Main pipeline: discover, download, parse, and output for a ticker."""
    config = load_config(ticker)
    company = config.get("company", {})
    company_name = company.get("name", ticker)
    fy_type = company.get("fiscal_year", "calendar")
    fy_end = company.get("fiscal_year_end_month", 12)

    client = EdgarClient()
    edgar_dir = os.path.join(PROJECT_ROOT, "companies", ticker, "edgar")

    # Step 1: CIK resolution
    cik = company.get("edgar_cik", "")
    if not cik:
        print(f"Resolving CIK for {ticker}...")
        cik = resolve_cik(client, ticker)
        if not cik:
            print(f"Error: Could not find CIK for ticker {ticker}")
            sys.exit(1)
        config["company"]["edgar_cik"] = cik
        save_config(ticker, config)
        print(f"  CIK: {cik} (saved to config)")
    else:
        print(f"CIK: {cik}")

    # Step 2: Determine which quarters to process
    quarters = config.get("quarters", [])
    if quarter_filter:
        quarters = [q for q in quarters if q["id"] == quarter_filter]
        if not quarters:
            print(f"Error: Quarter {quarter_filter} not found in config")
            sys.exit(1)

    # Skip already-downloaded quarters
    to_process = []
    skipped = []
    for q in quarters:
        json_path = os.path.join(edgar_dir, f"{q['id']}_financials.json")
        if not parse_only and os.path.exists(json_path) and os.path.getsize(json_path) > 100:
            skipped.append(q["id"])
        else:
            to_process.append(q)

    if skipped:
        print(f"Skipping {len(skipped)} already-downloaded: {', '.join(skipped)}")
    print(f"Processing {len(to_process)} quarters...")

    # Step 3: Discover filings
    if not parse_only:
        print(f"\nDiscovering EDGAR filings for {company_name}...")
        filings = discover_filings(client, cik, config)
        print(f"  Matched {len(filings)}/{len(to_process)} quarters")

        # Update config with discovered accessions
        config_changed = False
        for q in config.get("quarters", []):
            if q["id"] in filings:
                f = filings[q["id"]]
                if q.get("edgar_8k_accession") != f["accession_2_02"]:
                    q["edgar_8k_accession"] = f["accession_2_02"]
                    config_changed = True
                if f.get("accession_7_01") and q.get("edgar_8k_supplement") != f["accession_7_01"]:
                    q["edgar_8k_supplement"] = f["accession_7_01"]
                    config_changed = True
        if config_changed:
            save_config(ticker, config)
            print("  Config updated with EDGAR accession numbers")
    else:
        # Build filings dict from config
        filings = {}
        for q in to_process:
            acc = q.get("edgar_8k_accession", "")
            if acc:
                filings[q["id"]] = {
                    "accession_2_02": acc,
                    "accession_7_01": q.get("edgar_8k_supplement"),
                    "filing_date": q.get("call_date", ""),
                }

    if discover_only:
        print("\n--discover-only: stopping after discovery.")
        return

    # Step 4: Fetch XBRL facts (one call, cached for all quarters)
    print(f"\nFetching XBRL company facts...")
    try:
        xbrl_data = fetch_xbrl_facts(client, cik)
        print(f"  Loaded {len(xbrl_data.get('facts', {}).get('us-gaap', {}))} us-gaap concepts")
    except Exception as e:
        print(f"  Warning: XBRL fetch failed: {e}")
        xbrl_data = {}

    # Step 5: Process each quarter
    success = []
    failed = []
    for q in to_process:
        qid = q["id"]
        print(f"\n  [{qid}]")

        if qid not in filings:
            print(f"    Skipped: no matching 8-K found")
            failed.append((qid, "no matching 8-K"))
            continue

        filing_info = filings[qid]

        try:
            # Download exhibits
            if not parse_only:
                downloaded = download_quarter_exhibits(client, cik, ticker, qid, filing_info)

            # Parse press release
            pr_path = os.path.join(edgar_dir, f"{qid}_press_release.htm")
            if os.path.exists(pr_path):
                with open(pr_path, "r", encoding="utf-8", errors="replace") as f:
                    tables = parse_html_tables(f.read())
                print(f"    Parsed {len(tables)} financial tables")
            else:
                tables = []
                print(f"    Warning: No press release HTML to parse")

            # XBRL for this quarter
            end_date = quarter_end_date(qid, fy_type, fy_end)
            xbrl_facts = extract_xbrl_for_quarter(xbrl_data, end_date) if end_date and xbrl_data else {}
            if xbrl_facts:
                print(f"    XBRL: {len(xbrl_facts)} metrics for period ending {end_date}")

            # Save outputs
            save_quarter_outputs(ticker, qid, company_name, filing_info, tables, xbrl_facts)
            success.append(qid)

        except Exception as e:
            print(f"    ERROR: {e}")
            failed.append((qid, str(e)))

    # Final report
    print(f"\n{'='*60}")
    print(f"EDGAR Download Complete: {ticker}")
    print(f"  Success: {len(success)} quarters")
    if skipped:
        print(f"  Skipped: {len(skipped)} (already downloaded)")
    if failed:
        print(f"  Failed:  {len(failed)}")
        for qid, reason in failed:
            print(f"    {qid}: {reason}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: python edgar_download.py TICKER [QUARTER] [--discover-only] [--parse-only]")
        sys.exit(1)

    ticker = args[0].upper()
    quarter = None
    discover_only = "--discover-only" in args
    parse_only = "--parse-only" in args

    for a in args[1:]:
        if not a.startswith("--"):
            quarter = a

    process_ticker(ticker, quarter, discover_only, parse_only)
```

**Step 2: Test full pipeline on JPM (single quarter)**

Run: `python edgar_download.py JPM Q4_2025`
Expected: Discovers filing, downloads exhibits, parses tables, saves JSON + markdown. Prints progress.

**Step 3: Test full pipeline on CVNA (all quarters)**

Run: `python edgar_download.py CVNA`
Expected: Processes all 16 quarters. Most should succeed. Reports summary at end.

**Step 4: Test discover-only mode**

Run: `python edgar_download.py APP --discover-only`
Expected: Resolves CIK, finds all 8-K filings, updates config, stops before downloading.

**Step 5: Commit**

```bash
git add edgar_download.py
git commit -m "feat: add main CLI pipeline with full download/parse/output flow"
```

---

### Task 9: Write the skill file

**Files:**
- Create: `.claude/commands/edgar-download.md`

**Step 1: Write the skill definition**

```markdown
# EDGAR Earnings Release Download

Download and parse earnings releases from SEC EDGAR for a company. Supplements BamSEC transcripts with official SEC filings (8-K press releases, financial supplements, and XBRL data).

**Argument:** `<args>` (format: `TICKER [QUARTER]`, e.g., `JPM`, `JPM Q4_2025`)

## Instructions

1. **Parse arguments.** Split `<args>` into TICKER and optional QUARTER. If TICKER is missing, ask the user.

2. **Load the company config** from `companies/{{TICKER}}/config.yaml`. If the file doesn't exist, tell the user to run `/earnings-setup {{TICKER}}` first.

3. **Run the EDGAR download script:**
   ```bash
   cd /c/Users/AdrianOw/Projects/Call-extraction && python edgar_download.py {{TICKER}} {{QUARTER}}
   ```
   If QUARTER is omitted, the script processes all quarters in the config.

4. **Report results** from the script output:
   - Number of quarters successfully processed
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

## Output Files

For each quarter, the script creates in `companies/{{TICKER}}/edgar/`:
- `{{QUARTER}}_press_release.htm` — Raw 8-K EX-99.1 HTML (earnings press release)
- `{{QUARTER}}_supplement.htm` — Raw 8-K EX-99.2 HTML (financial supplement, if available)
- `{{QUARTER}}_financials.json` — Parsed financial tables + XBRL data
- `{{QUARTER}}_earnings.md` — Readable markdown summary

## Important Notes

- **No authentication needed.** EDGAR APIs are public, requiring only a User-Agent header.
- **Rate limited to ~10 req/sec.** The script handles this automatically.
- **Heavy filers (JPM, banks)** have thousands of non-earnings filings. The script efficiently searches overflow archives by date range.
- **XBRL data** comes from 10-Q/10-K filings and provides standardized, validated financial numbers.
- **Press release tables** vary by company format — parsing is best-effort. Raw HTML is always saved.
```

**Step 2: Commit**

```bash
git add .claude/commands/edgar-download.md
git commit -m "feat: add /edgar-download skill definition"
```

---

### Task 10: End-to-end validation

**Files:**
- None (testing only)

**Step 1: Run full pipeline on 3 different company types**

Run sequentially:

```bash
# Bank (heavy filer, many overflow files)
python edgar_download.py JPM

# Tech (moderate filer)
python edgar_download.py MSFT

# Small filer (few filings)
python edgar_download.py CVNA
```

**Step 2: Verify output quality**

Check that for each company:
- `companies/{TICKER}/edgar/` directory contains files for each quarter
- `_financials.json` files have non-empty `tables` and `xbrl` sections
- `_earnings.md` files are readable with financial data
- `config.yaml` has `edgar_cik` and `edgar_8k_accession` fields populated

Run: `find companies/JPM/edgar -name '*.json' | head -5 && python -c "import json; d=json.load(open('companies/JPM/edgar/Q4_2025_financials.json')); print(f'Tables: {len(d[\"tables\"])}, XBRL: {len(d[\"xbrl\"])}')" `

**Step 3: Test the skill invocation**

Tell user to test: `/edgar-download JPM Q4_2025`

**Step 4: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: address issues found during end-to-end validation"
```
