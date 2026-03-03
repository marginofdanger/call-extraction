# Earnings Call Extraction

Extract structured guidance data from an earnings call transcript into a Markdown file.

**Arguments:** `$ARGUMENTS` (format: `TICKER QUARTER`, e.g., `TSM Q4_2025`)

## Instructions

1. **Parse arguments.** Split `$ARGUMENTS` into TICKER and QUARTER. If either is missing, ask the user.

2. **Load the company config** from `companies/{{TICKER}}/config.yaml`. If the file doesn't exist, tell the user to run `/earnings-setup {{TICKER}}` first.

3. **Find the quarter** in the config's `quarters` list. Extract the `call_date` and `reporting_quarter` for use in the prompt.

4. **Locate the transcript.** Look for the transcript file in this order:
   - `companies/{{TICKER}}/transcripts/{{TICKER}}_{{QUARTER}}_transcript.txt`
   - `companies/{{TICKER}}/transcripts/{{QUARTER}}_transcript.txt`
   - `companies/{{TICKER}}/transcripts/{{QUARTER}}.txt`

   If not found, tell the user where to place it.

5. **Read the extraction prompt template** from `prompts/extraction_prompt.md`.

6. **Populate the template variables:**
   - `{{company_name}}` → from config `company.name`
   - `{{ticker}}` → from config `company.ticker`
   - `{{quarter_id}}` → the QUARTER argument (e.g., Q4_2025)
   - `{{call_date}}` → from the quarter entry in config
   - `{{sector}}` → from config `company.sector`
   - `{{extraction_context}}` → from config `extraction_context`
   - `{{topic_hints}}` → format each hint as a bullet point from config `topic_hints`

7. **Read the full transcript** into context.

8. **Extract the data.** Using the populated prompt as your guide, read the full transcript and produce a structured Markdown file following the format rules in the prompt. This is the core extraction — you ARE the extractor. Read carefully, capture ALL quantitative data, separate actuals from guidance, and preserve management's exact language for qualitative assessments.

9. **Write the output** to `companies/{{TICKER}}/guidance/{{QUARTER}}_guidance.md`.

10. **Validate the extraction:**
    - Check that each `tracked_metrics` entry in the config has corresponding data in the output. Warn if any tracked metric is missing from the extraction.
    - If there's a prior quarter's guidance file, compare section headers for consistency. Note any new sections or dropped sections.
    - Report: number of sections extracted, number of bullet items, any tracked metrics that are missing.

11. **If a prior quarter exists**, briefly note what changed:
    - Which tracked metrics have different values
    - Which sections are new
    - Which sections were dropped

## Output Format

The extracted file should follow this structure exactly:

```markdown
# [Company Name] [Quarter] Earnings Call Guidance Extraction
**Call Date:** [date] | **Reporting Quarter:** [quarter description]

---

## [Quarter] Actuals (Reported)
- **Revenue:** ...
- **Gross Margin:** ...
[etc.]

### [Quarter] [Breakdown 1]
[items]

### [Quarter] [Breakdown 2]
[items]

---

## Quarterly Guidance ([Next Quarter])
- **Revenue:** ...
[etc.]

## Full Year [Year] Guidance
[items]

## Long-Term Targets
[items]

---

## [Special Topic 1]
[items]

## [Special Topic 2]
[items]
```

## Important Notes

- Extract EVERYTHING. The tracked_metrics in config only determine what shows up in the metrics card on the HTML page. The full content of every section still appears in the HTML detail page.
- Be consistent with prior quarter section titles when the same topic recurs.
- When management raises or lowers guidance, always note the prior value in parentheses.
- Q4 calls typically include full-year actuals — capture these in a separate section.
