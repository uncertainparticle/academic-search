# Academic Research Skill for Claude Code

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill that searches, retrieves, organizes, and **verifies** peer-reviewed academic literature from **Semantic Scholar**, **PubMed**, and **Crossref**. Built for writing medical research articles, literature reviews, case reports, and comparative studies.

## Features

- **Triple-source search** -- queries Semantic Scholar + PubMed, deduplicates by DOI, enriches with Crossref
- **Citation verification** -- cross-checks references against Crossref and PubMed, flags errors and retractions
- **Clinical query filters** -- NLM-validated search hedges for therapy, diagnosis, prognosis, etiology, and systematic reviews
- **Citation network exploration** -- trace forward citations and backward references
- **Author lookup** -- find researchers and their publication history (S2 with PubMed fallback)
- **Paper recommendations** -- get AI-powered recommendations based on seed papers via Semantic Scholar
- **Graceful degradation** -- works with PubMed + Crossref when Semantic Scholar is unavailable
- **Persistent sessions** -- research sessions are saved as JSON files so you can resume across conversations
- **Citation formatting** -- AMA, Vancouver, and other styles supported with volume/issue/pages
- **Retraction checking** -- flags retracted papers in verification reports
- **Zero external dependencies** -- uses only Python standard library

## Installation

Copy the skill into your Claude Code skills directory:

```bash
# Clone the repo
git clone https://github.com/uncertainparticle/academic-search.git

# Copy to Claude Code skills directory
cp -r academic-search ~/.claude/skills/academic-research
```

Or manually:

```bash
mkdir -p ~/.claude/skills/academic-research
# Copy SKILL.md and academic_search.py into that directory
```

Restart Claude Code after installing. The skill will appear automatically.

## API Key Setup

### Semantic Scholar (recommended)

The Semantic Scholar API works without a key but is rate-limited. For reliable use, get a free API key:

