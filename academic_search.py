#!/usr/bin/env python3
"""
Academic Research Skill - Semantic Scholar + PubMed Integration

Provides literature search, citation network exploration, author lookup,
paper recommendations, and persistent session management for medical
research article writing.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, date
from uuid import uuid4
import re
import glob

# =============================================================================
# Configuration
# =============================================================================

def load_config():
    """Load API keys from environment variables or config file."""
    config = {
        "s2_api_key": os.environ.get("SEMANTIC_SCHOLAR_API_KEY"),
        "ncbi_api_key": os.environ.get("NCBI_API_KEY"),
    }
    config_path = os.path.expanduser("~/.semantic_scholar_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                file_config = json.load(f)
            if not config["s2_api_key"]:
                config["s2_api_key"] = file_config.get("api_key")
            if not config["ncbi_api_key"]:
                config["ncbi_api_key"] = file_config.get("ncbi_api_key")
        except (json.JSONDecodeError, IOError):
            pass
    return config


CONFIG = load_config()

S2_BASE = "https://api.semanticscholar.org/graph/v1"
S2_REC_BASE = "https://api.semanticscholar.org/recommendations/v1"
PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

S2_PAPER_FIELDS = (
    "paperId,externalIds,title,abstract,year,venue,"
    "publicationVenue,citationCount,authors,journal,publicationDate"
)
S2_RATE_DELAY = 1.1   # seconds between Semantic Scholar requests
PM_RATE_DELAY = 0.35   # seconds between PubMed requests


# =============================================================================
# HTTP Helpers
# =============================================================================

def s2_request(url, params=None):
    """Make an authenticated GET request to Semantic Scholar API."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "AcademicResearchSkill/1.0")
    if CONFIG.get("s2_api_key"):
        req.add_header("x-api-key", CONFIG["s2_api_key"])
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        return {"error": f"HTTP {e.code}: {error_body}"}
    except Exception as e:
        return {"error": str(e)}


