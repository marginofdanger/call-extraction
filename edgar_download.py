#!/usr/bin/env python3
"""Download earnings releases from SEC EDGAR.

Usage:
  python edgar_download.py TICKER [QUARTER] [--discover-only] [--parse-only]
  python edgar_download.py TICKER --monthly [N]
  python edgar_download.py JPM
  python edgar_download.py JPM Q4_2025
  python edgar_download.py PGR --monthly 48
"""

import calendar
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

import requests
import yaml
from bs4 import BeautifulSoup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = SCRIPT_DIR
USER_AGENT = "CallExtraction admin@example.com"
SEC_BASE = "https://data.sec.gov"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"


# ---------------------------------------------------------------------------
# EdgarClient — HTTP client with User-Agent and 100 ms rate limiting
# ---------------------------------------------------------------------------

class EdgarClient:
    """HTTP client for SEC EDGAR with required User-Agent and rate limiting."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "gzip, deflate",
        })
        self._last_request_time = 0.0

    def _rate_limit(self):
        """Enforce 100 ms minimum between requests (SEC limit: 10 req/sec)."""
        elapsed = time.time() - self._last_request_time
        if elapsed < 0.1:
            time.sleep(0.1 - elapsed)
        self._last_request_time = time.time()

    def get(self, url):
        """GET request with rate limiting. Returns response object."""
        self._rate_limit()
        resp = self.session.get(url, timeout=30)
        if resp.status_code != 200:
            print(f"  WARNING: HTTP {resp.status_code} for {url}")
        return resp

    def get_json(self, url):
        """GET request returning parsed JSON, or None on failure."""
        resp = self.get(url)
        if resp.status_code != 200:
            return None
        try:
            return resp.json()
        except ValueError:
            print(f"  WARNING: Invalid JSON from {url}")
            return None


# ---------------------------------------------------------------------------
# Config I/O
# ---------------------------------------------------------------------------

def load_config(ticker):
    """Load companies/{ticker}/config.yaml. Exits if not found."""
    config_path = os.path.join(PROJECT_ROOT, "companies", ticker, "config.yaml")
    if not os.path.exists(config_path):
        print(f"Error: Config not found at {config_path}")
        print(f"Run /earnings-setup {ticker} first.")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(ticker, config):
    """Write config back to companies/{ticker}/config.yaml."""
    config_path = os.path.join(PROJECT_ROOT, "companies", ticker, "config.yaml")
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# CIK Resolution
# ---------------------------------------------------------------------------

def resolve_cik(client, ticker):
    """Look up CIK for a ticker from SEC company_tickers.json.

    Returns CIK as a zero-padded 10-digit string, or None.
    """
    url = "https://www.sec.gov/files/company_tickers.json"
    data = client.get_json(url)
    if data is None:
        print("ERROR: Could not fetch company tickers from SEC")
        return None

    ticker_upper = ticker.upper()
    for _key, entry in data.items():
        if entry.get("ticker", "").upper() == ticker_upper:
            cik = entry["cik_str"]
            return str(cik).zfill(10)

    print(f"ERROR: Ticker '{ticker}' not found in SEC company tickers")
    return None


# ---------------------------------------------------------------------------
# Filing Discovery
# ---------------------------------------------------------------------------

def parse_call_date(date_str):
    """Parse 'April 13, 2022' or 'April 2022' to datetime.date. Returns None on failure."""
    if not date_str:
        return None
    s = date_str.strip()
    # Try full date: "April 13, 2022" or "Apr 13, 2022"
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Try month-only: "April 2022" or "Apr 2022" (use 15th as default day)
    for fmt in ("%B %Y", "%b %Y"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(day=15).date()
        except ValueError:
            continue
    print(f"  WARNING: Could not parse date '{date_str}'")
    return None


def find_earnings_8ks(filings_data, form_type="8-K"):
    """Filter filings for earnings-related forms.

    For 8-K: requires Item 2.02 or Item 7.01.
    For 6-K: all 6-K filings are returned (no item filtering; matched by date later).

    Args:
        filings_data: dict with parallel arrays: form, filingDate, primaryDocument,
                      accessionNumber, items (optional)
        form_type: "8-K" (default) or "6-K"

    Returns:
        list of dicts with: form, filingDate, accessionNumber, primaryDocument, items
    """
    results = []
    forms = filings_data.get("form", [])
    dates = filings_data.get("filingDate", [])
    accessions = filings_data.get("accessionNumber", [])
    docs = filings_data.get("primaryDocument", [])
    items_list = filings_data.get("items", [])

    for i in range(len(forms)):
        form = forms[i] if i < len(forms) else ""
        if form != form_type:
            continue

        items_str = items_list[i] if i < len(items_list) else ""

        if form_type == "6-K":
            # 6-K filings don't use item numbers; include all, filter by date later
            results.append({
                "form": form,
                "filingDate": dates[i] if i < len(dates) else "",
                "accessionNumber": accessions[i] if i < len(accessions) else "",
                "primaryDocument": docs[i] if i < len(docs) else "",
                "items": items_str,
            })
        else:
            # 8-K: require Item 2.02 (Results of Operations) or Item 7.01 (Reg FD Disclosure)
            if "2.02" in str(items_str) or "7.01" in str(items_str):
                results.append({
                    "form": form,
                    "filingDate": dates[i] if i < len(dates) else "",
                    "accessionNumber": accessions[i] if i < len(accessions) else "",
                    "primaryDocument": docs[i] if i < len(docs) else "",
                    "items": items_str,
                })

    return results


def find_10q_10k(filings_data):
    """Filter filings for 10-Q, 10-K, and 20-F forms.

    Includes 20-F for foreign private issuers (e.g., TSM).

    Returns list of dicts with form, filingDate, accessionNumber, primaryDocument.
    """
    results = []
    forms = filings_data.get("form", [])
    dates = filings_data.get("filingDate", [])
    accessions = filings_data.get("accessionNumber", [])
    docs = filings_data.get("primaryDocument", [])

    for i in range(len(forms)):
        form = forms[i] if i < len(forms) else ""
        if form in ("10-Q", "10-K", "20-F"):
            results.append({
                "form": form,
                "filingDate": dates[i] if i < len(dates) else "",
                "accessionNumber": accessions[i] if i < len(accessions) else "",
                "primaryDocument": docs[i] if i < len(docs) else "",
            })

    return results


def _filing_date_range(filings_data):
    """Return (earliest_date, latest_date) from filings_data, or (None, None)."""
    dates = filings_data.get("filingDate", [])
    if not dates:
        return None, None
    parsed = []
    for d in dates:
        try:
            parsed.append(datetime.strptime(d, "%Y-%m-%d").date())
        except (ValueError, TypeError):
            continue
    if not parsed:
        return None, None
    return min(parsed), max(parsed)


def discover_filings(client, cik, config):
    """Discover earnings filings (8-K or 6-K) for all quarters in config.

    Fetches the main submissions JSON, then selectively fetches overflow files
    whose date ranges cover the target call dates.

    For 8-K: filters by Item 2.02/7.01, matches by call_date proximity.
    For 6-K: matches all 6-Ks by call_date proximity (no item filtering).

    Returns dict: { quarter_id: { '8k': {...}, '10q_10k': {...} or None } }
    """
    form_type = config.get("company", {}).get("edgar_form_type", "8-K")

    # Build set of target call dates from config
    quarters = config.get("quarters", [])
    target_dates = {}  # quarter_id -> date
    for q in quarters:
        cd = parse_call_date(q.get("call_date", ""))
        if cd:
            target_dates[q["id"]] = cd

    if not target_dates:
        print("  WARNING: No valid call dates found in config")
        return {}

    earliest_target = min(target_dates.values()) - timedelta(days=10)
    latest_target = max(target_dates.values()) + timedelta(days=10)

    # Fetch main submissions
    url = f"{SEC_BASE}/submissions/CIK{cik}.json"
    data = client.get_json(url)
    if data is None:
        print(f"ERROR: Could not fetch submissions for CIK {cik}")
        return {}

    # Collect all filings from recent filings
    all_earnings = []
    all_10q10k = []

    recent = data.get("filings", {}).get("recent", {})
    if recent:
        all_earnings.extend(find_earnings_8ks(recent, form_type=form_type))
        all_10q10k.extend(find_10q_10k(recent))

    # Handle overflow files for heavy filers
    overflow_files = data.get("filings", {}).get("files", [])
    if overflow_files:
        print(f"  Found {len(overflow_files)} overflow filing file(s)")
        for of in overflow_files:
            of_name = of.get("name", "")
            should_fetch = False

            filing_from = of.get("filingFrom", "")
            filing_to = of.get("filingTo", "")

            if filing_from and filing_to:
                try:
                    of_start = datetime.strptime(filing_from, "%Y-%m-%d").date()
                    of_end = datetime.strptime(filing_to, "%Y-%m-%d").date()
                    if of_start <= latest_target and of_end >= earliest_target:
                        should_fetch = True
                except (ValueError, TypeError):
                    should_fetch = True
            else:
                should_fetch = True

            if should_fetch and of_name:
                of_url = f"{SEC_BASE}/submissions/{of_name}"
                print(f"  Fetching overflow: {of_name}")
                of_data = client.get_json(of_url)
                if of_data:
                    all_earnings.extend(find_earnings_8ks(of_data, form_type=form_type))
                    all_10q10k.extend(find_10q_10k(of_data))

    form_label = form_type
    print(f"  Found {len(all_earnings)} earnings {form_label}(s), {len(all_10q10k)} 10-Q/10-K(s)")

    # Match filings to quarters by call_date proximity
    results = {}

    if form_type == "6-K":
        # 6-K: match closest filing to each call date (no item separation)
        for qid, call_date in target_dates.items():
            matched = None
            best_delta = None

            for window in (3, 7):
                if matched:
                    break
                for filing in all_earnings:
                    try:
                        fd = datetime.strptime(filing["filingDate"], "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        continue
                    delta = abs((fd - call_date).days)
                    if delta <= window:
                        if best_delta is None or delta < best_delta:
                            best_delta = delta
                            matched = filing
                if matched and window == 7:
                    print(f"  Note: {qid} matched {form_type} at ±{best_delta}d (widened window)")

            # Find companion 10-Q/10-K or 20-F (filed within 60 days after call date)
            matched_periodic = None
            best_periodic_delta = None
            for filing in all_10q10k:
                try:
                    fd = datetime.strptime(filing["filingDate"], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue
                delta_days = (fd - call_date).days
                if 0 <= delta_days <= 60:
                    if best_periodic_delta is None or delta_days < best_periodic_delta:
                        best_periodic_delta = delta_days
                        matched_periodic = filing

            if matched:
                results[qid] = {
                    "8k": matched,  # Keep key as '8k' for pipeline compatibility
                    "7_01": None,
                    "10q_10k": matched_periodic,
                }
            else:
                print(f"  Warning: No {form_type} found for {qid} (call_date={call_date})")

    else:
        # 8-K: separate 2.02 from 7.01-only filings (prefer 2.02)
        filings_2_02 = [f for f in all_earnings if "2.02" in str(f.get("items", ""))]
        filings_7_01 = [f for f in all_earnings if "7.01" in str(f.get("items", "")) and "2.02" not in str(f.get("items", ""))]

        for qid, call_date in target_dates.items():
            matched_2_02 = None
            matched_7_01 = None

            # Try Item 2.02 first (canonical earnings press release)
            for window in (3, 7):
                if matched_2_02:
                    break
                best_delta = None
                for filing in filings_2_02:
                    try:
                        fd = datetime.strptime(filing["filingDate"], "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        continue
                    delta = abs((fd - call_date).days)
                    if delta <= window:
                        if best_delta is None or delta < best_delta:
                            best_delta = delta
                            matched_2_02 = filing
                if matched_2_02 and window == 7:
                    print(f"  Note: {qid} matched 8-K at ±{best_delta}d (widened window)")

            # If no 2.02, try 7.01 (some companies use this for results)
            if not matched_2_02:
                for window in (3, 7):
                    if matched_2_02:
                        break
                    best_delta = None
                    for filing in filings_7_01:
                        try:
                            fd = datetime.strptime(filing["filingDate"], "%Y-%m-%d").date()
                        except (ValueError, TypeError):
                            continue
                        delta = abs((fd - call_date).days)
                        if delta <= window:
                            if best_delta is None or delta < best_delta:
                                best_delta = delta
                                matched_2_02 = filing  # Use as primary match
                    if matched_2_02 and window == 7:
                        print(f"  Note: {qid} matched 7.01 8-K at ±{best_delta}d (widened window)")

            # Find companion Item 7.01 filing (financial supplement, same day)
            if matched_2_02:
                filing_date = matched_2_02["filingDate"]
                for filing in filings_7_01:
                    if filing["filingDate"] == filing_date and filing is not matched_2_02:
                        matched_7_01 = filing
                        break

            # Find companion 10-Q/10-K (filed within 60 days after call date)
            matched_periodic = None
            best_periodic_delta = None
            for filing in all_10q10k:
                try:
                    fd = datetime.strptime(filing["filingDate"], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue
                delta_days = (fd - call_date).days
                if 0 <= delta_days <= 60:
                    if best_periodic_delta is None or delta_days < best_periodic_delta:
                        best_periodic_delta = delta_days
                        matched_periodic = filing

            if matched_2_02:
                results[qid] = {
                    "8k": matched_2_02,
                    "7_01": matched_7_01,
                    "10q_10k": matched_periodic,
                }
            else:
                print(f"  Warning: No earnings 8-K (Item 2.02) found for {qid} (call_date={call_date})")

    return results


# ---------------------------------------------------------------------------
# Exhibit Download
# ---------------------------------------------------------------------------

def fetch_filing_exhibits(client, cik, accession):
    """Fetch the filing index and return exhibit filenames.

    Tries JSON index first, falls back to HTML.

    Returns dict: { 'EX-99.1': filename, 'EX-99.2': filename, ... }
    """
    # Accession number without dashes for URL path
    acc_nodash = accession.replace("-", "")

    # Try JSON index first
    json_url = f"{SEC_ARCHIVES}/{cik}/{acc_nodash}/{accession}-index.json"
    data = client.get_json(json_url)

    exhibits = {}

    if data and "directory" in data:
        items = data["directory"].get("item", [])
        for item in items:
            name = item.get("name", "")
            doc_type = item.get("type", "")
            if doc_type.upper().startswith("EX-99"):
                exhibits[doc_type.upper()] = name
        if exhibits:
            return exhibits

    # Fallback: parse HTML index
    html_url = f"{SEC_ARCHIVES}/{cik}/{acc_nodash}/{accession}-index.htm"
    resp = client.get(html_url)
    if resp.status_code != 200:
        print(f"  WARNING: Could not fetch filing index for {accession}")
        return exhibits

    soup = BeautifulSoup(resp.text, "html.parser")
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) >= 4:
            doc_type = cells[3].get_text(strip=True).upper()
            if doc_type.startswith("EX-99"):
                link = cells[2].find("a")
                if link:
                    href = link.get("href", "")
                    filename = href.split("/")[-1] if "/" in href else href
                    exhibits[doc_type] = filename

    return exhibits


def download_exhibit(client, cik, accession, filename, output_path):
    """Download a single exhibit file to output_path.

    Returns True on success, False on failure.
    """
    acc_nodash = accession.replace("-", "")
    url = f"{SEC_ARCHIVES}/{cik}/{acc_nodash}/{filename}"

    resp = client.get(url)
    if resp.status_code != 200:
        print(f"  ERROR: Could not download {url}")
        return False

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(resp.content)

    print(f"  Downloaded: {filename} ({len(resp.content):,} bytes) -> {output_path}")
    return True


def download_quarter_exhibits(client, cik, ticker, quarter_id, filing_info):
    """Download exhibits for a quarter's 8-K filing.

    Downloads EX-99.1 (press release) and EX-99.2 (supplement) from Item 2.02 filing.
    Also checks companion Item 7.01 filing for financial supplement.

    Args:
        filing_info: dict with '8k', optionally '7_01' and '10q_10k'

    Returns dict: { 'press_release': local_path, 'supplement': local_path }
    """
    edgar_dir = os.path.join(PROJECT_ROOT, "companies", ticker, "edgar")
    os.makedirs(edgar_dir, exist_ok=True)

    eight_k = filing_info.get("8k")
    if not eight_k:
        print(f"    No 8-K filing for {quarter_id}")
        return {}

    accession = eight_k["accessionNumber"]
    exhibits = fetch_filing_exhibits(client, cik, accession)

    downloaded = {}

    # Download EX-99.1 as press_release (also check EX-99 for companies like PGR)
    ex_99_1 = exhibits.get("EX-99.1") or exhibits.get("EX-99")
    if ex_99_1:
        out_path = os.path.join(edgar_dir, f"{quarter_id}_press_release.htm")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
            print(f"    Already exists: {quarter_id}_press_release.htm")
            downloaded["press_release"] = out_path
        elif download_exhibit(client, cik, accession, ex_99_1, out_path):
            downloaded["press_release"] = out_path
    else:
        # No EX-99.1: fall back to primary document (e.g., PGR embeds results
        # in the 8-K body; TSM sometimes files 6-K without exhibits)
        primary_doc = eight_k.get("primaryDocument", "")
        if primary_doc and primary_doc.endswith((".htm", ".html")):
            out_path = os.path.join(edgar_dir, f"{quarter_id}_press_release.htm")
            if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
                print(f"    Already exists: {quarter_id}_press_release.htm (primary doc)")
                downloaded["press_release"] = out_path
            elif download_exhibit(client, cik, accession, primary_doc, out_path):
                downloaded["press_release"] = out_path
        else:
            print(f"    Warning: No EX-99.1 found in {accession}")

    # Download EX-99.2 as supplement
    ex_99_2 = exhibits.get("EX-99.2")
    if ex_99_2:
        out_path = os.path.join(edgar_dir, f"{quarter_id}_supplement.htm")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
            print(f"    Already exists: {quarter_id}_supplement.htm")
            downloaded["supplement"] = out_path
        elif download_exhibit(client, cik, accession, ex_99_2, out_path):
            downloaded["supplement"] = out_path

    # Check companion 7.01 filing for supplement if we don't have one yet
    seven_01 = filing_info.get("7_01")
    if seven_01 and "supplement" not in downloaded:
        supp_acc = seven_01["accessionNumber"]
        supp_exhibits = fetch_filing_exhibits(client, cik, supp_acc)
        for key in ("EX-99.1", "EX-99.2"):
            if supp_exhibits.get(key):
                out_path = os.path.join(edgar_dir, f"{quarter_id}_supplement.htm")
                if download_exhibit(client, cik, supp_acc, supp_exhibits[key], out_path):
                    downloaded["supplement"] = out_path
                    break

    return downloaded


def download_exhibit_images(client, cik, accession, htm_path):
    """Download images referenced in an exhibit HTML file.

    Scans for <img src="..."> with relative paths (no http/https) and
    downloads each from the same EDGAR filing directory.

    Returns count of images downloaded.
    """
    if not os.path.exists(htm_path):
        return 0

    with open(htm_path, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    img_tags = soup.find_all("img")

    acc_nodash = accession.replace("-", "")
    img_dir = os.path.dirname(htm_path)
    count = 0

    for img in img_tags:
        src = img.get("src", "")
        if not src or src.startswith(("http://", "https://", "data:", "//")):
            continue
        # Skip if already downloaded
        img_path = os.path.join(img_dir, src)
        if os.path.exists(img_path) and os.path.getsize(img_path) > 100:
            count += 1
            continue
        # Download from EDGAR filing directory
        url = f"{SEC_ARCHIVES}/{cik}/{acc_nodash}/{src}"
        resp = client.get(url)
        if resp.status_code == 200:
            os.makedirs(os.path.dirname(img_path), exist_ok=True)
            with open(img_path, "wb") as f:
                f.write(resp.content)
            count += 1
        else:
            print(f"    WARNING: Could not download image {src}")

    return count


# ---------------------------------------------------------------------------
# HTML Table Parsing
# ---------------------------------------------------------------------------

def clean_cell_text(text):
    """Normalize cell text from an HTML financial table.

    - Strips whitespace and non-breaking spaces
    - Converts parenthesized numbers to negatives: (1,234) -> -1234
    - Removes $ signs, footnote markers
    - Returns cleaned string
    """
    if not text:
        return ""
    # Normalize whitespace
    text = text.replace("\xa0", " ").replace("\u200b", "").strip()
    # Remove footnote superscripts like (1), (a), etc. at end
    text = re.sub(r"\s*\([a-zA-Z]\)\s*$", "", text)
    text = re.sub(r"\s*\(\d\)\s*$", "", text)
    # Remove $ signs
    text = text.replace("$", "").strip()
    # Handle parenthesized negatives: (1,234) or (1,234.56)
    paren_match = re.match(r"^\(([0-9,]+\.?\d*)\)$", text)
    if paren_match:
        text = "-" + paren_match.group(1).replace(",", "")
    else:
        # Remove commas from numbers
        if re.match(r"^-?[0-9,]+\.?\d*$", text.replace(",", "")):
            text = text.replace(",", "")
    return text


def is_financial_table(table_soup):
    """Heuristic check if a <table> contains financial data.

    Looks for keywords like Revenue, Income, Earnings, Assets, etc.
    Also checks for numeric content density.
    """
    text = table_soup.get_text(" ", strip=True).lower()

    financial_keywords = [
        "revenue", "income", "earnings", "assets", "liabilities",
        "expenses", "net interest", "provision", "charge-off",
        "operating", "diluted", "per share", "total", "margin",
        "capital", "equity", "deposits", "loans", "compensation",
        "noninterest", "managed", "return on",
    ]

    keyword_hits = sum(1 for kw in financial_keywords if kw in text)
    if keyword_hits < 2:
        return False

    # Check for numeric density — at least some cells should have numbers
    cells = table_soup.find_all(["td", "th"])
    if len(cells) < 6:
        return False

    numeric_cells = 0
    for cell in cells:
        cell_text = cell.get_text(strip=True)
        # Check for number-like content
        if re.search(r"\d", cell_text):
            numeric_cells += 1

    return numeric_cells >= 4


def parse_html_tables(html_content):
    """Extract all financial tables from HTML content.

    Returns list of dicts:
      { 'headers': [...], 'rows': [[...], ...], 'caption': str }
    """
    soup = BeautifulSoup(html_content, "html.parser")
    tables = soup.find_all("table")
    results = []

    for table in tables:
        if not is_financial_table(table):
            continue

        # Extract caption
        caption = ""
        cap_tag = table.find("caption")
        if cap_tag:
            caption = cap_tag.get_text(" ", strip=True)
        else:
            # Look for preceding bold/header text
            prev = table.find_previous_sibling()
            if prev and prev.name in ("p", "div", "b", "strong", "h1", "h2", "h3", "h4"):
                caption = prev.get_text(" ", strip=True)

        # Parse header rows
        headers = []
        thead = table.find("thead")
        header_rows = thead.find_all("tr") if thead else []
        if not header_rows:
            # Try first row(s) with <th>
            for row in table.find_all("tr"):
                ths = row.find_all("th")
                if ths:
                    header_rows.append(row)
                else:
                    break

        for hrow in header_rows:
            cells = hrow.find_all(["th", "td"])
            h = [clean_cell_text(c.get_text(" ", strip=True)) for c in cells]
            if any(h):
                headers.append(h)

        # Use last header row as main headers (often there are multi-level headers)
        main_headers = headers[-1] if headers else []

        # Parse data rows
        rows = []
        tbody = table.find("tbody")
        data_rows = tbody.find_all("tr") if tbody else table.find_all("tr")

        for row in data_rows:
            # Skip rows that were already captured as headers
            if row.find("th") and not row.find("td"):
                continue
            cells = row.find_all(["td", "th"])
            r = [clean_cell_text(c.get_text(" ", strip=True)) for c in cells]
            if any(r):  # Skip completely empty rows
                rows.append(r)

        if rows:
            results.append({
                "headers": main_headers,
                "rows": rows,
                "caption": caption[:200] if caption else "",
            })

    return results


def _split_workiva_rows(text, num_cols):
    """Split a flat Workiva text string into label + values rows.

    The text is a continuous string like:
      'Management fees $444 $476 $523 $1,772 $1,899 Advisory... 141 181 205 623 822'

    We scan for sequences of num_cols consecutive numeric values and treat
    the text before each such sequence as the row label.

    Returns list of [label, val1, val2, ...] rows.
    """
    # Pattern matching financial values: $1,234  (1,234)  -1,234  1,234.56  —  –  -  N/A  NM
    val_pattern = r"""(?:
        \$?\([\d,]+\.?\d*\)       |   # parenthesized: $(1,234) or (1,234)
        -?\$?[\d,]+\.?\d*%?       |   # regular: $1,234  -1,234  12.5%
        [\u2014\u2013]            |   # em-dash or en-dash (meaning zero/N/A)
        N/?[AM]                        # NM or N/A
    )"""
    val_re = re.compile(val_pattern, re.VERBOSE)

    # Tokenize: split on whitespace, preserving token positions
    tokens = text.split()
    rows = []
    i = 0

    while i < len(tokens):
        # Try to find num_cols consecutive value tokens starting at some position
        # First, accumulate label tokens until we hit a value sequence
        label_tokens = []
        while i < len(tokens):
            # Check if the next num_cols tokens are all values
            if i + num_cols <= len(tokens):
                candidate = tokens[i:i + num_cols]
                if all(val_re.fullmatch(t) for t in candidate):
                    # Found a value sequence
                    label = " ".join(label_tokens).strip()
                    values = [clean_cell_text(v) for v in candidate]
                    if label:
                        rows.append([label] + values)
                    i += num_cols
                    label_tokens = []
                    break
            label_tokens.append(tokens[i])
            i += 1

        # If we ran out of tokens while accumulating label, break
        if label_tokens and i >= len(tokens):
            break

    return rows


def parse_workiva_hidden_text(html_content):
    """Extract financial data from Workiva slide-format supplements.

    Workiva/Wdesk renders financial data as JPEG slide images with hidden
    white text (1pt, color:white) containing the actual data for search
    indexability. This function extracts that hidden text and parses it
    into structured table-like data.

    Returns list of dicts with same format as parse_html_tables():
      { 'headers': [...], 'rows': [[...], ...], 'caption': str }
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Find all hidden white text elements (Workiva pattern)
    # Pattern 1: style="color:white" or style="font-size:1pt;color:white"
    hidden_fonts = soup.find_all("font", style=re.compile(r"color\s*:\s*white", re.I))
    # Pattern 2: color="#FFFFFF" or color="white" as attribute
    if not hidden_fonts:
        hidden_fonts = soup.find_all("font", attrs={"color": re.compile(r"^(?:#FFF(?:FFF)?|white)$", re.I)})
    if not hidden_fonts:
        return []

    financial_keywords = [
        "revenue", "income", "earnings", "assets", "liabilities",
        "expenses", "operating", "diluted", "per share", "total",
        "margin", "capital", "equity", "fee", "compensation",
        "management fees", "advisory", "spread", "segment",
        "cash flow", "ebitda", "adjusted", "gaap",
    ]

    # Common column header patterns (quarter labels)
    # Matches: 4Q'23, 1Q'24, FY'24, FY'23, 1H'24, LTM 1Q'25
    col_header_re = re.compile(
        r"(?:LTM\s+)?(?:\d[QH]|FY)\s*['\u2019]?\s*\d{2}"
    )

    results = []

    for font in hidden_fonts:
        text = font.get_text(" ", strip=True)
        text = text.replace("\xa0", " ").replace("\u200b", "")

        # Check for financial content
        text_lower = text.lower()
        keyword_hits = sum(1 for kw in financial_keywords if kw in text_lower)
        if keyword_hits < 2:
            continue

        # Check for numeric density
        if len(re.findall(r'\d', text)) < 10:
            continue

        # Find column headers
        headers = col_header_re.findall(text)
        if not headers:
            continue

        # Find the header sequence in the text to split caption from data
        # Look for the first occurrence of consecutive headers
        first_header_pos = text.find(headers[0])
        last_header = headers[-1]
        last_header_pos = text.rfind(last_header)
        header_end_pos = last_header_pos + len(last_header)

        caption = text[:first_header_pos].strip()
        data_text = text[header_end_pos:].strip()

        if not data_text:
            continue

        num_cols = len(headers)
        rows = _split_workiva_rows(data_text, num_cols)

        if len(rows) >= 2:
            results.append({
                "headers": [""] + headers,
                "rows": rows,
                "caption": caption[:200] if caption else "",
                "source": "workiva_hidden_text",
            })

    if results:
        print(f"    Parsed {len(results)} table(s) from Workiva hidden text")

    return results


