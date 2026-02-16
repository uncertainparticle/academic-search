# Academic Research Skill for Claude Code

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill that searches, retrieves, and organizes peer-reviewed academic literature from **Semantic Scholar** and **PubMed**. Built for writing medical research articles, literature reviews, case reports, and comparative studies.

## Features

- **Dual-source search** -- queries both Semantic Scholar and PubMed, then deduplicates by DOI
- **Citation network exploration** -- trace forward citations (who cites this paper) and backward references (what this paper cites)
- **Author lookup** -- find researchers and their publication history with h-index and citation metrics
- **Paper recommendations** -- get AI-powered recommendations based on seed papers via Semantic Scholar
- **Persistent sessions** -- research sessions are saved as JSON files so you can resume across conversations
- **Citation formatting** -- AMA, Vancouver, and other styles supported
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

## Usage

Once installed, just talk to Claude naturally:

| What you say | What happens |
|---|---|
| "Find papers on CRISPR gene therapy" | Searches both sources, shows deduplicated results |
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

# Get forward citations
python3 academic_search.py citations <paper_id> --direction citedBy

# Get backward references
python3 academic_search.py citations <paper_id> --direction references

# Author search
python3 academic_search.py author "Jennifer Doudna"

# Paper recommendations from seed papers
python3 academic_search.py recommend <paper_id_1> <paper_id_2>

# Get full paper details
python3 academic_search.py detail <paper_id_or_doi>

# List saved research sessions
python3 academic_search.py session

# Load a specific session
python3 academic_search.py session research_session_crispr_2025-02-15.json
```

## Session Files

Research sessions are saved as `research_session_{topic}_{date}.json` in the working directory. They contain:

- All papers found across searches (deduplicated)
- Search history with timestamps
- Citation graph data
- User-added tags and notes

Sessions can be resumed in future conversations by asking Claude to "continue my research on [topic]".

## How It Works

```
User query
    |
    v
+-------------------+     +-------------------+
| Semantic Scholar   |     | PubMed (NCBI)     |
| - Paper search     |     | - E-utilities API |
| - Citation graph   |     | - XML parsing     |
| - Author lookup    |     | - Clinical focus  |
| - Recommendations  |     |                   |
+-------------------+     +-------------------+
    |                           |
    v                           v
+---------------------------------------+
| Deduplication & Merging               |
| - Match by DOI, PMID, or title       |
| - Keep most complete metadata         |
| - Sort by citation count              |
+---------------------------------------+
    |
    v
+-------------------+
| Session Storage   |
| (JSON files)      |
+-------------------+
```

## Rate Limits

| Source | Without key | With key |
|---|---|---|
| Semantic Scholar | Very limited | 1 req/sec |
| PubMed | 3 req/sec | 10 req/sec |

The script handles rate limiting automatically with built-in delays.

## Limitations

- **Abstracts only** -- neither API provides full-text access
- **Indexing lag** -- very recent publications (last 1-2 weeks) may not appear yet
- **Citation counts** -- PubMed does not provide citation counts directly; these come from Semantic Scholar
- **Medicine focus** -- the default search filters to the Medicine field of study on Semantic Scholar (configurable in the script)

## Requirements

- Python 3.7+
- No external packages required (uses only standard library)

## License

MIT