def s2_post(url, body, params=None):
    """Make an authenticated POST request to Semantic Scholar API."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "AcademicResearchSkill/1.0")
    if CONFIG.get("s2_api_key"):
        req.add_header("x-api-key", CONFIG["s2_api_key"])
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        return {"error": f"HTTP {e.code}: {error_body}"}
    except Exception as e:
        return {"error": str(e)}


def pubmed_request(endpoint, params):
    """Make a request to PubMed E-utilities."""
    if CONFIG.get("ncbi_api_key"):
        params["api_key"] = CONFIG["ncbi_api_key"]
    params["tool"] = "AcademicResearchSkill"
    params["email"] = "research@example.com"
    url = f"{PUBMED_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "AcademicResearchSkill/1.0")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode()
    except Exception as e:
        return f"<error>{str(e)}</error>"


# =============================================================================
# Semantic Scholar Functions
# =============================================================================

def s2_search(query, limit=20, year_range=None, fields_of_study=None):
    """Search Semantic Scholar for papers."""
    params = {
        "query": query,
        "limit": min(limit, 100),
        "fields": S2_PAPER_FIELDS,
    }
    if year_range:
        params["year"] = year_range  # e.g., "2018-2024"
    if fields_of_study:
        params["fieldsOfStudy"] = fields_of_study  # e.g., "Medicine"
    result = s2_request(f"{S2_BASE}/paper/search", params)
    if "error" in result:
        return result
    papers = [normalize_s2_paper(p) for p in result.get("data", [])]
    return {"total": result.get("total", 0), "papers": papers}


def s2_get_paper(paper_id):
    """Get detailed paper info from Semantic Scholar."""
    result = s2_request(
        f"{S2_BASE}/paper/{paper_id}", {"fields": S2_PAPER_FIELDS}
    )
    if "error" in result:
        return result
    return normalize_s2_paper(result)


def s2_get_citations(paper_id, direction="citedBy", limit=50):
    """
    Get citation graph for a paper.

    Args:
        paper_id: Semantic Scholar paper ID or DOI
        direction: 'citedBy' (papers citing this one) or 'references'
                   (papers this one cites)
        limit: Maximum number of results

    Returns:
        Dict with 'papers' list sorted by citation count descending.
    """
    # Map user-facing direction to S2 API endpoint and response key
    endpoint_map = {
        "citedBy": ("citations", "citingPaper"),
        "references": ("references", "citedPaper"),
    }
    if direction not in endpoint_map:
        return {"error": f"Invalid direction '{direction}'. Use 'citedBy' or 'references'."}

    endpoint, paper_key = endpoint_map[direction]
    fields = "paperId,externalIds,title,year,venue,citationCount,authors"
    result = s2_request(
        f"{S2_BASE}/paper/{paper_id}/{endpoint}",
        {"fields": fields, "limit": min(limit, 1000)},
    )
    if "error" in result:
        return result

    papers = []
    for item in result.get("data", []):
        p = item.get(paper_key, item)
        if p and p.get("paperId"):
            papers.append({
                "semantic_scholar_id": p.get("paperId"),
                "title": p.get("title", ""),
                "year": p.get("year"),
                "venue": p.get("venue", ""),
                "citation_count": p.get("citationCount", 0),
                "authors": [a.get("name", "") for a in p.get("authors", [])],
                "doi": (p.get("externalIds") or {}).get("DOI"),
            })
    return {
        "papers": sorted(
            papers, key=lambda x: x.get("citation_count", 0), reverse=True
        )
    }


def s2_search_author(name, limit=5):
    """Search for an author on Semantic Scholar."""
    params = {
        "query": name,
        "limit": limit,
        "fields": "authorId,name,paperCount,citationCount,hIndex",
    }
    result = s2_request(f"{S2_BASE}/author/search", params)
    if "error" in result:
        return result
    return result.get("data", [])


def s2_get_author_papers(author_id, limit=100):
    """Get all papers by an author."""
    params = {"fields": S2_PAPER_FIELDS, "limit": min(limit, 1000)}
    result = s2_request(f"{S2_BASE}/author/{author_id}/papers", params)
    if "error" in result:
        return result
    papers = [normalize_s2_paper(item) for item in result.get("data", [])]
    return {
        "papers": sorted(papers, key=lambda x: x.get("year") or 0, reverse=True)
    }


def s2_recommend(seed_paper_ids, limit=20):
    """Get paper recommendations based on seed papers."""
    body = {"positivePaperIds": seed_paper_ids}
    params = {"fields": S2_PAPER_FIELDS, "limit": limit}
    result = s2_post(f"{S2_REC_BASE}/papers/", body, params)
    if "error" in result:
        return result
    papers = [normalize_s2_paper(p) for p in result.get("recommendedPapers", [])]
    return {"papers": papers}


def normalize_s2_paper(p):
    """Normalize a Semantic Scholar paper record to a standard dict."""
    ext_ids = p.get("externalIds") or {}
    journal = p.get("journal") or {}
    pub_venue = p.get("publicationVenue") or {}
    venue_name = (
        pub_venue.get("name")
        or journal.get("name")
        or p.get("venue", "")
    )
    return {
        "semantic_scholar_id": p.get("paperId"),
        "title": p.get("title", ""),
        "authors": [a.get("name", "") for a in p.get("authors", [])],
        "year": p.get("year"),
        "journal": venue_name,
        "doi": ext_ids.get("DOI"),
        "pmid": ext_ids.get("PubMed"),
        "abstract": p.get("abstract") or "",
        "citation_count": p.get("citationCount", 0),
        "publication_date": p.get("publicationDate"),
        "source": "semantic_scholar",
    }


# =============================================================================
# PubMed Functions
# =============================================================================

def pm_search(query, limit=20, date_range=None):
    """Search PubMed and return paper metadata."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": limit,
        "retmode": "json",
        "sort": "relevance",
    }
    if date_range:
        params["mindate"] = date_range[0]
        params["maxdate"] = date_range[1]
        params["datetype"] = "pdat"

    raw = pubmed_request("esearch.fcgi", params)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return {"error": f"Failed to parse PubMed search response: {raw[:200]}"}

    id_list = result.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return {"total": 0, "papers": []}

    total = int(result.get("esearchresult", {}).get("count", 0))
    time.sleep(PM_RATE_DELAY)

    papers = pm_fetch_details(id_list)
    return {"total": total, "papers": papers}


def pm_fetch_details(pmids):
    """Fetch detailed metadata for a list of PubMed IDs."""
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(str(p) for p in pmids),
        "retmode": "xml",
    }
    raw = pubmed_request("efetch.fcgi", params)

    if raw.startswith("<error>"):
        return []

    papers = []
    try:
        root = ET.fromstring(raw)
        for article in root.findall(".//PubmedArticle"):
            papers.append(parse_pubmed_article(article))
    except ET.ParseError:
        pass

    return papers