# ---------------------------------------------------------------------------
# XBRL Enrichment
# ---------------------------------------------------------------------------

XBRL_CONCEPTS = {
    "Revenues": "Total Revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "Revenue",
    "NetIncomeLoss": "Net Income",
    "NetIncomeLossAvailableToCommonStockholdersBasic": "Net Income to Common",
    "EarningsPerShareBasic": "EPS (Basic)",
    "EarningsPerShareDiluted": "EPS (Diluted)",
    "InterestIncomeExpenseNet": "Net Interest Income",
    "NoninterestIncome": "Noninterest Revenue",
    "ProvisionForLoanLeaseAndOtherLosses": "Provision for Credit Losses",
    "ProvisionForCreditLosses": "Provision for Credit Losses",
    "Assets": "Total Assets",
    "Liabilities": "Total Liabilities",
    "StockholdersEquity": "Total Equity",
    "CommonStockSharesOutstanding": "Shares Outstanding",
    "OperatingIncomeLoss": "Operating Income",
    "CashAndCashEquivalentsAtCarryingValue": "Cash & Equivalents",
    "ComprehensiveIncomeNetOfTax": "Comprehensive Income",
    "ReturnOnEquity": "Return on Equity",
    "NoninterestExpense": "Noninterest Expense",
    "IncomeTaxExpenseBenefit": "Income Tax Expense",
}


