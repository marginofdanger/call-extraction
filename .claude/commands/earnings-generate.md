# Earnings Call HTML Generator

Generate HTML detail pages and comparison dashboard for a company's earnings calls.

**Argument:** `$ARGUMENTS` (ticker symbol, e.g., TSM, NVDA)

## Instructions

1. **Parse the ticker** from `$ARGUMENTS`. If empty, ask the user for a ticker.

2. **Verify prerequisites:**
   - `companies/{{TICKER}}/config.yaml` must exist. If not, tell the user to run `/earnings-setup {{TICKER}}`.
   - At least one guidance MD file must exist in `companies/{{TICKER}}/guidance/`. If none, tell the user to run `/earnings-extract {{TICKER}} QUARTER` first.

3. **Run the generator:**
   ```bash
   cd /c/Users/AdrianOw/Projects/Call-extraction && python lib/generate_company.py {{TICKER}}
   ```

4. **Report results:**
   - List all generated files (quarter HTML pages + comparison.html)
   - Note any quarters that were skipped (missing guidance files)
   - Suggest viewing the comparison page: `companies/{{TICKER}}/comparison.html`
   - Suggest viewing a specific quarter: `companies/{{TICKER}}/quarters/Q4_2025.html`

5. **If the generator fails**, read the error output and troubleshoot:
   - Missing `yaml` module → suggest `pip install pyyaml`
   - Config parse errors → check config.yaml syntax
   - Missing guidance files → list which quarters need extraction