def pm_search_author(author_name, limit=20):
    """Search PubMed for papers by a specific author."""
    query = f"{author_name}[Author]"
    return pm_search(query, limit=limit)


def parse_pubmed_article(article):
    """Parse a PubmedArticle XML element into a normalized dict."""
    medline = article.find(".//MedlineCitation")
    art = medline.find(".//Article") if medline is not None else None

    # PMID
    pmid = ""
    if medline is not None:
        pmid_elem = medline.find("PMID")
        pmid = pmid_elem.text if pmid_elem is not None else ""

    # Title
    title = ""
    if art is not None:
        title_elem = art.find("ArticleTitle")
        title = "".join(title_elem.itertext()) if title_elem is not None else ""

    # Authors
    authors = []
    if art is not None:
        for author in art.findall(".//Author"):
            last = author.find("LastName")
            fore = author.find("ForeName")
            name_parts = []
            if fore is not None and fore.text:
                name_parts.append(fore.text)
            if last is not None and last.text:
                name_parts.append(last.text)
            if name_parts:
                authors.append(" ".join(name_parts))

    # Year
    year = None
    pub_date = art.find(".//PubDate") if art is not None else None
    if pub_date is not None:
        year_elem = pub_date.find("Year")
        if year_elem is not None and year_elem.text:
            try:
                year = int(year_elem.text)
            except ValueError:
                pass
        if year is None:
            medline_date = pub_date.find("MedlineDate")
            if medline_date is not None and medline_date.text:
                match = re.search(r"(\d{4})", medline_date.text)
                if match:
                    year = int(match.group(1))

    # Journal
    journal = ""
    if art is not None:
        journal_elem = art.find(".//Journal/Title")
        if journal_elem is not None:
            journal = journal_elem.text or ""
        if not journal:
            iso = art.find(".//Journal/ISOAbbreviation")
            if iso is not None:
                journal = iso.text or ""

    # Abstract
    abstract = ""
    if art is not None:
        abs_texts = art.findall(".//Abstract/AbstractText")
        parts = []
        for at in abs_texts:
            label = at.get("Label", "")
            text = "".join(at.itertext())
            if label:
                parts.append(f"{label}: {text}")
            else:
                parts.append(text)
        abstract = " ".join(parts)

    # DOI
    doi = None
    for eid in article.findall(".//ArticleIdList/ArticleId"):
        if eid.get("IdType") == "doi":
            doi = eid.text
            break
    if not doi and art is not None:
        for eid in art.findall(".//ELocationID"):
            if eid.get("EIdType") == "doi":
                doi = eid.text
                break

    return {
        "pmid": pmid,
        "title": title,
        "authors": authors,
        "year": year,
        "journal": journal,
        "doi": doi,
        "abstract": abstract,
        "citation_count": None,  # PubMed doesn't provide this directly
        "semantic_scholar_id": None,
        "source": "pubmed",
    }


# =============================================================================
# Deduplication & Merging
# =============================================================================

def deduplicate_papers(s2_papers, pm_papers):
    """
    Merge and deduplicate papers from both sources.
    Prefers the record with more complete metadata.
    """
    merged = {}

    # Index Semantic Scholar papers by DOI, PMID, or title
    for p in s2_papers:
        key = (
            p.get("doi")
            or p.get("pmid")
            or p.get("semantic_scholar_id")
            or p.get("title", "").lower()
        )
        merged[key] = p

    # Merge PubMed papers, filling gaps in existing records
    for p in pm_papers:
        doi_key = p.get("doi")
        pmid_key = p.get("pmid")
        title_key = p.get("title", "").lower()

        existing_key = None
        for k in [doi_key, pmid_key, title_key]:
            if k and k in merged:
                existing_key = k
                break

        if existing_key:
            existing = merged[existing_key]
            for field in ["pmid", "doi", "abstract", "journal"]:
                if not existing.get(field) and p.get(field):
                    existing[field] = p[field]
            existing["source"] = "both"
        else:
            key = doi_key or pmid_key or title_key
            if key:
                merged[key] = p

    return list(merged.values())


