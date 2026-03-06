# Earnings Update — Full Pipeline

Run the complete earnings pipeline for a company's latest quarter: download transcript + EDGAR release, extract guidance, generate pages, and update all editorial HTML (comparison, results, index).

**Argument:** `<args>` (format: `TICKER [QUARTER]`, e.g., `AVGO`, `AVGO FQ1_2026`)

---

## Step 1: Determine What to Update

1. **Parse arguments.** Split `<args>` into TICKER and optional QUARTER. If TICKER is missing, ask the user.

2. **Load the company config** from `companies/{{TICKER}}/config.yaml`. If missing, tell the user to run `/earnings-setup {{TICKER}}` first.

3. **Identify the target quarter:**
   - If QUARTER is provided, use it.
   - If omitted, use the **last entry** in the config's `quarters` list (the most recent quarter).
   - Extract `call_date`, `reporting_quarter`, and `id` from the config.

4. **Check what already exists** for the target quarter:
   - Transcript: `companies/{{TICKER}}/transcripts/{{TICKER}}_{{QUARTER}}_transcript.txt`
   - EDGAR data: `companies/{{TICKER}}/edgar/{{QUARTER}}_earnings.md`
   - Guidance extraction: `companies/{{TICKER}}/guidance/{{QUARTER}}_guidance.md`
   - Quarter HTML page: `companies/{{TICKER}}/quarters/{{QUARTER}}.html`

   Report what exists and what needs to be done. Skip steps where output already exists (unless the user says to redo them).

---

## Step 2: Download (if needed)

Run these two downloads in parallel if both are needed:

### 2a. Transcript from BamSEC
If the transcript `.txt` file doesn't exist or is <1000 chars:
- Follow the `/earnings-download` skill instructions for the single quarter: `{{TICKER}} {{QUARTER}}`
- This requires Chrome browser automation and a BamSEC login

### 2b. EDGAR Earnings Release
If the EDGAR `_earnings.md` file doesn't exist:
- Run: `cd /c/Users/AdrianOw/Projects/Call-extraction && python edgar_download.py {{TICKER}} {{QUARTER}}`

After both complete, confirm both files exist before proceeding.

---

## Step 3: Extract Guidance

If `companies/{{TICKER}}/guidance/{{QUARTER}}_guidance.md` doesn't exist:
- Follow the `/earnings-extract` skill instructions: `{{TICKER}} {{QUARTER}}`
- This reads the transcript, the extraction prompt template, prior quarter guidance, and EDGAR data, then writes the structured guidance MD file.

If the guidance file already exists, skip this step (tell the user).

---

## Step 4: Generate Quarter HTML Pages

Run: `cd /c/Users/AdrianOw/Projects/Call-extraction && python lib/generate_company.py {{TICKER}}`

This regenerates all quarter detail pages in `companies/{{TICKER}}/quarters/`. It skips `comparison.html` if it already exists (editorial pages are updated manually in the next step).

---

## Step 5: Update comparison.html

This is the most complex step — the comparison page is an editorial document with 15-25 topical sections. Each section has a data table that needs the new quarter's data added.

### 5a. Read Context
Read these files:
- `companies/{{TICKER}}/comparison.html` (the existing editorial comparison page)
- `companies/{{TICKER}}/guidance/{{QUARTER}}_guidance.md` (the new quarter's extracted data)
- The prior quarter's guidance file (for context on what changed)

### 5b. Update the Nav Bar
The comparison page has a `<div class="quarter-nav">` with links to individual quarter pages, grouped by year. Add the new quarter's link in the correct position:
- Find the appropriate year group (or create a new one if this is the first quarter of a new year)
- Add an `<a>` link to `quarters/{{QUARTER}}.html` in the correct position within the year group
- Quarters within a year group should be in reverse chronological order (Q4 before Q3, etc.)

### 5c. Update the Title/Header
- Update the quarter count in the `<title>` and `<h1>` (e.g., "16-Quarter" → "17-Quarter")
- Update the date range in the subtitle if the new quarter extends it

### 5d. Update Each Section's Table
For each section in the comparison page:
1. **Read the section's table** to understand its column structure
2. **Find the relevant data** for this section in the new guidance MD file
3. **Add a new row** at the TOP of the table body (reverse chronological — newest first)
4. If a new fiscal year starts, add a **year divider row** (`<tr class="year-divider">`) above the new data row, with a contextual label if appropriate
5. Use the same formatting patterns as existing rows:
   - `.pos` class for positive changes (green text)
   - `.neg` class for negative changes (red text)
   - `.raised` class for rows where guidance was raised (green background)
   - `.lowered` class for rows where guidance was lowered (red background)
   - `.tag-raised`, `.tag-lowered`, `.tag-maintained`, `.tag-new` for inline badges
   - `.muted` for "Not discussed"
6. If a prior quarter's row said "Pending" for forward guidance, update it with the actual result now that we have it

### 5e. Handle Forward-Looking Guidance
If the new quarter introduces guidance for a NEW fiscal year (e.g., Q4 FY2026 call gives FY2027 guidance), do NOT mix forward-looking guidance into the historical tables. Instead:
- Create a **new dedicated section** for the forward guidance (e.g., "FY2027 Guidance (Initial)")
- Place it between the last guidance-tracking section and the first operational/strategic section
- Add an entry to the Table of Contents
- Use a consolidated table showing all guided metrics for the new period

This keeps historical comparison tables clean and analytically pure.

### 5f. Update Insight Boxes
If the new data changes the narrative of a section's insight box (e.g., a streak continues, a record is set, a trend reverses), update the insight text to reflect the new data point.

### 5g. Update Key Takeaways
Review the "Key Takeaways" section at the bottom. If any takeaway references specific data (e.g., "revenue has grown for X consecutive quarters"), update the numbers. If the new quarter introduces a significant new storyline, consider adding a takeaway and removing the least impactful one to maintain 8-12 items.

### 5h. Update Footer
Update the data range in the footer if needed (e.g., "Q1 2022 – Q4 2025" → "Q1 2022 – Q1 2026").

### Important Comparison Update Rules
- **Reverse chronological order in ALL tables.** Newest year group first, newest quarter first within each group. This is the most common mistake — always verify ordering after edits.
- **Never skip a section.** Even if the new quarter has no data for a section, add a row with "Not discussed" or "Maintained" as appropriate.
- **Preserve editorial voice.** The comparison page is an analyst report. Match the existing tone and level of detail.
- **Cross-reference between sections.** If a data point in one section relates to another section, note it.

---

## Step 6: Update results.html

If `companies/{{TICKER}}/results.html` exists:

### 6a. Read Context
- Read `companies/{{TICKER}}/results.html`
- Read the new quarter's guidance MD (for actuals)
- Read the prior quarter's guidance MD (for the guidance that predicted this quarter's actuals)