def fetch_xbrl_facts(client, cik):
    """Fetch all XBRL company facts in a single API call.

    Returns the full companyfacts JSON, or None.
    """
    url = f"{SEC_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
    data = client.get_json(url)
    if data is None:
        print("  WARNING: Could not fetch XBRL company facts")
    return data


def extract_xbrl_for_quarter(xbrl_data, quarter_end_date):
    """Extract XBRL facts matching a specific quarter end date.

    Filters facts by end date and prefers 10-K/10-Q over 8-K data.

    Args:
        xbrl_data: full companyfacts JSON
        quarter_end_date: datetime.date for the quarter end

    Returns dict: { 'human_label': { 'value': ..., 'units': ..., 'form': ... } }
    """
    if not xbrl_data or not quarter_end_date:
        return {}

    date_str = quarter_end_date.strftime("%Y-%m-%d")
    results = {}

    us_gaap = xbrl_data.get("facts", {}).get("us-gaap", {})

    for concept, label in XBRL_CONCEPTS.items():
        concept_data = us_gaap.get(concept, {})
        if not concept_data:
            continue

        # Try each unit type (USD, USD/shares, shares, pure)
        for unit_type, entries in concept_data.get("units", {}).items():
            best_entry = None
            best_priority = -1

            for entry in entries:
                end = entry.get("end", "")
                if end != date_str:
                    continue

                # Prefer entries without start date (instant) or with quarterly duration
                form = entry.get("form", "")

                # Priority: 10-K > 10-Q > 8-K > other
                if form == "10-K":
                    priority = 3
                elif form == "10-Q":
                    priority = 2
                elif form == "8-K":
                    priority = 1
                else:
                    priority = 0

                # Prefer quarterly entries (with start date ~90 days before end)
                start = entry.get("start", "")
                if start:
                    try:
                        start_dt = datetime.strptime(start, "%Y-%m-%d").date()
                        end_dt = datetime.strptime(end, "%Y-%m-%d").date()
                        duration = (end_dt - start_dt).days
                        # Quarterly: 85-100 days; Annual: 360-370 days
                        if 85 <= duration <= 100:
                            priority += 0.5  # Prefer quarterly over annual
                    except (ValueError, TypeError):
                        pass

                if priority > best_priority:
                    best_priority = priority
                    best_entry = entry

            if best_entry:
                results[label] = {
                    "value": best_entry.get("val"),
                    "units": unit_type,
                    "form": best_entry.get("form", ""),
                    "filed": best_entry.get("filed", ""),
                    "concept": concept,
                }
                break  # Use first matching unit type

    return results


