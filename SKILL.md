---
name: academic-research
description: Search, retrieve, organize, and verify peer-reviewed academic literature from Semantic Scholar, PubMed, and Crossref. Use when asked to "find papers on [topic]", "build a literature review", "search the literature", "verify citations", "check my references", explore citation networks, find works by a specific author, get paper recommendations, or continue a previous research session.
---

# Academic Research Skill

## CRITICAL: Invocation Rules

**ALWAYS invoke via Bash, NOT via the Skill tool sub-agent.**

```bash
python3 ~/.claude/skills/academic-research/academic_search.py <command> [args]
```

### For citation verification — use `verify`, NEVER `search`:

| Task | Correct command | Wrong command |
|------|----------------|---------------|
| Check specific known references | `verify refs.json` | `search "BRIDGE trial atrial fibrillation"` |
| Find papers on a topic | `search "antiplatelet cardiac device"` | — |

**Workflow for verify:**
1. Create a JSON file in the project directory with DOIs, titles, authors
2. Run `verify <abs_path_to_json> [--output <abs_path_to_results.json>]`
3. Parse the output report

`search` is for topic discovery only. Use `verify` or `detail` to look up specific known references by DOI or title.

---

## Purpose

This skill enables Claude to search, retrieve, organize, and **verify** peer-reviewed academic literature from **Semantic Scholar**, **PubMed**, and **Crossref** for use in writing medical research articles, literature reviews, case reports, and comparative reviews. It stores results in structured JSON session files that persist across conversations.

## When to Use This Skill

- User asks to "find papers on [topic]", "build a literature review", "search the literature"
- User is writing or editing a medical article and needs references
- User wants to **verify citations** or **check references** in an existing article
- User wants to explore citation networks (what cites a paper, what a paper cites)
- User wants to find works by a specific author or research group
- User wants paper recommendations based on seed papers
- User asks to continue a previous research session

## When NOT to Use This Skill

- Clinical decision-making or guideline lookups (use clinical tools instead)
- Searching for non-academic content (use web search)
- Drug interaction or dosing questions

## Setup

### API Key Configuration

The Semantic Scholar API key is read in this order:

1. Environment variable: `SEMANTIC_SCHOLAR_API_KEY`
2. Config file: `~/.semantic_scholar_config.json` with format: `{"api_key": "YOUR_KEY"}`

PubMed E-utilities require no API key for basic use (rate limit: 3 req/sec). For higher throughput, an optional NCBI API key can be set via the `NCBI_API_KEY` environment variable or in the same config file as `{"ncbi_api_key": "YOUR_KEY"}`.

Crossref requires no API key.

### First-Time Setup

If no Semantic Scholar API key is configured, prompt the user to either:

- Run: `export SEMANTIC_SCHOLAR_API_KEY="their_key"`
- Or create `~/.semantic_scholar_config.json`

Note: The skill degrades gracefully without a Semantic Scholar key -- search and verify still work via PubMed and Crossref. Citation counts and recommendations require Semantic Scholar.

## Execution Pattern

Always run the Python script using its installed location:

```bash
# For citation verification (PREFERRED pattern):
python3 ~/.claude/skills/academic-research/academic_search.py verify /abs/path/refs.json --output /abs/path/results.json

# For topic search:
python3 ~/.claude/skills/academic-research/academic_search.py search "query" --limit 20
```

## Core Workflows

### Workflow 1: Targeted Literature Search

When the user asks to "find papers on [topic]":

1. Run `python3 ~/.claude/skills/academic-research/academic_search.py search <query>` -- this searches BOTH Semantic Scholar and PubMed
2. Results are automatically deduplicated by DOI and merged
3. Present the summary table: title, first author, year, journal, citation count
4. Session is auto-saved to a JSON file in the working directory
5. Ask if the user wants to explore citations for any of the top papers

Optional flags:
- `--limit N` to control result count
- `--year YYYY-YYYY` to filter by year range
- `--filter therapy|diagnosis|prognosis|etiology|systematic_review` to apply PubMed clinical query hedges

### Workflow 2: Deep Literature Review

When the user asks to "build a lit review on [topic]":