# =============================================================================
# Session Management
# =============================================================================

def create_session(topic):
    """Create a new research session."""
    slug = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")
    today = date.today().isoformat()
    return {
        "session_id": str(uuid4()),
        "topic": topic,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "filename": f"research_session_{slug}_{today}.json",
        "searches_performed": [],
        "papers": {},
        "citation_graph": {},
    }


def save_session(session):
    """Save session to a JSON file in the current directory."""
    session["updated_at"] = datetime.now().isoformat()
    filepath = session["filename"]
    with open(filepath, "w") as f:
        json.dump(session, f, indent=2, default=str)
    return filepath


def load_session(filepath):
    """Load a session from a JSON file."""
    with open(filepath) as f:
        return json.load(f)


def add_papers_to_session(session, papers, search_query, source):
    """Add papers to session and log the search."""
    session["searches_performed"].append({
        "source": source,
        "query": search_query,
        "timestamp": datetime.now().isoformat(),
        "result_count": len(papers),
    })
    for p in papers:
        key = (
            p.get("doi")
            or p.get("pmid")
            or p.get("semantic_scholar_id")
            or p.get("title", "")
        )
        if not key:
            continue
        if key in session["papers"]:
            existing = session["papers"][key]
            for field in [
                "pmid", "doi", "abstract", "journal",
                "semantic_scholar_id", "citation_count",
            ]:
                if not existing.get(field) and p.get(field):
                    existing[field] = p[field]
            if existing.get("source") != p.get("source"):
                existing["source"] = "both"
        else:
            p.setdefault("tags", [])
            p.setdefault("notes", "")
            session["papers"][key] = p
    return session


def add_citations_to_session(session, paper_id, direction, papers):
    """Add citation graph data to session."""
    if paper_id not in session["citation_graph"]:
        session["citation_graph"][paper_id] = {"cites": [], "cited_by": []}

    key = "cited_by" if direction == "citedBy" else "cites"
    ids = [
        p.get("semantic_scholar_id") or p.get("doi") or ""
        for p in papers
        if p
    ]
    session["citation_graph"][paper_id][key] = ids
    return session


# =============================================================================
# Formatting Helpers
# =============================================================================