# ---------------------------------------------------------------------------
# Output Generation
# ---------------------------------------------------------------------------

def build_financials_json(ticker, quarter_id, filing_info, tables, xbrl_facts):
    """Build structured JSON for a quarter's financial data.

    Returns dict matching design spec: {ticker, quarter, filing_date, accession, tables, xbrl}
    """
    eight_k = filing_info.get("8k", {})

    return {
        "ticker": ticker,
        "quarter": quarter_id,
        "filing_date": eight_k.get("filingDate", ""),
        "accession": eight_k.get("accessionNumber", ""),
        "tables": tables if tables else [],
        "xbrl": xbrl_facts if xbrl_facts else {},
    }


def generate_earnings_markdown(ticker, quarter_id, company_name, cik, filing_info, tables, xbrl_facts):
    """Generate readable markdown summary of earnings data.

    Includes XBRL key metrics table and financial tables.
    Uses CIK in SEC EDGAR URLs (not ticker).
    """
    eight_k = filing_info.get("8k", {})
    accession = eight_k.get("accessionNumber", "")

    lines = []
    lines.append(f"# {company_name} — {quarter_id} Earnings Release")
    lines.append("")
    lines.append(f"**Ticker:** {ticker}")
    lines.append(f"**Filing Date:** {eight_k.get('filingDate', 'N/A')}")
    lines.append(f"**Accession:** {accession}")
    if accession:
        acc_nodash = accession.replace("-", "")
        cik_int = int(cik) if cik else 0
        lines.append(f"**Source:** [SEC EDGAR](https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{accession}-index.htm)")
    lines.append("")

    # XBRL Key Metrics
    if xbrl_facts:
        lines.append("## Key Metrics (XBRL)")
        lines.append("")
        lines.append("| Metric | Value | Units | Source |")
        lines.append("|--------|------:|-------|--------|")
        for label, info in sorted(xbrl_facts.items()):
            val = info.get("value", "")
            units = info.get("units", "")
            form = info.get("form", "")
            # Format large numbers
            if isinstance(val, (int, float)) and units == "USD" and abs(val) >= 1_000_000:
                if abs(val) >= 1_000_000_000:
                    val_str = f"${val / 1_000_000_000:,.2f}B"
                else:
                    val_str = f"${val / 1_000_000:,.1f}M"
            elif isinstance(val, (int, float)) and "shares" in units.lower():
                if abs(val) >= 1_000_000:
                    val_str = f"{val / 1_000_000:,.1f}M"
                else:
                    val_str = f"{val:,.0f}"
            elif isinstance(val, (int, float)):
                val_str = f"{val:,.4f}" if isinstance(val, float) and abs(val) < 100 else f"{val:,.0f}"
            else:
                val_str = str(val)
            lines.append(f"| {label} | {val_str} | {units} | {form} |")
        lines.append("")

    # Financial Tables
    if tables:
        lines.append("## Financial Tables (from Exhibits)")
        lines.append("")
        for i, tbl in enumerate(tables, 1):
            caption = tbl.get("caption", f"Table {i}")
            lines.append(f"### {caption}")
            lines.append("")

            headers = tbl.get("headers", [])
            rows = tbl.get("rows", [])

            if headers:
                lines.append("| " + " | ".join(str(h) for h in headers) + " |")
                lines.append("| " + " | ".join("---" for _ in headers) + " |")

            for row in rows:
                # Pad row to match header length
                if headers:
                    while len(row) < len(headers):
                        row.append("")
                    row = row[:len(headers)]
                lines.append("| " + " | ".join(str(c) for c in row) + " |")
            lines.append("")

    if not xbrl_facts and not tables:
        lines.append("*No financial data extracted for this quarter.*")
        lines.append("")

    lines.append("---")
    lines.append(f"*Generated by edgar_download.py on {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return "\n".join(lines)


def save_quarter_outputs(ticker, quarter_id, company_name, cik, filing_info, tables, xbrl_facts):
    """Save JSON and markdown output files for a quarter.

    Files are saved to companies/{ticker}/edgar/ (flat directory).
    """
    edgar_dir = os.path.join(PROJECT_ROOT, "companies", ticker, "edgar")
    os.makedirs(edgar_dir, exist_ok=True)

    # Save JSON
    json_path = os.path.join(edgar_dir, f"{quarter_id}_financials.json")
    json_data = build_financials_json(ticker, quarter_id, filing_info, tables, xbrl_facts)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"    JSON: {os.path.getsize(json_path):,} bytes -> {os.path.basename(json_path)}")

    # Save Markdown
    md_path = os.path.join(edgar_dir, f"{quarter_id}_earnings.md")
    md_content = generate_earnings_markdown(
        ticker, quarter_id, company_name, cik, filing_info, tables, xbrl_facts
    )
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"    MD:   {len(md_content):,} chars -> {os.path.basename(md_path)}")


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------

