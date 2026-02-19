#!/usr/bin/env python3
"""
Academic Research Skill - Semantic Scholar + PubMed + Crossref Integration

Provides literature search, citation network exploration, author lookup,
paper recommendations, citation verification, and persistent session
management for medical research article writing.
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
import html as html_module


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
CROSSREF_BASE = "https://api.crossref.org"

S2_PAPER_FIELDS = (
    "paperId,externalIds,title,abstract,year,venue,"
    "publicationVenue,citationCount,authors,journal,publicationDate"
)
S2_RATE_DELAY = 1.1   # seconds between Semantic Scholar requests
PM_RATE_DELAY = 0.35   # seconds between PubMed requests
CR_RATE_DELAY = 0.1    # seconds between Crossref requests

# PubMed Clinical Queries search hedges (validated by NLM).
# These are the "sensitive" (high-recall) versions.
CLINICAL_QUERY_FILTERS = {
    "therapy": (
        "(randomized controlled trial[pt] OR controlled clinical trial[pt] "
        "OR randomized[tiab] OR placebo[tiab] OR drug therapy[sh] "
        "OR randomly[tiab] OR trial[tiab] OR groups[tiab]) "
        "NOT (animals[mh] NOT humans[mh])"
    ),
    "diagnosis": (
        "(sensitiv*[tiab] OR sensitivity and specificity[MeSH Terms] "
        "OR diagnos*[tiab] OR diagnosis[MeSH:noexp] "
        "OR diagnostic *[MeSH:noexp] OR diagnosis,differential[MeSH:noexp] "
        "OR diagnosis[Subheading:noexp]) "
        "NOT (animals[mh] NOT humans[mh])"
    ),
    "prognosis": (
        "(incidence[MeSH:noexp] OR mortality[MeSH Terms] "
        "OR follow up studies[MeSH:noexp] OR prognos*[tw] "
        "OR predict*[tw] OR course[tw]) "
        "NOT (animals[mh] NOT humans[mh])"
    ),
    "etiology": (
        "(risk*[tiab] OR risk*[MeSH:noexp] OR cohort studies[MeSH Terms] "
        "OR odds ratio[tw] OR relative risk[tw] "
        "OR case control*[tw]) "
        "NOT (animals[mh] NOT humans[mh])"
    ),
    "systematic_review": (
        "(systematic review[ti] OR meta-analysis[pt] OR meta-analysis[ti] "
        "OR systematic literature review[ti] "
        "OR (systematic review[tiab] AND review[pt]) "
        "OR cochrane database syst rev[ta]) "
        "NOT (animals[mh] NOT humans[mh])"
    ),
}


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


def crossref_request(url, params=None):
    """Make a GET request to Crossref API. No API key required."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    # Crossref polite pool: include mailto for priority access
    req.add_header(
        "User-Agent",
        "AcademicResearchSkill/1.0 (mailto:research@example.com)",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        return {"error": f"HTTP {e.code}: {error_body}"}
    except Exception as e:
        return {"error": str(e)}


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
        params["year"] = year_range
    if fields_of_study:
        params["fieldsOfStudy"] = fields_of_study
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
    """Get citation graph for a paper."""
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
        "volume": journal.get("volume"),
        "issue": None,
        "pages": journal.get("pages"),
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


def pm_check_retractions(pmids):
    """Check which PMIDs correspond to retracted publications.

    Returns a set of PMIDs that have been retracted.
    """
    if not pmids:
        return set()

    params = {
        "db": "pubmed",
        "id": ",".join(str(p) for p in pmids),
        "retmode": "xml",
    }
    raw = pubmed_request("efetch.fcgi", params)
    if raw.startswith("<error>"):
        return set()

    retracted = set()
    try:
        root = ET.fromstring(raw)
        for article in root.findall(".//PubmedArticle"):
            pmid_elem = article.find(".//MedlineCitation/PMID")
            if pmid_elem is None:
                continue
            pmid = pmid_elem.text

            # Check PublicationTypeList for "Retracted Publication"
            for pub_type in article.findall(
                ".//Article/PublicationTypeList/PublicationType"
            ):
                if pub_type.text and "retracted publication" in pub_type.text.lower():
                    retracted.add(pmid)
                    break

            # Also check CommentsCorrections for RetractionIn
            if pmid not in retracted:
                for cc in article.findall(
                    ".//MedlineCitation/CommentsCorrectionsList/CommentsCorrections"
                ):
                    if cc.get("RefType") == "RetractionIn":
                        retracted.add(pmid)
                        break
    except ET.ParseError:
        pass

    return retracted


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

    # Volume, Issue, Pages
    volume = None
    issue = None
    pages = None
    if art is not None:
        vol_elem = art.find(".//Journal/JournalIssue/Volume")
        if vol_elem is not None and vol_elem.text:
            volume = vol_elem.text
        iss_elem = art.find(".//Journal/JournalIssue/Issue")
        if iss_elem is not None and iss_elem.text:
            issue = iss_elem.text
        pgn_elem = art.find(".//Pagination/MedlinePgn")
        if pgn_elem is not None and pgn_elem.text:
            pages = pgn_elem.text

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
        "volume": volume,
        "issue": issue,
        "pages": pages,
        "doi": doi,
        "abstract": abstract,
        "citation_count": None,
        "semantic_scholar_id": None,
        "source": "pubmed",
    }