def format_paper_table(papers, max_papers=25):
    """Format papers as a readable text table."""
    lines = []
    header = (
        f"{'#':<4} {'Year':<6} {'Cites':<8} "
        f"{'First Author':<25} {'Title':<55} {'Journal':<30}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for i, p in enumerate(papers[:max_papers], 1):
        authors = p.get("authors", [])
        first_author = authors[0] if authors else "Unknown"
        if len(first_author) > 24:
            first_author = first_author[:22] + ".."

        title = p.get("title", "")
        if len(title) > 54:
            title = title[:52] + ".."

        journal = p.get("journal", "")
        if len(journal) > 29:
            journal = journal[:27] + ".."

        year = str(p.get("year") or "N/A")
        cites = p.get("citation_count")
        cites_str = str(cites) if cites is not None else "N/A"

        lines.append(
            f"{i:<4} {year:<6} {cites_str:<8} "
            f"{first_author:<25} {title:<55} {journal:<30}"
        )

    return "\n".join(lines)


def format_citation_ama(p, number=1):
    """Format a paper in AMA citation style."""
    authors = p.get("authors", [])
    if len(authors) > 6:
        author_str = ", ".join(authors[:3]) + ", et al"
    else:
        author_str = ", ".join(authors)
    title = p.get("title", "").rstrip(".")
    journal = p.get("journal", "")
    year = p.get("year", "")
    doi = p.get("doi", "")
    doi_str = f" doi:{doi}" if doi else ""
    return f"{number}. {author_str}. {title}. {journal}. {year}.{doi_str}"


def format_citation_vancouver(p, number=1):
    """Format a paper in Vancouver citation style."""
    authors = p.get("authors", [])
    if len(authors) > 6:
        author_str = ", ".join(authors[:6]) + ", et al"
    else:
        author_str = ", ".join(authors)
    title = p.get("title", "").rstrip(".")
    journal = p.get("journal", "")
    year = p.get("year", "")
    doi = p.get("doi", "")
    doi_str = f" doi: {doi}" if doi else ""
    return f"{number}. {author_str}. {title}. {journal}. {year}.{doi_str}"


# =============================================================================
# CLI Commands
# =============================================================================

def parse_flags(args, flags):
    """
    Extract named flags from an argument list.

    Args:
        args: List of CLI arguments.
        flags: Dict mapping flag names (e.g., '--limit') to expected type
               (str, int, or None for boolean).

    Returns:
        Tuple of (remaining_args, parsed_flags_dict).
    """
    remaining = []
    parsed = {}
    i = 0
    while i < len(args):
        if args[i] in flags:
            flag = args[i]
            expected_type = flags[flag]
            if expected_type is None:
                parsed[flag] = True
                i += 1
            elif i + 1 < len(args):
                value = args[i + 1]
                parsed[flag] = expected_type(value)
                i += 2
            else:
                print(f"Warning: {flag} requires a value")
                i += 1
        else:
            remaining.append(args[i])
            i += 1
    return remaining, parsed


def cmd_search(args):
    """Search both Semantic Scholar and PubMed."""
    word_args, flags = parse_flags(args, {"--limit": int, "--year": str})
    query = " ".join(word_args)
    if not query:
        print("Usage: academic_search.py search <query> [--limit N] [--year YYYY-YYYY]")
        return

    limit = flags.get("--limit", 20)
    year_range = flags.get("--year")

    # --- Semantic Scholar ---
    print(f"Searching Semantic Scholar for: {query}")
    s2_result = s2_search(
        query, limit=limit, year_range=year_range, fields_of_study="Medicine"
    )
    s2_papers = s2_result.get("papers", []) if "error" not in s2_result else []
    if "error" in s2_result:
        print(f"  S2 warning: {s2_result['error']}")
    print(f"  Found {len(s2_papers)} papers from Semantic Scholar")

    time.sleep(S2_RATE_DELAY)

    # --- PubMed ---
    print(f"Searching PubMed for: {query}")
    pm_date = None
    if year_range and "-" in year_range:
        parts = year_range.split("-")
        pm_date = (f"{parts[0]}/01/01", f"{parts[1]}/12/31")
    pm_result = pm_search(query, limit=limit, date_range=pm_date)
    pm_papers = pm_result.get("papers", []) if "error" not in pm_result else []
    if "error" in pm_result:
        print(f"  PM warning: {pm_result['error']}")
    print(f"  Found {len(pm_papers)} papers from PubMed")

    # --- Merge ---
    merged = deduplicate_papers(s2_papers, pm_papers)
    merged.sort(key=lambda x: x.get("citation_count") or 0, reverse=True)

    print(f"\nTotal unique papers after deduplication: {len(merged)}\n")
    print(format_paper_table(merged))

    # --- Save session ---
    session = create_session(query)
    session = add_papers_to_session(session, merged, query, "both")
    filepath = save_session(session)
    print(f"\nSession saved to: {filepath}")

    print("\n---JSON_DATA_START---")
    print(json.dumps({"merged_papers": merged, "session_file": filepath}, indent=2, default=str))
    print("---JSON_DATA_END---")


def cmd_citations(args):
    """Get forward or backward citations for a paper."""
    word_args, flags = parse_flags(args, {"--direction": str})
    if not word_args:
        print("Usage: academic_search.py citations <paper_id> [--direction citedBy|references]")
        return

    paper_id = word_args[0]
    direction = flags.get("--direction", "citedBy")

    print(f"Fetching {direction} for paper: {paper_id}")
    result = s2_get_citations(paper_id, direction=direction)

    if "error" in result:
        print(f"Error: {result['error']}")
        return

    papers = result.get("papers", [])
    print(f"Found {len(papers)} papers\n")
    print(format_paper_table(papers))

    print("\n---JSON_DATA_START---")
    print(json.dumps(result, indent=2, default=str))
    print("---JSON_DATA_END---")


def cmd_author(args):
    """Search for an author and fetch their papers."""
    name = " ".join(args)
    if not name:
        print("Usage: academic_search.py author <author name>")
        return

    print(f"Searching for author: {name}")
    authors = s2_search_author(name)

    if isinstance(authors, dict) and "error" in authors:
        print(f"Error: {authors['error']}")
        return

    if not authors:
        print("No authors found.")
        return

    for a in authors:
        print(f"\n  {a.get('name')} (ID: {a.get('authorId')})")
        print(
            f"    Papers: {a.get('paperCount', 'N/A')} | "
            f"Citations: {a.get('citationCount', 'N/A')} | "
            f"h-index: {a.get('hIndex', 'N/A')}"
        )

    print(f"\nFetching papers for top result: {authors[0].get('name')}")
    time.sleep(S2_RATE_DELAY)
    result = s2_get_author_papers(authors[0]["authorId"], limit=50)
    if "error" not in result:
        papers = result.get("papers", [])
        print(f"Found {len(papers)} papers\n")
        print(format_paper_table(papers))

    print("\n---JSON_DATA_START---")
    print(json.dumps({"authors": authors}, indent=2, default=str))
    print("---JSON_DATA_END---")


def cmd_recommend(args):
    """Get paper recommendations from seed papers."""
    if not args:
        print("Usage: academic_search.py recommend <paper_id1> [paper_id2] ...")
        return

    print(f"Getting recommendations based on {len(args)} seed paper(s)")
    result = s2_recommend(args)

    if "error" in result:
        print(f"Error: {result['error']}")
        return

    papers = result.get("papers", [])
    print(f"Found {len(papers)} recommended papers\n")
    print(format_paper_table(papers))

    print("\n---JSON_DATA_START---")
    print(json.dumps(result, indent=2, default=str))
    print("---JSON_DATA_END---")


def cmd_detail(args):
    """Get detailed metadata for a specific paper."""
    if not args:
        print("Usage: academic_search.py detail <paper_id_or_doi>")
        return

    paper_id = args[0]
    print(f"Fetching details for: {paper_id}")
    result = s2_get_paper(paper_id)

    if "error" in result:
        print(f"Error: {result['error']}")
        return

    print(f"\nTitle:    {result.get('title')}")
    print(f"Authors:  {', '.join(result.get('authors', []))}")
    print(f"Year:     {result.get('year')}")
    print(f"Journal:  {result.get('journal')}")
    print(f"Citations:{result.get('citation_count')}")
    print(f"DOI:      {result.get('doi')}")
    print(f"PMID:     {result.get('pmid')}")
    print(f"\nAbstract:\n{result.get('abstract', 'N/A')}")

    print("\n---JSON_DATA_START---")
    print(json.dumps(result, indent=2, default=str))
    print("---JSON_DATA_END---")


def cmd_session(args):
    """List or load research sessions."""
    if not args:
        sessions = sorted(glob.glob("research_session_*.json"))
        if sessions:
            print("Available sessions:")
            for s in sessions:
                try:
                    data = load_session(s)
                    paper_count = len(data.get("papers", {}))
                    print(f"  {s}  —  {data.get('topic', '?')} ({paper_count} papers)")
                except (json.JSONDecodeError, IOError):
                    print(f"  {s}  —  (could not read)")
        else:
            print("No session files found in current directory.")
        return

    filepath = args[0]
    try:
        session = load_session(filepath)
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        return
    except json.JSONDecodeError:
        print(f"Invalid JSON in: {filepath}")
        return

    print(f"Session:  {session.get('topic')}")
    print(f"Created:  {session.get('created_at')}")
    print(f"Updated:  {session.get('updated_at')}")
    print(f"Papers:   {len(session.get('papers', {}))}")
    print(f"Searches: {len(session.get('searches_performed', []))}")

    print("\n---JSON_DATA_START---")
    print(json.dumps(session, indent=2, default=str))
    print("---JSON_DATA_END---")


# =============================================================================
# Main Entry Point
# =============================================================================

COMMANDS = {
    "search": cmd_search,
    "citations": cmd_citations,
    "author": cmd_author,
    "recommend": cmd_recommend,
    "detail": cmd_detail,
    "session": cmd_session,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Academic Research Skill — Semantic Scholar + PubMed")
        print(f"\nUsage: {sys.argv[0]} <command> [args]\n")
        print("Commands:")
        print("  search <query> [--limit N] [--year YYYY-YYYY]    Search both sources")
        print("  citations <paper_id> [--direction citedBy|refs]   Citation graph")
        print("  author <name>                                     Author search")
        print("  recommend <id1> [id2] ...                         Paper recommendations")
        print("  detail <paper_id_or_doi>                          Paper details")
        print("  session [filepath]                                 Load/list sessions")
        sys.exit(1)

    cmd = sys.argv[1]
    COMMANDS[cmd](sys.argv[2:])