### 6b. Update Data Mapping
The critical data mapping: **Q[X] call's guidance predicts Q[X+1]'s results.**

For example, if processing Q1 2026:
- The Q4 2025 call gave Q1 2026 guidance → now we have Q1 2026 actuals to compare
- The Q1 2026 call gives Q2 2026 guidance → this becomes a new "Pending" row

### 6c. Update Revenue Table
1. Find the most recent "Pending" row for the quarter we now have actuals for
2. Replace "Pending" with the actual values:
   - Actual revenue
   - vs Low, vs Mid, vs High (percentage difference for revenue)
3. Add a new "Pending" row at the top for the newest forward guidance
4. Add year divider rows as needed

### 6d. Update Margin Tables (GM, OM)
Same pattern as revenue, but use basis point differences instead of percentages:
```
vs_mid = (actual - midpoint) × 100 → "+155 bps"
```

### 6e. Update Scorecard Cards
Recalculate aggregate statistics:
- Beat rate vs midpoint (X/N quarters)
- Average beat vs midpoint
- Beat rate vs high end
- Times missed low end
- Update these in the `.score-card` elements at the top

### 6f. Add to Key Takeaways
If the new quarter's results are noteworthy (record beat, first miss, etc.), update the relevant takeaway card.

### 6g. Update Nav Bar and Header
Same pattern as comparison — add new quarter link, update quarter count.

---

## Step 7: Update index.html

Read `index.html` and update the card for this company:

1. **Quarter count:** Update the number (e.g., "16 quarters" → "17 quarters")
2. **Date range:** Update the end of the range (e.g., "Q1 2022 – Q4 2025" → "Q1 2022 – Q1 2026")
3. **Last call date:** Update the "Last call:" line to show the new quarter's call date

The index card structure for each company:
```html
<div class="card-detail">17 quarters: FQ1 2022 &ndash; FQ1 2026</div>
<div class="card-detail" style="color:#6c757d; font-size:0.78rem;">Last call: Mar 4, 2026</div>
```

---

## Step 8: Final Report

Summarize what was done:
- Which steps were executed vs skipped
- Files created or modified
- Key data points from the new quarter (revenue, key metrics, notable guidance changes)
- Any sections that had sparse data (may indicate extraction gaps)
- Suggest the user open comparison.html and results.html in a browser to review

---

## Error Handling

- **BamSEC login required:** If the transcript download fails due to auth, tell the user to log into BamSEC in Chrome and retry.
- **Missing config quarter:** If the target quarter isn't in the config's quarters list, tell the user to add it to `config.yaml` first (with `call_date`, `reporting_quarter`, and empty `bamsec_id`/`edgar_8k_accession`).
- **Extraction prompt missing:** If `prompts/extraction_prompt.md` doesn't exist, tell the user.
- **No prior quarter:** If this is the very first quarter for a company, skip the comparison/results updates and suggest running `/earnings-comparison` to create the initial editorial page.

## Parallelization

Where possible, parallelize independent work:
- Steps 2a and 2b (transcript + EDGAR downloads) can run in parallel
- Step 5 (comparison update) and Step 6 (results update) can run in parallel after Step 4 completes
- Step 7 (index update) is fast and can run after Steps 5-6