# =============================================================================
# Crossref Functions
# =============================================================================

def normalize_doi(doi):
    """Normalize a DOI string: strip URL prefix, doi: prefix, trailing punct."""
    doi = doi.strip().rstrip(".,;)")
    doi = re.sub(r'^https?://doi\.org/', '', doi, flags=re.IGNORECASE)
    doi = re.sub(r'^doi:\s*', '', doi, flags=re.IGNORECASE).strip()
    return doi


def crossref_resolve_doi(doi):
    """Resolve a DOI via Crossref and return normalized metadata."""
    doi = normalize_doi(doi)
    encoded = urllib.parse.quote(doi, safe="")
    result = crossref_request(f"{CROSSREF_BASE}/works/{encoded}")
    if "error" in result:
        return result
    item = result.get("message", {})
    return normalize_crossref_paper(item)


def crossref_search(query, limit=5):
    """Search Crossref by bibliographic query string."""
    params = {
        "query.bibliographic": query,
        "rows": min(limit, 20),
    }
    result = crossref_request(f"{CROSSREF_BASE}/works", params)
    if "error" in result:
        return result
    items = result.get("message", {}).get("items", [])
    return {"papers": [normalize_crossref_paper(item) for item in items]}


def normalize_crossref_paper(item):
    """Normalize a Crossref work record to a standard dict."""
    authors = []
    for a in item.get("author", []):
        given = a.get("given", "")
        family = a.get("family", "")
        name = f"{given} {family}".strip()
        if name:
            authors.append(name)

    year = None
    for date_field in ["published-print", "published-online", "issued"]:
        parts = item.get(date_field, {}).get("date-parts", [[]])
        if parts and parts[0] and parts[0][0]:
            year = parts[0][0]
            break

    titles = item.get("title", [])
    title = html_module.unescape(titles[0]) if titles else ""

    containers = item.get("container-title", [])
    journal = html_module.unescape(containers[0]) if containers else ""

    return {
        "doi": item.get("DOI"),
        "title": title,
        "authors": authors,
        "year": year,
        "journal": journal,
        "volume": item.get("volume"),
        "issue": item.get("issue"),
        "pages": item.get("page"),
        "publisher": item.get("publisher"),
        "type": item.get("type"),
        "pmid": None,
        "abstract": "",
        "citation_count": item.get("is-referenced-by-count"),
        "semantic_scholar_id": None,
        "source": "crossref",
    }


# =============================================================================
# Text Similarity (for citation verification)
# =============================================================================

def _normalize_text(s):
    """Normalize text for comparison: decode HTML, normalize dashes/quotes."""
    s = html_module.unescape(s)
    # Normalize various Unicode hyphens/dashes to ASCII hyphen
    s = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", s)
    # Normalize various Unicode quotes to ASCII
    s = re.sub(r"[\u2018\u2019\u201C\u201D]", "'", s)
    return s


def token_similarity(a, b):
    """Compute Jaccard similarity on lowercased word tokens."""
    if not a or not b:
        return 0.0
    a = _normalize_text(a)
    b = _normalize_text(b)
    tokens_a = set(re.findall(r"\w+", a.lower()))
    tokens_b = set(re.findall(r"\w+", b.lower()))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _extract_last_name(name):
    """Extract last name from various author name formats.

    Handles: 'Last First' (Younger Jarred), 'First Last' (Jarred Younger),
    'Last FI' (Younger J), 'Last, First' (Younger, Jarred),
    single-token initials like 'J' or 'JM'.
    """
    if not name:
        return ""
    name = name.strip()
    # "Last, First" format
    if "," in name:
        return name.split(",")[0].strip().lower()
    parts = name.split()
    if len(parts) == 1:
        return parts[0].lower()
    # If last token is a short initial (1-2 chars, all uppercase or single letter),
    # then the name is in "Last Initial" format
    last_token = parts[-1]
    if len(last_token) <= 2 and last_token.replace(".", "").isalpha():
        return parts[0].lower()
    # If first token is a short initial, name is in "Initial Last" format
    first_token = parts[0]
    if len(first_token) <= 2 and first_token.replace(".", "").isalpha():
        return parts[-1].lower()
    # Default: assume "First Last" format
    return parts[-1].lower()