def quarter_end_date(quarter_id, fiscal_year_type, fy_end_month=12):
    """Estimate the quarter-end date from a quarter ID.

    Handles both calendar and offset fiscal years.

    Examples:
      Q1_2022 (calendar) -> 2022-03-31
      Q4_2022 (calendar) -> 2022-12-31
      Q1_FY2023 (offset, end_month=6) -> 2022-09-30
      Q4_FY2023 (offset, end_month=6) -> 2023-06-30

    Returns datetime.date or None.
    """
    # Parse quarter number and year
    match = re.match(r"Q(\d)_(?:FY)?(\d{4})", quarter_id)
    if not match:
        print(f"  WARNING: Could not parse quarter ID '{quarter_id}'")
        return None

    q_num = int(match.group(1))
    year = int(match.group(2))

    if fiscal_year_type == "calendar" or fy_end_month == 12:
        # Calendar year: Q1=Mar, Q2=Jun, Q3=Sep, Q4=Dec
        month_map = {1: 3, 2: 6, 3: 9, 4: 12}
        month = month_map.get(q_num, 12)
        last_day = calendar.monthrange(year, month)[1]
        return datetime(year, month, last_day).date()
    else:
        # Offset fiscal year: FY ends in fy_end_month
        # Q4 ends on fy_end_month; Q1 is 9 months before FY end
        # For FY ending June (month=6):
        #   Q1 = Jul-Sep (ends Sep), Q2 = Oct-Dec (ends Dec),
        #   Q3 = Jan-Mar (ends Mar), Q4 = Apr-Jun (ends Jun)
        quarter_offsets = {
            1: -9,   # 3 months into FY
            2: -6,   # 6 months into FY
            3: -3,   # 9 months into FY
            4: 0,    # FY end
        }
        offset = quarter_offsets.get(q_num, 0)
        # Calculate the end month
        end_month = fy_end_month + offset
        end_year = year
        while end_month <= 0:
            end_month += 12
            end_year -= 1
        while end_month > 12:
            end_month -= 12
            end_year += 1

        last_day = calendar.monthrange(end_year, end_month)[1]
        return datetime(end_year, end_month, last_day).date()