1. Search broadly: `python3 ~/.claude/skills/academic-research/academic_search.py search <query> --limit 50`
2. Identify the top 15-20 most-cited papers from the results
3. For the top 5, trace forward citations: `python3 ~/.claude/skills/academic-research/academic_search.py citations <paper_id> --direction citedBy`
4. Also trace backward references: `python3 ~/.claude/skills/academic-research/academic_search.py citations <paper_id> --direction references`
5. Deduplicate the full set across all searches
6. Organize by theme/subtopic using abstracts
7. Present a structured summary grouped by theme
8. Save the full session with thematic tags

### Workflow 3: Citation Verification

When the user asks to "check my references", "verify citations", or provides a reference list:

1. Create `refs_to_verify.json` using an **absolute path** in the project working directory before running the script. Example:
   ```json
   [
     {"label": "Ref1_Author2020", "doi": "10.1234/example", "title": "...", "authors": ["Author A"], "year": 2020, "journal": "...", "volume": "10", "issue": "3", "pages": "100-110"},
     {"label": "Ref2_Smith2018", "pmid": "12345678"},
     {"label": "Ref3_Jones2022", "doi": "https://doi.org/10.5678/xyz", "title": "..."}
   ]
   ```
   - Use `label` fields (e.g. `"BC2_Douketis2015"`) to identify references in the report
   - DOIs can be provided as bare (`10.1234/abc`), with `doi:` prefix, or as full URLs — all are normalized automatically
   - Session files are saved to the current working directory; run from the project directory or use absolute paths

2. Run:
   ```bash
   python3 ~/.claude/skills/academic-research/academic_search.py verify /abs/path/refs_to_verify.json --output /abs/path/verify_results.json
   ```
   - Use `--output /abs/path/results.json` to write the structured JSON output separately from the human-readable report
   - Human-readable report always goes to stdout; `--output` cleanly separates the two streams