def normalize_string(s):
    """Lowercase and strip punctuation for comparison."""
    if not s:
        return ""
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


# =============================================================================
# Reference Text Parser (for verify command)
# =============================================================================

def parse_reference_text(text):
    """Extract structured fields from a raw reference string.

    Handles common citation formats (AMA, Vancouver, APA, numbered).
    Returns a dict with whatever fields can be extracted.
    """
    ref = {"raw": text.strip()}

    # Strip leading reference numbers: "1. ", "1) ", "[1] "
    cleaned = re.sub(r"^\s*\[?\d+[\].)]\s*", "", text)

    # Extract DOI (handles doi:, doi.org URLs, and bare 10.xxxx)
    doi_match = re.search(
        r"(?:https?://doi\.org/|doi[:\s]*)(10\.\d{4,}/[^\s,;\"]+)",
        cleaned,
        re.IGNORECASE,
    )
    if not doi_match:
        doi_match = re.search(r"\b(10\.\d{4,}/[^\s,;\"]+)", cleaned)
    if doi_match:
        doi = doi_match.group(1).rstrip(".")
        ref["doi"] = doi

    # Extract PMID
    pmid_match = re.search(r"PMID[:\s]*(\d+)", cleaned, re.IGNORECASE)
    if pmid_match:
        ref["pmid"] = pmid_match.group(1)

    # Extract year (prefer parenthesized year, then freestanding)
    year_match = re.search(r"\((\d{4})\)", cleaned)
    if not year_match:
        year_match = re.search(r"[\.\s;,](\d{4})[\.\s;,]", cleaned)
    if year_match:
        y = int(year_match.group(1))
        if 1900 <= y <= 2100:
            ref["year"] = y

    # Extract volume(issue):pages pattern: e.g., "10(4):663-72" or "15:123-130"
    vip_match = re.search(r"(\d+)\((\d+)\)[:\s]*(\d+[\-\u2013]\d+)", cleaned)
    if vip_match:
        ref["volume"] = vip_match.group(1)
        ref["issue"] = vip_match.group(2)
        ref["pages"] = vip_match.group(3)
    else:
        vp_match = re.search(r";(\d+)[:\s]+(\d+[\-\u2013]\d+)", cleaned)
        if vp_match:
            ref["volume"] = vp_match.group(1)
            ref["pages"] = vp_match.group(2)

    return ref


def load_references_file(filepath):
    """Load references from a JSON or text file.

    JSON format: array of dicts with any subset of standard fields.
    Text format: one reference per line (or per paragraph).

    Returns a list of reference dicts.
    """
    with open(filepath) as f:
        content = f.read().strip()

    # Try JSON first
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "references" in data:
            return data["references"]
    except json.JSONDecodeError:
        pass

    # Parse as text: split on blank lines or numbered lines
    refs = []
    lines = content.split("\n")
    current = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                refs.append(parse_reference_text(" ".join(current)))
                current = []
        elif re.match(r"^\s*\[?\d+[\].)]\s+", stripped) and current:
            refs.append(parse_reference_text(" ".join(current)))
            current = [stripped]
        else:
            current.append(stripped)
    if current:
        refs.append(parse_reference_text(" ".join(current)))

    return refs


# =============================================================================
# Deduplication & Merging
# =============================================================================

MERGE_FIELDS = [
    "pmid", "doi", "abstract", "journal",
    "volume", "issue", "pages", "semantic_scholar_id", "citation_count",
]


def deduplicate_papers(s2_papers, pm_papers):
    """Merge and deduplicate papers from both sources.

    Prefers the record with more complete metadata.
    """
    merged = {}

    for p in s2_papers:
        key = (
            p.get("doi")
            or p.get("pmid")
            or p.get("semantic_scholar_id")
            or p.get("title", "").lower()
        )
        merged[key] = p

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
            for field in MERGE_FIELDS:
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
            for field in MERGE_FIELDS:
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