def process_ticker(ticker, quarter_filter=None, discover_only=False, parse_only=False):
    """Full pipeline: CIK -> discover -> download -> parse -> XBRL -> output.

    Args:
        ticker: stock ticker (e.g. 'JPM')
        quarter_filter: optional quarter ID to process (e.g. 'Q4_2025')
        discover_only: if True, only discover filings, don't download/parse
        parse_only: if True, skip discovery/download, just parse existing files
    """
    print(f"\n{'='*60}")
    print(f"EDGAR Download: {ticker}")
    print(f"{'='*60}")

    # Load config
    config = load_config(ticker)
    company_name = config.get("company", {}).get("name", ticker)
    fiscal_year_type = config.get("company", {}).get("fiscal_year", "calendar")
    fy_end_month = config.get("company", {}).get("fiscal_year_end_month", 12)

    client = EdgarClient()
    edgar_dir = os.path.join(PROJECT_ROOT, "companies", ticker, "edgar")

    # Step 1: CIK resolution (save to config once)
    cik = config.get("company", {}).get("edgar_cik", "")
    if not cik:
        print(f"Resolving CIK for {ticker}...")
        cik = resolve_cik(client, ticker)
        if not cik:
            return
        config.setdefault("company", {})["edgar_cik"] = cik
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

    # Skip already-downloaded quarters (unless parse_only)
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

    if parse_only:
        # Skip discovery and download; just parse existing exhibits
        print("\n[Parse-only mode]")
        xbrl_data = fetch_xbrl_facts(client, cik)

        for q in to_process:
            qid = q["id"]
            print(f"\n  [{qid}]")

            # Find existing exhibit files
            tables = []
            for fname in os.listdir(edgar_dir) if os.path.isdir(edgar_dir) else []:
                if fname.startswith(qid) and fname.endswith((".htm", ".html")):
                    fpath = os.path.join(edgar_dir, fname)
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        html = f.read()
                    parsed = parse_html_tables(html)
                    if parsed:
                        print(f"    Parsed {len(parsed)} table(s) from {fname}")
                        tables.extend(parsed)
                    elif "supplement" in fname:
                        # Try Workiva hidden text for slide-based supplements
                        parsed = parse_workiva_hidden_text(html)
                        if parsed:
                            tables.extend(parsed)

            # XBRL
            q_end = quarter_end_date(qid, fiscal_year_type, fy_end_month)
            xbrl_facts = extract_xbrl_for_quarter(xbrl_data, q_end) if xbrl_data else {}

            # Build filing_info stub from existing JSON or config
            filing_info = {"8k": {"accessionNumber": q.get("edgar_8k_accession", ""),
                                   "filingDate": "", "items": ""}}

            save_quarter_outputs(ticker, qid, company_name, cik, filing_info, tables, xbrl_facts)
        return

    # Step 3: Discover filings
    print(f"\nDiscovering EDGAR filings for {company_name}...")
    discovered = discover_filings(client, cik, config)
    print(f"  Matched {len(discovered)}/{len(to_process)} quarters")

    # Update config with discovered accessions
    config_changed = False
    for q in config.get("quarters", []):
        if q["id"] in discovered:
            info = discovered[q["id"]]
            eight_k = info.get("8k", {})
            acc = eight_k.get("accessionNumber", "")
            if acc and q.get("edgar_8k_accession") != acc:
                q["edgar_8k_accession"] = acc
                config_changed = True
    if config_changed:
        save_config(ticker, config)
        print("  Config updated with EDGAR accession numbers")

    if discover_only:
        print("\n--discover-only: stopping after discovery.")
        for qid, info in sorted(discovered.items()):
            eight_k = info.get("8k", {})
            print(f"  {qid}: {eight_k.get('accessionNumber', 'N/A')} ({eight_k.get('filingDate', 'N/A')})")
        return

    # Step 4: Fetch XBRL facts (one call, cached for all quarters)
    print(f"\nFetching XBRL company facts...")
    xbrl_data = fetch_xbrl_facts(client, cik)
    if xbrl_data:
        us_gaap_count = len(xbrl_data.get("facts", {}).get("us-gaap", {}))
        print(f"  Loaded {us_gaap_count} us-gaap concepts")

    # Step 5: Process each quarter
    success = []
    failed = []
    for q in to_process:
        qid = q["id"]
        print(f"\n  [{qid}]")

        if qid not in discovered:
            print(f"    Skipped: no matching 8-K found")
            failed.append((qid, "no matching 8-K"))
            continue

        filing_info = discovered[qid]

        try:
            # Download exhibits
            downloaded = download_quarter_exhibits(client, cik, ticker, qid, filing_info)

            # Download images referenced in exhibit HTML files
            accession = filing_info.get("8k", {}).get("accessionNumber", "")
            for label, fpath in downloaded.items():
                if fpath.endswith((".htm", ".html")):
                    img_count = download_exhibit_images(client, cik, accession, fpath)
                    if img_count:
                        print(f"    Downloaded {img_count} image(s) for {label}")

            # Parse press release HTML
            tables = []
            pr_path = os.path.join(edgar_dir, f"{qid}_press_release.htm")
            if os.path.exists(pr_path):
                with open(pr_path, "r", encoding="utf-8", errors="replace") as f:
                    tables = parse_html_tables(f.read())
                if tables:
                    print(f"    Parsed {len(tables)} financial tables")

            # If no tables from press release, try supplement
            if not tables:
                supp_path = os.path.join(edgar_dir, f"{qid}_supplement.htm")
                if os.path.exists(supp_path):
                    with open(supp_path, "r", encoding="utf-8", errors="replace") as f:
                        supp_html = f.read()
                    tables = parse_html_tables(supp_html)
                    if tables:
                        print(f"    Parsed {len(tables)} table(s) from supplement")
                    else:
                        # Try Workiva hidden text for slide-based supplements
                        tables = parse_workiva_hidden_text(supp_html)

            # Fallback: try any other downloaded exhibit
            if not tables:
                for label, fpath in sorted(downloaded.items()):
                    if fpath.endswith((".htm", ".html")):
                        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                            parsed = parse_html_tables(f.read())
                        if parsed:
                            print(f"    Parsed {len(parsed)} table(s) from {label}")
                            tables.extend(parsed)

            # XBRL for this quarter
            q_end = quarter_end_date(qid, fiscal_year_type, fy_end_month)
            xbrl_facts = extract_xbrl_for_quarter(xbrl_data, q_end) if q_end and xbrl_data else {}
            if xbrl_facts:
                print(f"    XBRL: {len(xbrl_facts)} metrics for period ending {q_end}")

            # Save outputs
            save_quarter_outputs(ticker, qid, company_name, cik, filing_info, tables, xbrl_facts)
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