3. For each reference, the tool applies a **three-layer fallback**:
   - **Layer 1 — Crossref**: resolves DOI directly (authoritative DOI registry, best for volume/issue/pages)
   - **Layer 2 — Semantic Scholar**: tried automatically when Crossref fails for a DOI (catches DOI typos resolved by S2's fuzzy matching)
   - **Layer 3 — PubMed DOI field search**: `"<doi>"[doi]` query to obtain PMID when Crossref fails
   - If no identifiers: falls back to title + author bibliographic search across Crossref and PubMed

4. The tool compares manuscript fields against source-of-truth data and checks for retracted publications.

5. Parse the output report — each reference shows:
   - Status: `VERIFIED (N sources)` / `ERRORS_FOUND (N sources)` / `NOT_FOUND` / `RETRACTED`
   - Label shown alongside index: `Reference 3 [Ref3_Jones2022]: VERIFIED (2 sources)`
   - Field mismatches: `volume [XX] manuscript="373" vs source="374"`
   - Confirmed metadata: `Confirmed: Vol 373(9):823-833 | PMID: 26095867 | Authors: Douketis JD...`
   - Sources used: `Sources: Crossref, PubMed` (or `Semantic Scholar` if fallback was used)

JSON input format:
```json
[
  {"label": "BRIDGE_Douketis2015", "title": "...", "authors": ["..."], "year": 2015, "doi": "10.1056/NEJMoa1501035", "journal": "...", "volume": "373", "issue": "9", "pages": "823-833"},
  {"label": "Ref2", "doi": "10.1234/example"},
  {"label": "Ref3", "pmid": "12345678"}
]
```

Text input format: one reference per line or paragraph (DOIs and PMIDs are auto-extracted).

### Workflow 4: Citation Network Exploration

When the user asks "what cites this paper" or "trace citations":

1. Use `python3 ~/.claude/skills/academic-research/academic_search.py citations <paper_id> --direction citedBy` for forward citations
2. Use `python3 ~/.claude/skills/academic-research/academic_search.py citations <paper_id> --direction references` for backward references
3. Present results sorted by citation count
4. Highlight papers in the same clinical domain

### Workflow 5: Author Search

When the user asks "find papers by [author]":

1. Run `python3 ~/.claude/skills/academic-research/academic_search.py author <author name>`
2. Tries Semantic Scholar first; automatically falls back to PubMed if S2 is unavailable
3. Present the author's publication list with citation metrics

### Workflow 6: Paper Recommendations

When the user asks "find similar papers" or "what else should I read":

1. Collect Semantic Scholar paper IDs from the session or from user input
2. Run `python3 ~/.claude/skills/academic-research/academic_search.py recommend <paper_id1> <paper_id2> ...`
3. Present recommended papers with relevance context

### Workflow 7: Paper Details

When the user asks about a specific paper by DOI or PMID:

1. Run `python3 ~/.claude/skills/academic-research/academic_search.py detail <doi_or_pmid>`
2. Tries Semantic Scholar, falls back to Crossref (for DOIs) or PubMed (for PMIDs)
3. Returns full metadata including volume, issue, pages

### Workflow 8: Resume Previous Session

When the user says "continue my research on [topic]" or "load my previous search":

1. Run `python3 ~/.claude/skills/academic-research/academic_search.py session` to list available session files
2. Run `python3 ~/.claude/skills/academic-research/academic_search.py session <filepath>` to load a specific session
3. Summarize previous findings
4. Ask how to proceed

## API Sources

| Source | Purpose | Key Required |
|---|---|---|
| Semantic Scholar | Search, citation counts, citation graphs, author search, recommendations, DOI fallback lookup | Optional (rate-limited without) |
| PubMed | Search, clinical trial metadata, retraction checking, DOI field search | No |
| Crossref | DOI resolution, citation verification, volume/issue/pages metadata | No |

## API Rate Limiting

- **Semantic Scholar**: 1 req/sec (authenticated). The script includes `time.sleep(1.1)` between calls.
- **PubMed**: 3 req/sec without key, 10/sec with NCBI key. The script includes `time.sleep(0.35)` between calls.
- **Crossref**: No hard limit for polite requests. The script includes `time.sleep(0.1)` between calls.
- For large searches (deep lit reviews), inform the user that the process will take a moment.

## Clinical Query Filters

The `--filter` flag applies validated NLM clinical query hedges to PubMed searches:

- `therapy` -- finds randomized controlled trials and treatment studies
- `diagnosis` -- finds diagnostic accuracy and sensitivity/specificity studies
- `prognosis` -- finds prognosis, mortality, and follow-up studies
- `etiology` -- finds risk factor, cohort, and case-control studies
- `systematic_review` -- finds systematic reviews and meta-analyses

These are the "sensitive" (high-recall) versions of the NLM hedges.

## Session File Format

Session files are saved as `research_session_{topic_slug}_{date}.json` in the working directory.

```json
{
  "session_id": "uuid",
  "topic": "descriptive topic name",
  "created_at": "ISO timestamp",
  "updated_at": "ISO timestamp",
  "searches_performed": [
    {
      "source": "semantic_scholar|pubmed|both",
      "query": "...",
      "timestamp": "...",
      "result_count": 0
    }
  ],
  "papers": {
    "DOI_or_ID": {
      "title": "...",
      "authors": ["..."],
      "year": 2024,
      "journal": "...",
      "volume": "...",
      "issue": "...",
      "pages": "...",
      "doi": "...",
      "pmid": "...",
      "semantic_scholar_id": "...",
      "abstract": "...",
      "citation_count": 0,
      "source": "semantic_scholar|pubmed|both",
      "tags": ["theme1", "theme2"],
      "notes": ""
    }
  },
  "citation_graph": {
    "paper_id": {
      "cites": ["id1", "id2"],
      "cited_by": ["id3", "id4"]
    }
  }
}
```

## Output Formatting

- When presenting search results, use a concise table format
- Always include: title, first author, year, journal, citation count
- For literature reviews, organize by theme with brief narrative summaries
- Citation formatting style should match what the user specifies (AMA, Vancouver, APA, etc.) -- if not specified, ask

## Important Notes

- Semantic Scholar has stronger citation metrics and recommendation features
- PubMed has better coverage of clinical trials, case reports, and clinical medicine literature
- Crossref is the authoritative source for DOI resolution and bibliographic metadata (volume, issue, pages)
- Always search BOTH Semantic Scholar and PubMed and deduplicate for comprehensive results
- When Semantic Scholar is unavailable, the skill degrades gracefully to PubMed + Crossref
- When deduplicating, prefer the record with more complete metadata
- Full text is NOT available through any API -- only abstracts and metadata
- Very recent publications (last 1-2 weeks) may have an indexing lag
- The verify command checks for retracted publications via PubMed
- DOI typos or URL-format DOIs are automatically normalized before lookup