def _format_vol_issue_pages(p):
    """Build the ;Volume(Issue):Pages suffix for citation strings."""
    parts = []
    vol = p.get("volume")
    iss = p.get("issue")
    pgs = p.get("pages")
    if vol:
        s = vol
        if iss:
            s += f"({iss})"
        parts.append(s)
    if pgs:
        parts.append(pgs)
    if not parts:
        return ""
    if vol and pgs:
        return f";{vol}{'(' + iss + ')' if iss else ''}:{pgs}"
    if vol:
        return f";{vol}{'(' + iss + ')' if iss else ''}"
    return f":{pgs}" if pgs else ""


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
    vip = _format_vol_issue_pages(p)
    doi = p.get("doi", "")
    doi_str = f" doi:{doi}" if doi else ""
    return f"{number}. {author_str}. {title}. {journal}. {year}{vip}.{doi_str}"


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
    vip = _format_vol_issue_pages(p)
    doi = p.get("doi", "")
    doi_str = f" doi: {doi}" if doi else ""
    return f"{number}. {author_str}. {title}. {journal}. {year}{vip}.{doi_str}"


# =============================================================================
# Citation Verification Engine
# =============================================================================

def verify_single_reference(ref, index):
    """Verify a single reference against Crossref and PubMed.

    Returns a verification result dict with status, sources found,
    field comparisons, and retraction status.
    """
    result = {
        "index": index,
        "input": ref,
        "status": "NOT_FOUND",
        "sources": {},
        "field_checks": {},
        "retracted": False,
        "best_match": None,
    }

    doi = ref.get("doi")
    if doi:
        doi = normalize_doi(doi)
    pmid = ref.get("pmid")

    # --- Resolve via DOI (Crossref) ---
    if doi:
        time.sleep(CR_RATE_DELAY)
        cr_paper = crossref_resolve_doi(doi)
        if "error" not in cr_paper:
            result["sources"]["crossref"] = cr_paper
        else:
            result["sources"]["crossref_error"] = cr_paper["error"]

    # Fallback: Semantic Scholar DOI lookup when Crossref fails
    if doi and not result["sources"].get("crossref"):
        time.sleep(S2_RATE_DELAY)
        s2_paper = s2_get_paper(f"DOI:{doi}")
        if "error" not in s2_paper and s2_paper.get("title"):
            result["sources"]["semantic_scholar"] = s2_paper

    # Fallback: PubMed DOI search to obtain PMID when Crossref fails
    if doi and not result["sources"].get("pubmed"):
        time.sleep(PM_RATE_DELAY)
        pm_doi = pm_search(f'"{doi}"[doi]', limit=1)
        if pm_doi.get("papers"):
            result["sources"]["pubmed"] = pm_doi["papers"][0]

    # --- Resolve via PMID (PubMed) ---
    if pmid:
        time.sleep(PM_RATE_DELAY)
        pm_papers = pm_fetch_details([pmid])
        if pm_papers:
            result["sources"]["pubmed"] = pm_papers[0]

    # --- Fallback search if no identifiers resolved ---
    if not result["sources"].get("crossref") and not result["sources"].get("pubmed"):
        search_parts = []
        if ref.get("title"):
            search_parts.append(ref["title"])
        elif ref.get("raw"):
            # Use the raw text minus DOI/PMID patterns
            raw_clean = re.sub(
                r"(?:doi[:\s]*)?10\.\d{4,}/\S+", "", ref.get("raw", ""), flags=re.IGNORECASE
            )
            raw_clean = re.sub(r"PMID[:\s]*\d+", "", raw_clean, flags=re.IGNORECASE)
            search_parts.append(raw_clean.strip())
        if ref.get("authors"):
            if isinstance(ref["authors"], list) and ref["authors"]:
                search_parts.append(ref["authors"][0])
            elif isinstance(ref["authors"], str):
                search_parts.append(ref["authors"])

        query = " ".join(search_parts).strip()
        if query:
            # Try Crossref bibliographic search
            time.sleep(CR_RATE_DELAY)
            cr_results = crossref_search(query, limit=3)
            if "error" not in cr_results:
                for candidate in cr_results.get("papers", []):
                    sim = token_similarity(
                        ref.get("title") or ref.get("raw", ""),
                        candidate.get("title", ""),
                    )
                    if sim > 0.5:
                        result["sources"]["crossref"] = candidate
                        break

            # Try PubMed search
            if not result["sources"].get("pubmed"):
                time.sleep(PM_RATE_DELAY)
                pm_results = pm_search(query, limit=3)
                if "error" not in pm_results:
                    for candidate in pm_results.get("papers", []):
                        sim = token_similarity(
                            ref.get("title") or ref.get("raw", ""),
                            candidate.get("title", ""),
                        )
                        if sim > 0.5:
                            result["sources"]["pubmed"] = candidate
                            break

    # --- Pick best match for comparison ---
    # Prefer PubMed (more authoritative for biomedical), fall back to Crossref, then S2
    best = (result["sources"].get("pubmed")
            or result["sources"].get("crossref")
            or result["sources"].get("semantic_scholar"))
    if not best:
        result["status"] = "NOT_FOUND"
        return result

    result["best_match"] = best
    source_count = sum(
        1 for k in ("crossref", "pubmed", "semantic_scholar") if result["sources"].get(k)
    )

    # --- Field-by-field comparison ---
    checks = {}
    has_error = False

    # Title
    if ref.get("title") and best.get("title"):
        sim = token_similarity(ref["title"], best["title"])
        match = sim > 0.7
        checks["title"] = {
            "status": "match" if match else "mismatch",
            "similarity": round(sim, 2),
            "manuscript": ref["title"],
            "source": best["title"],
        }
        if not match:
            has_error = True

    # Year
    if ref.get("year") and best.get("year"):
        match = str(ref["year"]) == str(best["year"])
        checks["year"] = {
            "status": "match" if match else "mismatch",
            "manuscript": ref["year"],
            "source": best["year"],
        }
        if not match:
            has_error = True

    # Journal
    if ref.get("journal") and best.get("journal"):
        sim = token_similarity(ref["journal"], best["journal"])
        match = sim > 0.5  # journals often abbreviated differently
        checks["journal"] = {
            "status": "match" if match else "mismatch",
            "similarity": round(sim, 2),
            "manuscript": ref["journal"],
            "source": best["journal"],
        }
        if not match:
            has_error = True

    # Authors (compare first author last name)
    if ref.get("authors") and best.get("authors"):
        ref_authors = ref["authors"]
        if isinstance(ref_authors, str):
            ref_authors = [ref_authors]
        best_authors = best.get("authors", [])
        if ref_authors and best_authors:
            ref_first_last = _extract_last_name(ref_authors[0]) if ref_authors[0] else ""
            best_first_last = _extract_last_name(best_authors[0]) if best_authors[0] else ""
            match = ref_first_last == best_first_last
            checks["first_author"] = {
                "status": "match" if match else "mismatch",
                "manuscript": ref_authors[0] if ref_authors else "",
                "source": best_authors[0] if best_authors else "",
            }
            if not match:
                has_error = True

    # Volume
    if ref.get("volume") and best.get("volume"):
        match = str(ref["volume"]) == str(best["volume"])
        checks["volume"] = {
            "status": "match" if match else "mismatch",
            "manuscript": ref["volume"],
            "source": best["volume"],
        }
        if not match:
            has_error = True

    # Issue
    if ref.get("issue") and best.get("issue"):
        match = str(ref["issue"]) == str(best["issue"])
        checks["issue"] = {
            "status": "match" if match else "mismatch",
            "manuscript": ref["issue"],
            "source": best["issue"],
        }
        if not match:
            has_error = True

    # Pages
    if ref.get("pages") and best.get("pages"):
        # Normalize en-dash to hyphen for comparison
        ref_pages = str(ref["pages"]).replace("\u2013", "-")
        src_pages = str(best["pages"]).replace("\u2013", "-")
        match = ref_pages == src_pages
        checks["pages"] = {
            "status": "match" if match else "mismatch",
            "manuscript": ref["pages"],
            "source": best["pages"],
        }
        if not match:
            has_error = True

    # DOI cross-check (use normalized doi for comparison)
    if doi and best.get("doi"):
        match = doi.lower() == best["doi"].lower()
        checks["doi"] = {
            "status": "match" if match else "mismatch",
            "manuscript": doi,
            "source": best["doi"],
        }
        if not match:
            has_error = True

    result["field_checks"] = checks
    if has_error:
        result["status"] = f"ERRORS_FOUND ({source_count} source{'s' if source_count > 1 else ''})"
    else:
        result["status"] = f"VERIFIED ({source_count} source{'s' if source_count > 1 else ''})"

    return result