# ---------------------------------------------------------------------------
# Monthly Download Pipeline
# ---------------------------------------------------------------------------

def process_monthly(ticker, months_back=48):
    """Download ALL monthly result filings from EDGAR.

    Finds every 8-K with Item 2.02/7.01 filed in the last N months,
    skips those already downloaded as quarterly filings, and downloads
    the rest. Output files are named M_YYYY-MM-DD_*.

    Used for companies like PGR that report monthly results via 8-K.
    """
    print(f"\n{'='*60}")
    print(f"EDGAR Monthly Download: {ticker} (last {months_back} months)")
    print(f"{'='*60}")

    config = load_config(ticker)
    company_name = config.get("company", {}).get("name", ticker)
    form_type = config.get("company", {}).get("edgar_form_type", "8-K")

    client = EdgarClient()
    edgar_dir = os.path.join(PROJECT_ROOT, "companies", ticker, "edgar")
    os.makedirs(edgar_dir, exist_ok=True)

    cik = config.get("company", {}).get("edgar_cik", "")
    if not cik:
        cik = resolve_cik(client, ticker)
        if not cik:
            return
        config.setdefault("company", {})["edgar_cik"] = cik
        save_config(ticker, config)
    print(f"CIK: {cik}")

    # 1. Discover all result filings in date range
    cutoff = (datetime.now() - timedelta(days=months_back * 31)).date()

    url = f"{SEC_BASE}/submissions/CIK{cik}.json"
    data = client.get_json(url)
    if data is None:
        print(f"ERROR: Could not fetch submissions")
        return

    all_earnings = []
    recent = data.get("filings", {}).get("recent", {})
    if recent:
        all_earnings.extend(find_earnings_8ks(recent, form_type=form_type))

    for of in data.get("filings", {}).get("files", []):
        of_name = of.get("name", "")
        filing_to = of.get("filingTo", "")
        should_fetch = True
        if filing_to:
            try:
                should_fetch = datetime.strptime(filing_to, "%Y-%m-%d").date() >= cutoff
            except (ValueError, TypeError):
                pass
        if should_fetch and of_name:
            print(f"  Fetching overflow: {of_name}")
            of_data = client.get_json(f"{SEC_BASE}/submissions/{of_name}")
            if of_data:
                all_earnings.extend(find_earnings_8ks(of_data, form_type=form_type))

    # 2. Filter by date, deduplicate, sort
    seen = set()
    filings = []
    for f in all_earnings:
        acc = f.get("accessionNumber", "")
        if acc in seen:
            continue
        seen.add(acc)
        try:
            fd = datetime.strptime(f["filingDate"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if fd >= cutoff:
            filings.append(f)

    filings.sort(key=lambda x: x.get("filingDate", ""))
    print(f"  Found {len(filings)} result filing(s) in date range")

    # 3. Build set of already-downloaded accessions (from quarterly pipeline)
    quarterly_accs = set()
    for q in config.get("quarters", []):
        acc = q.get("edgar_8k_accession", "")
        if acc:
            json_path = os.path.join(edgar_dir, f"{q['id']}_financials.json")
            if os.path.exists(json_path) and os.path.getsize(json_path) > 100:
                quarterly_accs.add(acc)

    # 4. Process each filing
    success = []
    skipped_quarterly = []
    skipped_exists = []
    failed = []

    for filing in filings:
        acc = filing.get("accessionNumber", "")
        fd = filing.get("filingDate", "")
        # Name by reporting month (month before filing), e.g. filed 2024-02-15 → M_2024-01
        try:
            fd_date = datetime.strptime(fd, "%Y-%m-%d").date()
            if fd_date.month == 1:
                file_id = f"M_{fd_date.year - 1}-12"
            else:
                file_id = f"M_{fd_date.year}-{fd_date.month - 1:02d}"
        except (ValueError, TypeError):
            file_id = f"M_{fd}"

        # Skip if already downloaded as quarterly
        if acc in quarterly_accs:
            skipped_quarterly.append(file_id)
            continue

        # Skip if monthly file already exists
        json_path = os.path.join(edgar_dir, f"{file_id}_financials.json")
        if os.path.exists(json_path) and os.path.getsize(json_path) > 100:
            skipped_exists.append(file_id)
            continue

        print(f"\n  [{file_id}] accession={acc}")

        try:
            filing_info = {"8k": filing, "7_01": None, "10q_10k": None}

            # Download exhibits
            exhibits = fetch_filing_exhibits(client, cik, acc)
            downloaded = {}

            ex_99 = exhibits.get("EX-99.1") or exhibits.get("EX-99")
            if ex_99:
                out_path = os.path.join(edgar_dir, f"{file_id}_press_release.htm")
                if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
                    downloaded["press_release"] = out_path
                elif download_exhibit(client, cik, acc, ex_99, out_path):
                    downloaded["press_release"] = out_path
            else:
                # Primary document fallback
                primary_doc = filing.get("primaryDocument", "")
                if primary_doc and primary_doc.endswith((".htm", ".html")):
                    out_path = os.path.join(edgar_dir, f"{file_id}_press_release.htm")
                    if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
                        downloaded["press_release"] = out_path
                    elif download_exhibit(client, cik, acc, primary_doc, out_path):
                        downloaded["press_release"] = out_path

            ex_99_2 = exhibits.get("EX-99.2")
            if ex_99_2:
                out_path = os.path.join(edgar_dir, f"{file_id}_supplement.htm")
                if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
                    downloaded["supplement"] = out_path
                elif download_exhibit(client, cik, acc, ex_99_2, out_path):
                    downloaded["supplement"] = out_path

            # Download images
            for label, fpath in downloaded.items():
                if fpath.endswith((".htm", ".html")):
                    img_count = download_exhibit_images(client, cik, acc, fpath)
                    if img_count:
                        print(f"    Downloaded {img_count} image(s)")

            # Parse tables
            tables = []
            pr_path = os.path.join(edgar_dir, f"{file_id}_press_release.htm")
            if os.path.exists(pr_path):
                with open(pr_path, "r", encoding="utf-8", errors="replace") as f_in:
                    tables = parse_html_tables(f_in.read())
                if tables:
                    print(f"    Parsed {len(tables)} financial tables")

            if not tables:
                supp_path = os.path.join(edgar_dir, f"{file_id}_supplement.htm")
                if os.path.exists(supp_path):
                    with open(supp_path, "r", encoding="utf-8", errors="replace") as f_in:
                        supp_html = f_in.read()
                    tables = parse_html_tables(supp_html)
                    if not tables:
                        tables = parse_workiva_hidden_text(supp_html)

            # Save outputs (no XBRL for monthly — it's quarterly-aligned)
            save_quarter_outputs(ticker, file_id, company_name, cik,
                                 filing_info, tables, {})
            success.append(file_id)

        except Exception as e:
            print(f"    ERROR: {e}")
            failed.append((file_id, str(e)))

    # Report
    print(f"\n{'='*60}")
    print(f"Monthly Download Complete: {ticker}")
    print(f"  Downloaded: {len(success)}")
    if skipped_quarterly:
        print(f"  Skipped (already in quarterly): {len(skipped_quarterly)}")
    if skipped_exists:
        print(f"  Skipped (already exists): {len(skipped_exists)}")
    if failed:
        print(f"  Failed: {len(failed)}")
        for fid, reason in failed:
            print(f"    {fid}: {reason}")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    ticker_arg = sys.argv[1].upper()
    quarter_arg = None
    discover_only_flag = False
    parse_only_flag = False
    monthly_flag = False
    monthly_months = 48

    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--discover-only":
            discover_only_flag = True
        elif arg == "--parse-only":
            parse_only_flag = True
        elif arg == "--monthly":
            monthly_flag = True
            # Check if next arg is a number (months count)
            if i + 1 < len(sys.argv) and sys.argv[i + 1].isdigit():
                monthly_months = int(sys.argv[i + 1])
                i += 1
        elif not arg.startswith("--") and "_" in arg:
            quarter_arg = arg
        else:
            print(f"Unknown argument: {arg}")
            print(__doc__)
            sys.exit(1)
        i += 1

    if monthly_flag:
        process_monthly(ticker_arg, months_back=monthly_months)
    else:
        process_ticker(
            ticker=ticker_arg,
            quarter_filter=quarter_arg,
            discover_only=discover_only_flag,
            parse_only=parse_only_flag,
        )
