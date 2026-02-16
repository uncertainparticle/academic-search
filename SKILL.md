---
name: academic-research
description: Search, retrieve, and organize peer-reviewed academic literature from Semantic Scholar and PubMed. Use when asked to "find papers on [topic]", "build a literature review", "search the literature", explore citation networks, find works by a specific author, get paper recommendations, or continue a previous research session.
---

# Academic Research Skill

## Purpose

This skill enables Claude to search, retrieve, and organize peer-reviewed academic literature from **Semantic Scholar** and **PubMed** for use in writing medical research articles, literature reviews, case reports, and comparative reviews. It stores results in structured JSON session files that persist across conversations.

## When to Use This Skill

- User asks to "find papers on [topic]", "build a literature review", "search the literature"
- User is writing or editing a medical article and needs references
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

### First-Time Setup

If no API key is configured, prompt the user to either:

- Run: `export SEMANTIC_SCHOLAR_API_KEY="their_key"`
- Or create `~/.semantic_scholar_config.json`

## Execution Pattern

Always run the Python script using its installed location:

```bash
python3 ~/.claude/skills/academic-research/academic_search.py <command> <args>
```

## Core Workflows

### Workflow 1: Targeted Literature Search

When the user asks to "find papers on [topic]":

1. Run `python3 ~/.claude/skills/academic-research/academic_search.py search <query>` -- this searches BOTH Semantic Scholar and PubMed
2. Results are automatically deduplicated by DOI and merged
3. Present the summary table: title, first author, year, journal, citation count
4. Session is auto-saved to a JSON file in the working directory
5. Ask if the user wants to explore citations for any of the top papers

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

### Workflow 3: Citation Network Exploration

When the user asks "what cites this paper" or "trace citations":

1. Use `python3 ~/.claude/skills/academic-research/academic_search.py citations <paper_id> --direction citedBy` for forward citations
2. Use `python3 ~/.claude/skills/academic-research/academic_search.py citations <paper_id> --direction references` for backward references
3. Present results sorted by citation count
4. Highlight papers in the same clinical domain

### Workflow 4: Author Search

When the user asks "find papers by [author]":

1. Run `python3 ~/.claude/skills/academic-research/academic_search.py author <author name>`
2. This searches Semantic Scholar for the author and fetches their papers
3. Present the author's publication list with citation metrics

### Workflow 5: Paper Recommendations

When the user asks "find similar papers" or "what else should I read":

1. Collect Semantic Scholar paper IDs from the session or from user input
2. Run `python3 ~/.claude/skills/academic-research/academic_search.py recommend <paper_id1> <paper_id2> ...`
3. Present recommended papers with relevance context

### Workflow 6: Resume Previous Session

When the user says "continue my research on [topic]" or "load my previous search":

1. Run `python3 ~/.claude/skills/academic-research/academic_search.py session` to list available session files
2. Run `python3 ~/.claude/skills/academic-research/academic_search.py session <filepath>` to load a specific session
3. Summarize previous findings
4. Ask how to proceed

## API Rate Limiting

- **Semantic Scholar**: 1 req/sec (authenticated). The script includes `time.sleep(1.1)` between calls.
- **PubMed**: 3 req/sec without key, 10/sec with NCBI key. The script includes `time.sleep(0.35)` between calls.
- For large searches (deep lit reviews), inform the user that the process will take a moment.

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
- Always search BOTH sources and deduplicate for comprehensive results
- When deduplicating, prefer the record with more complete metadata
- Full text is NOT available through either API -- only abstracts and metadata
- Very recent publications (last 1-2 weeks) may have an indexing lag