def format_verification_report(results, retracted_pmids):
    """Format verification results as a human-readable report."""
    lines = []
    lines.append("=" * 72)
    lines.append("CITATION VERIFICATION REPORT")
    lines.append("=" * 72)

    verified = 0
    errors = 0
    not_found = 0
    retraction_count = 0

    for r in results:
        idx = r["index"]
        ref = r["input"]
        title = ref.get("title") or ref.get("raw", "")[:70] or "(no title)"
        if len(title) > 70:
            title = title[:68] + ".."

        # Check retraction
        best = r.get("best_match") or {}
        ref_pmid = ref.get("pmid") or best.get("pmid")
        is_retracted = ref_pmid and str(ref_pmid) in retracted_pmids

        label = ref.get("label")
        label_str = f" [{label}]" if label else ""
        lines.append("")
        if is_retracted:
            lines.append(f"Reference {idx}{label_str}: *** RETRACTED ***")
            retraction_count += 1
        elif r["status"].startswith("VERIFIED"):
            lines.append(f"Reference {idx}{label_str}: {r['status']}")
            verified += 1
        elif r["status"].startswith("ERRORS"):
            lines.append(f"Reference {idx}{label_str}: {r['status']}")
            errors += 1
        else:
            lines.append(f"Reference {idx}{label_str}: NOT FOUND")
            not_found += 1

        lines.append(f"  Title:  {title}")

        # Show field checks
        for field, check in r.get("field_checks", {}).items():
            status_mark = "OK" if check["status"] == "match" else "XX"
            if check["status"] == "mismatch":
                lines.append(
                    f"  {field:<14} [{status_mark}] "
                    f"manuscript=\"{check['manuscript']}\" vs source=\"{check['source']}\""
                )
            else:
                lines.append(f"  {field:<14} [{status_mark}]")

        # Show confirmed metadata from best match
        if r.get("best_match"):
            bm = r["best_match"]
            parts = []
            vol = bm.get("volume")
            issue = bm.get("issue")
            pages = bm.get("pages")
            if vol or issue or pages:
                vip = f"Vol {vol}" if vol else ""
                if issue:
                    vip += f"({issue})" if vip else f"Issue {issue}"
                if pages:
                    vip += f":{pages}" if vip else pages
                parts.append(vip)
            if bm.get("pmid"):
                parts.append(f"PMID: {bm['pmid']}")
            authors = bm.get("authors", [])
            if authors:
                parts.append(f"Authors: {', '.join(str(a) for a in authors[:3])}")
            if parts:
                lines.append(f"  Confirmed:  {' | '.join(parts)}")

        # Show which sources found it
        sources_found = []
        if r["sources"].get("crossref"):
            sources_found.append("Crossref")
        if r["sources"].get("pubmed"):
            sources_found.append("PubMed")
        if r["sources"].get("semantic_scholar"):
            sources_found.append("Semantic Scholar")
        if sources_found:
            lines.append(f"  Sources: {', '.join(sources_found)}")
        elif r["sources"].get("crossref_error"):
            lines.append(f"  Crossref: {r['sources']['crossref_error']}")

        if is_retracted:
            lines.append(f"  *** WARNING: This paper has been RETRACTED (PMID: {ref_pmid}) ***")

    lines.append("")
    lines.append("=" * 72)
    lines.append("SUMMARY")
    lines.append(f"  Total references:  {len(results)}")
    lines.append(f"  Verified:          {verified}")
    lines.append(f"  Errors found:      {errors}")
    lines.append(f"  Not found:         {not_found}")
    if retraction_count:
        lines.append(f"  RETRACTED:         {retraction_count}")
    lines.append("=" * 72)

    return "\n".join(lines)