1. Go to [Semantic Scholar API](https://www.semanticscholar.org/product/api#api-key) and request a key
2. Configure it using **one** of these methods:

**Option A: Config file** (persistent, recommended)
```bash
echo '{"api_key": "YOUR_KEY_HERE"}' > ~/.semantic_scholar_config.json
```

**Option B: Environment variable**
```bash
export SEMANTIC_SCHOLAR_API_KEY="YOUR_KEY_HERE"
```

Add the export to your `~/.zshrc` or `~/.bashrc` to make it persistent.

### PubMed / NCBI (optional)

PubMed works without a key at 3 requests/sec. For higher throughput (10 req/sec), get a free NCBI API key:

1. Create an NCBI account at [ncbi.nlm.nih.gov](https://www.ncbi.nlm.nih.gov/account/)
2. Go to Settings > API Key Management and generate a key
3. Add it to the same config file:

```json
{
  "api_key": "YOUR_SEMANTIC_SCHOLAR_KEY",
  "ncbi_api_key": "YOUR_NCBI_KEY"
}
```

Or via environment variable: `export NCBI_API_KEY="YOUR_KEY_HERE"`

### Crossref

No API key required. The script uses Crossref's polite pool (includes a mailto in the User-Agent).

## Usage

Once installed, just talk to Claude naturally:

| What you say | What happens |
|---|---|
| "Find papers on CRISPR gene therapy" | Searches both sources, shows deduplicated results |
| "Find RCTs on naltrexone for fibromyalgia" | Search with `--filter therapy` for clinical trials |
| "Verify the references in my article" | Cross-checks each citation against Crossref + PubMed |
| "Build a literature review on checkpoint inhibitors" | Deep search with citation tracing and thematic grouping |
| "What cites this paper?" | Forward citation graph from Semantic Scholar |
| "Find papers by Jennifer Doudna" | Author search with publication list and metrics |
| "Find similar papers to these" | Recommendations based on seed papers |
| "Continue my previous research" | Reloads a saved session file |

### CLI Commands (for direct use)

The script can also be run directly:

```bash
# Search both Semantic Scholar and PubMed
python3 academic_search.py search "immunotherapy lung cancer" --limit 30

# Search with year filter
python3 academic_search.py search "CAR-T cell therapy" --year 2020-2025

# Search with clinical query filter (therapy, diagnosis, prognosis, etiology, systematic_review)
python3 academic_search.py search "naltrexone fibromyalgia" --filter therapy

# Verify citations in a reference list
python3 academic_search.py verify references.json
python3 academic_search.py verify references.txt --no-retraction-check

# Get forward citations
python3 academic_search.py citations <paper_id> --direction citedBy

# Get backward references
python3 academic_search.py citations <paper_id> --direction references

# Author search (S2 with PubMed fallback)
python3 academic_search.py author "Jennifer Doudna"

# Paper recommendations from seed papers
python3 academic_search.py recommend <paper_id_1> <paper_id_2>

# Get full paper details (S2 with Crossref/PubMed fallback)
python3 academic_search.py detail <doi_or_pmid>

# List saved research sessions
python3 academic_search.py session

# Load a specific session
python3 academic_search.py session research_session_crispr_2025-02-15.json
```

## Citation Verification

The `verify` command cross-checks references against authoritative sources:

```bash
python3 academic_search.py verify references.json
```

### Input Formats

**JSON** (structured):
```json
[
  {
    "title": "Low-dose naltrexone for fibromyalgia",
    "authors": ["Younger J", "Mackey S"],
    "year": 2009,
    "journal": "Pain Medicine",
    "doi": "10.1111/j.1526-4637.2009.00613.x",
    "volume": "10",
    "issue": "4",
    "pages": "663-672"
  }
]
```

**Text** (one reference per line):
```
1. Younger J, Mackey S. Pain Med. 2009;10(4):663-72. doi:10.1111/j.1526-4637.2009.00613.x
2. Smith A, et al. Some title. Journal. 2020;15:123-130.
```

### What It Checks

- **DOI resolution** via Crossref (the DOI registry)
- **PMID lookup** via PubMed
- **Title accuracy** (fuzzy match against source)
- **Year correctness**
- **Journal name**
- **Author verification** (first author last name, handles abbreviated and full name formats)
- **Volume, issue, pages**
- **Retraction status** via PubMed

### Output

Each reference gets a status:
- **VERIFIED** -- found in source(s), all fields match
- **ERRORS_FOUND** -- found but has field mismatches (details shown)
- **NOT_FOUND** -- not found in any source
- **RETRACTED** -- paper has been retracted

## Clinical Query Filters

The `--filter` flag applies NLM-validated search hedges to PubMed queries:

| Filter | What it finds |
|---|---|
| `therapy` | RCTs, controlled trials, treatment studies |
| `diagnosis` | Diagnostic accuracy, sensitivity/specificity studies |
| `prognosis` | Prognosis, mortality, follow-up studies |
| `etiology` | Risk factors, cohort studies, case-control studies |
| `systematic_review` | Systematic reviews, meta-analyses |

## How It Works

```
User query
    |
    v
+-------------------+     +-------------------+     +-------------------+
| Semantic Scholar   |     | PubMed (NCBI)     |     | Crossref          |
| - Paper search     |     | - E-utilities API |     | - DOI resolution  |
| - Citation graph   |     | - XML parsing     |     | - Vol/Issue/Pages |
| - Author lookup    |     | - Clinical focus  |     | - Verification    |
| - Recommendations  |     | - Retractions     |     | - Citation counts |
+-------------------+     +-------------------+     +-------------------+
    |                           |                           |
    v                           v                           v
+-----------------------------------------------------------+
| Deduplication & Merging                                   |
| - Match by DOI, PMID, or title                           |
| - Keep most complete metadata                             |
| - Merge volume/issue/pages across sources                |
+-----------------------------------------------------------+
    |
    v
+-------------------+
| Session Storage   |
| (JSON files)      |
+-------------------+
```

## Session Files

Research sessions are saved as `research_session_{topic}_{date}.json` in the working directory. They contain:

- All papers found across searches (deduplicated)
- Search history with timestamps
- Citation graph data
- User-added tags and notes

Sessions can be resumed in future conversations by asking Claude to "continue my research on [topic]".

## Rate Limits

| Source | Without key | With key |
|---|---|---|
| Semantic Scholar | Very limited | 1 req/sec |
| PubMed | 3 req/sec | 10 req/sec |
| Crossref | Unlimited (polite) | N/A |

The script handles rate limiting automatically with built-in delays.

## Limitations

- **Abstracts only** -- no API provides full-text access
- **Indexing lag** -- very recent publications (last 1-2 weeks) may not appear yet
- **Citation counts** -- PubMed does not provide citation counts directly; these come from Semantic Scholar or Crossref
- **Medicine focus** -- the default search filters to the Medicine field of study on Semantic Scholar (configurable)
- **Graceful degradation** -- when Semantic Scholar is unavailable, citation graphs and recommendations are not available, but search and verification continue via PubMed + Crossref

## Requirements

- Python 3.7+
- No external packages required (uses only standard library)

## License

MIT