# =============================================================================
# CLI Commands
# =============================================================================

def parse_flags(args, flags):
    """Extract named flags from an argument list."""
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
    word_args, flags = parse_flags(
        args, {"--limit": int, "--year": str, "--filter": str}
    )
    query = " ".join(word_args)
    if not query:
        print(
            "Usage: academic_search.py search <query> "
            "[--limit N] [--year YYYY-YYYY] [--filter therapy|diagnosis|prognosis|etiology|systematic_review]"
        )
        return

    limit = flags.get("--limit", 20)
    year_range = flags.get("--year")
    cq_filter = flags.get("--filter")

    if cq_filter and cq_filter not in CLINICAL_QUERY_FILTERS:
        print(
            f"Unknown filter '{cq_filter}'. "
            f"Available: {', '.join(CLINICAL_QUERY_FILTERS.keys())}"
        )
        return

    # --- Semantic Scholar ---
    print(f"Searching Semantic Scholar for: {query}")
    s2_result = s2_search(
        query, limit=limit, year_range=year_range, fields_of_study="Medicine"
    )
    s2_papers = s2_result.get("papers", []) if "error" not in s2_result else []
    if "error" in s2_result:
        print(f"  S2 warning: {s2_result['error']}")
        if not s2_papers:
            print("  Running in PubMed-only mode. Citation counts unavailable.")
    print(f"  Found {len(s2_papers)} papers from Semantic Scholar")

    time.sleep(S2_RATE_DELAY)

    # --- PubMed ---
    pm_query = query
    if cq_filter:
        hedge = CLINICAL_QUERY_FILTERS[cq_filter]
        pm_query = f"({query}) AND {hedge}"
        print(f"Searching PubMed for: {query} [filter: {cq_filter}]")
    else:
        print(f"Searching PubMed for: {query}")

    pm_date = None
    if year_range and "-" in year_range:
        parts = year_range.split("-")
        pm_date = (f"{parts[0]}/01/01", f"{parts[1]}/12/31")
    pm_result = pm_search(pm_query, limit=limit, date_range=pm_date)
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
    print(json.dumps(
        {"merged_papers": merged, "session_file": filepath},
        indent=2, default=str,
    ))
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
    """Search for an author and fetch their papers.

    Tries Semantic Scholar first; falls back to PubMed if S2 fails.
    """
    name = " ".join(args)
    if not name:
        print("Usage: academic_search.py author <author name>")
        return

    print(f"Searching for author: {name}")
    authors = s2_search_author(name)

    s2_ok = not (isinstance(authors, dict) and "error" in authors) and authors

    if s2_ok:
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

    else:
        # Fallback to PubMed author search
        if isinstance(authors, dict) and "error" in authors:
            print(f"  S2 warning: {authors['error']}")
        print(f"  Falling back to PubMed author search...")
        pm_result = pm_search_author(name, limit=30)
        pm_papers = pm_result.get("papers", []) if "error" not in pm_result else []
        if "error" in pm_result:
            print(f"  PM warning: {pm_result['error']}")

        if pm_papers:
            print(f"Found {len(pm_papers)} papers by {name} on PubMed\n")
            print(format_paper_table(pm_papers))
        else:
            print("No papers found.")

        print("\n---JSON_DATA_START---")
        print(json.dumps(
            {"source": "pubmed_fallback", "papers": pm_papers},
            indent=2, default=str,
        ))
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
    """Get detailed metadata for a specific paper.

    Tries Semantic Scholar first; falls back to PubMed/Crossref if S2 fails.
    """
    if not args:
        print("Usage: academic_search.py detail <paper_id_or_doi_or_pmid>")
        return

    paper_id = args[0]
    print(f"Fetching details for: {paper_id}")

    result = None

    # Try Semantic Scholar
    s2_result = s2_get_paper(paper_id)
    if "error" not in s2_result:
        result = s2_result
    else:
        print(f"  S2 warning: {s2_result['error']}")

    # Fallback: if input looks like a DOI, try Crossref
    if result is None and re.match(r"10\.\d{4,}/", paper_id):
        print("  Trying Crossref...")
        time.sleep(CR_RATE_DELAY)
        cr_result = crossref_resolve_doi(paper_id)
        if "error" not in cr_result:
            result = cr_result

    # Fallback: if input looks like a PMID, try PubMed
    if result is None and paper_id.isdigit():
        print("  Trying PubMed...")
        time.sleep(PM_RATE_DELAY)
        pm_papers = pm_fetch_details([paper_id])
        if pm_papers:
            result = pm_papers[0]

    # Fallback: try as DOI via S2 prefix
    if result is None and not paper_id.startswith("DOI:"):
        s2_doi = s2_get_paper(f"DOI:{paper_id}")
        if "error" not in s2_doi:
            result = s2_doi

    if result is None:
        print("Error: Paper not found in any source.")
        return

    print(f"\nTitle:    {result.get('title')}")
    print(f"Authors:  {', '.join(result.get('authors', []))}")
    print(f"Year:     {result.get('year')}")
    print(f"Journal:  {result.get('journal')}")
    print(f"Volume:   {result.get('volume', 'N/A')}")
    print(f"Issue:    {result.get('issue', 'N/A')}")
    print(f"Pages:    {result.get('pages', 'N/A')}")
    print(f"Citations:{result.get('citation_count')}")
    print(f"DOI:      {result.get('doi')}")
    print(f"PMID:     {result.get('pmid')}")
    print(f"Source:   {result.get('source')}")
    print(f"\nAbstract:\n{result.get('abstract', 'N/A')}")

    print("\n---JSON_DATA_START---")
    print(json.dumps(result, indent=2, default=str))
    print("---JSON_DATA_END---")


def cmd_verify(args):
    """Verify citations in a reference list against Crossref and PubMed.

    Accepts a JSON or text file of references. For each reference:
    1. Looks it up by DOI (Crossref), PMID (PubMed), or title search
    2. Compares manuscript fields against authoritative sources
    3. Checks for retractions
    4. Reports per-reference verification status
    """
    word_args, flags = parse_flags(args, {"--no-retraction-check": None, "--output": str})
    if not word_args:
        print(
            "Usage: academic_search.py verify <references_file.json|.txt> "
            "[--output <file.json>] [--no-retraction-check]"
        )
        print("\nJSON format: [{\"title\": \"...\", \"doi\": \"...\", ...}, ...]")
        print("Text format: one reference per line or per paragraph")
        return

    filepath = word_args[0]
    check_retractions = not flags.get("--no-retraction-check", False)

    try:
        refs = load_references_file(filepath)
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        return
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    if not refs:
        print("No references found in file.")
        return

    print(f"Loaded {len(refs)} references from {filepath}")
    print(f"Verifying against Crossref + PubMed...\n")

    results = []
    for i, ref in enumerate(refs, 1):
        title_preview = (ref.get("title") or ref.get("raw", ""))[:50]
        print(f"  [{i}/{len(refs)}] Checking: {title_preview}...")
        vr = verify_single_reference(ref, i)
        results.append(vr)

    # Batch retraction check for all PMIDs found
    retracted_pmids = set()
    if check_retractions:
        all_pmids = set()
        for r in results:
            for source_key in ("pubmed", "crossref"):
                paper = r["sources"].get(source_key)
                if paper and paper.get("pmid"):
                    all_pmids.add(str(paper["pmid"]))
            ref = r["input"]
            if ref.get("pmid"):
                all_pmids.add(str(ref["pmid"]))

        if all_pmids:
            print(f"\nChecking {len(all_pmids)} PMIDs for retractions...")
            time.sleep(PM_RATE_DELAY)
            retracted_pmids = pm_check_retractions(list(all_pmids))
            if retracted_pmids:
                print(f"  Found {len(retracted_pmids)} retracted paper(s)!")

    # Print report
    print("\n" + format_verification_report(results, retracted_pmids))

    # JSON output
    json_results = []
    for r in results:
        jr = {
            "index": r["index"],
            "label": r["input"].get("label"),
            "status": r["status"],
            "input": r["input"],
            "field_checks": r["field_checks"],
            "sources_found": list(
                k for k in ("crossref", "pubmed", "semantic_scholar") if r["sources"].get(k)
            ),
            "best_match": r.get("best_match"),
        }
        best = r.get("best_match") or {}
        ref_pmid = r["input"].get("pmid") or best.get("pmid")
        if ref_pmid and str(ref_pmid) in retracted_pmids:
            jr["retracted"] = True
            jr["status"] = "RETRACTED"
        json_results.append(jr)
    json_blob = json.dumps(
        {"verification_results": json_results, "total": len(refs)},
        indent=2, default=str,
    )
    output_file = flags.get("--output")
    if output_file:
        with open(output_file, "w") as f:
            f.write(json_blob)
        print(f"\nJSON results written to: {output_file}")
    else:
        print("\n---JSON_DATA_START---")
        print(json_blob)
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
                    print(f"  {s}  --  {data.get('topic', '?')} ({paper_count} papers)")
                except (json.JSONDecodeError, IOError):
                    print(f"  {s}  --  (could not read)")
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
    "verify": cmd_verify,
    "session": cmd_session,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Academic Research Skill -- Semantic Scholar + PubMed + Crossref")
        print(f"\nUsage: {sys.argv[0]} <command> [args]\n")
        print("Commands:")
        print("  search <query> [--limit N] [--year YYYY-YYYY] [--filter TYPE]")
        print("         Search both sources. Filters: therapy, diagnosis, prognosis, etiology, systematic_review")
        print("  verify <refs_file> [--output <file.json>] [--no-retraction-check]")
        print("         Verify citations against Crossref + Semantic Scholar + PubMed")
        print("  citations <paper_id> [--direction citedBy|references]")
        print("         Citation graph (Semantic Scholar)")
        print("  author <name>")
        print("         Author search (S2 with PubMed fallback)")
        print("  recommend <id1> [id2] ...")
        print("         Paper recommendations (Semantic Scholar)")
        print("  detail <paper_id_or_doi_or_pmid>")
        print("         Paper details (S2 with Crossref/PubMed fallback)")
        print("  session [filepath]")
        print("         List or load research sessions")
        sys.exit(1)

    cmd = sys.argv[1]
    COMMANDS[cmd](sys.argv[2:])
