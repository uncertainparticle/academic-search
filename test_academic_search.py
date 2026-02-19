#!/usr/bin/env python3
"""Comprehensive smoke-test suite for academic_search.py.

All external API calls are mocked — no network access required.
"""

import contextlib
import io
import json
import os
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch, MagicMock

import academic_search as AS


# ---------------------------------------------------------------------------
# XML helper
# ---------------------------------------------------------------------------

def _make_pubmed_xml(
    pmid="12345",
    title="Test Title",
    authors=None,
    year="2023",
    journal="Test Journal",
    volume="10",
    issue="4",
    pages="100-110",
    doi="10.1234/test",
    abstract="Test abstract text.",
    medline_date=None,
    structured_abstract=None,
    pub_types=None,
    retraction_in=False,
):
    """Build a minimal PubmedArticleSet XML string."""
    if authors is None:
        authors = [("John", "Doe"), ("Jane", "Smith")]

    author_xml = ""
    for fore, last in authors:
        author_xml += f"""
        <Author>
            <ForeName>{fore}</ForeName>
            <LastName>{last}</LastName>
        </Author>"""

    year_xml = ""
    if year and not medline_date:
        year_xml = f"<Year>{year}</Year>"
    if medline_date:
        year_xml = f"<MedlineDate>{medline_date}</MedlineDate>"

    abstract_xml = ""
    if structured_abstract:
        parts = ""
        for label, text in structured_abstract:
            parts += f'<AbstractText Label="{label}">{text}</AbstractText>\n'
        abstract_xml = f"<Abstract>{parts}</Abstract>"
    elif abstract:
        abstract_xml = f"<Abstract><AbstractText>{abstract}</AbstractText></Abstract>"

    pub_type_xml = ""
    if pub_types:
        entries = "".join(f"<PublicationType>{pt}</PublicationType>" for pt in pub_types)
        pub_type_xml = f"<PublicationTypeList>{entries}</PublicationTypeList>"

    retraction_xml = ""
    if retraction_in:
        retraction_xml = """
        <CommentsCorrectionsList>
            <CommentsCorrections RefType="RetractionIn">
                <RefSource>Some Journal. 2024</RefSource>
                <PMID>99999</PMID>
            </CommentsCorrections>
        </CommentsCorrectionsList>"""

    vol_xml = f"<Volume>{volume}</Volume>" if volume else ""
    iss_xml = f"<Issue>{issue}</Issue>" if issue else ""
    pages_xml = f"<Pagination><MedlinePgn>{pages}</MedlinePgn></Pagination>" if pages else ""
    doi_xml = f'<ArticleId IdType="doi">{doi}</ArticleId>' if doi else ""

    return f"""<?xml version="1.0" ?>
<PubmedArticleSet>
    <PubmedArticle>
        <MedlineCitation>
            <PMID>{pmid}</PMID>
            {retraction_xml}
            <Article>
                <ArticleTitle>{title}</ArticleTitle>
                <AuthorList>{author_xml}
                </AuthorList>
                {pub_type_xml}
                <Journal>
                    <Title>{journal}</Title>
                    <JournalIssue>
                        {vol_xml}
                        {iss_xml}
                    </JournalIssue>
                </Journal>
                <PubDate>
                    {year_xml}
                </PubDate>
                {pages_xml}
                {abstract_xml}
            </Article>
        </MedlineCitation>
        <ArticleIdList>
            {doi_xml}
        </ArticleIdList>
    </PubmedArticle>
</PubmedArticleSet>"""


# ====================================================================
# 1. TestNormalizeDoi
# ====================================================================
class TestNormalizeDoi(unittest.TestCase):

    def test_https_url(self):
        self.assertEqual(AS.normalize_doi("https://doi.org/10.1234/test"), "10.1234/test")

    def test_http_url(self):
        self.assertEqual(AS.normalize_doi("http://doi.org/10.1234/test"), "10.1234/test")

    def test_bare_doi_org(self):
        """Bug 3 fix: bare doi.org/ without protocol."""
        self.assertEqual(AS.normalize_doi("doi.org/10.1234/test"), "10.1234/test")

    def test_doi_prefix(self):
        self.assertEqual(AS.normalize_doi("doi:10.1234/test"), "10.1234/test")

    def test_doi_prefix_space(self):
        self.assertEqual(AS.normalize_doi("doi: 10.1234/test"), "10.1234/test")

    def test_trailing_period(self):
        self.assertEqual(AS.normalize_doi("10.1234/test."), "10.1234/test")

    def test_trailing_comma(self):
        self.assertEqual(AS.normalize_doi("10.1234/test,"), "10.1234/test")

    def test_trailing_semicolon(self):
        self.assertEqual(AS.normalize_doi("10.1234/test;"), "10.1234/test")

    def test_bare_doi(self):
        self.assertEqual(AS.normalize_doi("10.1234/test"), "10.1234/test")


# ====================================================================
# 2. TestNormalizeText
# ====================================================================
class TestNormalizeText(unittest.TestCase):

    def test_html_unescape(self):
        self.assertIn("&", AS._normalize_text("&amp;"))

    def test_unicode_dash(self):
        result = AS._normalize_text("foo\u2013bar")
        self.assertEqual(result, "foo-bar")

    def test_unicode_quotes(self):
        result = AS._normalize_text("\u201Chello\u201D")
        self.assertEqual(result, "'hello'")

    def test_plain_text(self):
        self.assertEqual(AS._normalize_text("hello"), "hello")

    def test_mixed(self):
        result = AS._normalize_text("It\u2019s a test &amp; more")
        self.assertIn("'", result)
        self.assertIn("&", result)

    def test_multiple_dashes(self):
        result = AS._normalize_text("\u2014\u2015\u2212")
        self.assertEqual(result, "---")


# ====================================================================
# 3. TestTokenSimilarity
# ====================================================================
class TestTokenSimilarity(unittest.TestCase):

    def test_identical(self):
        self.assertAlmostEqual(AS.token_similarity("hello world", "hello world"), 1.0)

    def test_completely_different(self):
        self.assertAlmostEqual(AS.token_similarity("hello world", "foo bar"), 0.0)

    def test_partial_overlap(self):
        sim = AS.token_similarity("hello world", "hello there")
        self.assertGreater(sim, 0.0)
        self.assertLess(sim, 1.0)

    def test_empty_first(self):
        self.assertAlmostEqual(AS.token_similarity("", "hello"), 0.0)

    def test_empty_second(self):
        self.assertAlmostEqual(AS.token_similarity("hello", ""), 0.0)

    def test_none_input(self):
        self.assertAlmostEqual(AS.token_similarity(None, "hello"), 0.0)

    def test_html_entities(self):
        sim = AS.token_similarity("cancer &amp; treatment", "cancer & treatment")
        self.assertAlmostEqual(sim, 1.0)

    def test_case_insensitive(self):
        self.assertAlmostEqual(AS.token_similarity("Hello World", "hello world"), 1.0)


# ====================================================================
# 4. TestExtractLastName
# ====================================================================
class TestExtractLastName(unittest.TestCase):

    def test_first_last(self):
        self.assertEqual(AS._extract_last_name("John Smith"), "smith")

    def test_last_comma_first(self):
        self.assertEqual(AS._extract_last_name("Smith, John"), "smith")

    def test_last_initial(self):
        self.assertEqual(AS._extract_last_name("Smith J"), "smith")

    def test_initial_last(self):
        self.assertEqual(AS._extract_last_name("J Smith"), "smith")

    def test_single_name(self):
        self.assertEqual(AS._extract_last_name("Smith"), "smith")

    def test_empty_string(self):
        self.assertEqual(AS._extract_last_name(""), "")

    def test_none(self):
        self.assertEqual(AS._extract_last_name(None), "")

    def test_two_initials_last(self):
        self.assertEqual(AS._extract_last_name("JM Smith"), "smith")

    def test_last_two_initials(self):
        self.assertEqual(AS._extract_last_name("Smith JM"), "smith")

    def test_multiple_parts_first_last(self):
        self.assertEqual(AS._extract_last_name("John Michael Smith"), "smith")

    def test_comma_with_spaces(self):
        self.assertEqual(AS._extract_last_name("Smith , John"), "smith")

    def test_dotted_initial(self):
        self.assertEqual(AS._extract_last_name("J. Smith"), "smith")


# ====================================================================
# 5. TestNormalizeString
# ====================================================================
class TestNormalizeString(unittest.TestCase):

    def test_lowercase(self):
        self.assertEqual(AS.normalize_string("Hello"), "hello")

    def test_strip_punctuation(self):
        self.assertEqual(AS.normalize_string("hello, world!"), "hello world")

    def test_none(self):
        self.assertEqual(AS.normalize_string(None), "")

    def test_empty(self):
        self.assertEqual(AS.normalize_string(""), "")

    def test_mixed(self):
        self.assertEqual(AS.normalize_string("J. Am. Chem. Soc."), "j am chem soc")


# ====================================================================
# 6. TestParseReferenceText
# ====================================================================
class TestParseReferenceText(unittest.TestCase):

    def test_doi_extraction(self):
        ref = AS.parse_reference_text("Some title. doi:10.1234/test.v1")
        self.assertEqual(ref["doi"], "10.1234/test.v1")

    def test_doi_url_extraction(self):
        ref = AS.parse_reference_text("https://doi.org/10.1234/test Some text")
        self.assertEqual(ref["doi"], "10.1234/test")

    def test_bare_doi(self):
        ref = AS.parse_reference_text("Ref text 10.1234/test more text")
        self.assertEqual(ref["doi"], "10.1234/test")

    def test_pmid_extraction(self):
        ref = AS.parse_reference_text("Title. PMID: 12345678")
        self.assertEqual(ref["pmid"], "12345678")

    def test_year_parenthesized(self):
        ref = AS.parse_reference_text("Author (2023). Title.")
        self.assertEqual(ref["year"], 2023)

    def test_year_freestanding(self):
        ref = AS.parse_reference_text("Author. Title. Journal. 2023;10:100.")
        self.assertEqual(ref["year"], 2023)

    def test_year_at_end_of_string(self):
        """Bug 2 fix: year at string boundary."""
        ref = AS.parse_reference_text("Published 2024")
        self.assertEqual(ref["year"], 2024)

    def test_year_at_start_of_string(self):
        """Bug 2 fix: year at start."""
        ref = AS.parse_reference_text("2023 Jan;10(1):50-55")
        self.assertEqual(ref["year"], 2023)

    def test_vip_extraction(self):
        ref = AS.parse_reference_text("Journal. 2023;10(4):663-72.")
        self.assertEqual(ref["volume"], "10")
        self.assertEqual(ref["issue"], "4")
        self.assertEqual(ref["pages"], "663-72")

    def test_numbered_ref_stripped(self):
        """Numbered prefix is stripped for extraction but raw is preserved."""
        ref = AS.parse_reference_text("[1] Author. Title. 2023.")
        # raw preserves original text
        self.assertIn("[1]", ref["raw"])
        # but year is still extracted from cleaned text
        self.assertEqual(ref["year"], 2023)

    def test_no_fields(self):
        ref = AS.parse_reference_text("Some random text")
        self.assertIn("raw", ref)
        self.assertNotIn("doi", ref)
        self.assertNotIn("pmid", ref)


# ====================================================================
# 7. TestLoadReferencesFile
# ====================================================================
class TestLoadReferencesFile(unittest.TestCase):

    def test_json_array(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([{"title": "A"}, {"title": "B"}], f)
            f.flush()
            result = AS.load_references_file(f.name)
        os.unlink(f.name)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["title"], "A")

    def test_json_dict_with_references_key(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"references": [{"title": "X"}]}, f)
            f.flush()
            result = AS.load_references_file(f.name)
        os.unlink(f.name)
        self.assertEqual(len(result), 1)

    def test_text_blank_line_split(self):
        content = "First reference line\n\nSecond reference line\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            f.flush()
            result = AS.load_references_file(f.name)
        os.unlink(f.name)
        self.assertEqual(len(result), 2)

    def test_text_numbered_refs(self):
        content = "1. First ref\n2. Second ref\n3. Third ref\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            f.flush()
            result = AS.load_references_file(f.name)
        os.unlink(f.name)
        self.assertEqual(len(result), 3)

    def test_single_reference(self):
        content = "Just one reference here"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            f.flush()
            result = AS.load_references_file(f.name)
        os.unlink(f.name)
        self.assertEqual(len(result), 1)

    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            AS.load_references_file("/nonexistent/path/refs.json")


# ====================================================================
# 8. TestParsePubmedArticle
# ====================================================================
class TestParsePubmedArticle(unittest.TestCase):

    def test_full_article(self):
        xml = _make_pubmed_xml()
        root = ET.fromstring(xml)
        article = root.find(".//PubmedArticle")
        result = AS.parse_pubmed_article(article)
        self.assertEqual(result["pmid"], "12345")
        self.assertEqual(result["title"], "Test Title")
        self.assertEqual(result["year"], 2023)
        self.assertEqual(result["journal"], "Test Journal")
        self.assertEqual(result["volume"], "10")
        self.assertEqual(result["issue"], "4")
        self.assertEqual(result["pages"], "100-110")
        self.assertEqual(result["doi"], "10.1234/test")
        self.assertEqual(len(result["authors"]), 2)
        self.assertEqual(result["source"], "pubmed")

    def test_missing_authors(self):
        xml = _make_pubmed_xml(authors=[])
        root = ET.fromstring(xml)
        article = root.find(".//PubmedArticle")
        result = AS.parse_pubmed_article(article)
        self.assertEqual(result["authors"], [])

    def test_medline_date_fallback(self):
        xml = _make_pubmed_xml(year=None, medline_date="2021 Jan-Feb")
        root = ET.fromstring(xml)
        article = root.find(".//PubmedArticle")
        result = AS.parse_pubmed_article(article)
        self.assertEqual(result["year"], 2021)

    def test_structured_abstract(self):
        xml = _make_pubmed_xml(
            abstract=None,
            structured_abstract=[("BACKGROUND", "Bg text."), ("METHODS", "Method text.")]
        )
        root = ET.fromstring(xml)
        article = root.find(".//PubmedArticle")
        result = AS.parse_pubmed_article(article)
        self.assertIn("BACKGROUND", result["abstract"])
        self.assertIn("METHODS", result["abstract"])

    def test_no_doi(self):
        xml = _make_pubmed_xml(doi=None)
        root = ET.fromstring(xml)
        article = root.find(".//PubmedArticle")
        result = AS.parse_pubmed_article(article)
        self.assertIsNone(result["doi"])


# ====================================================================
# 9. TestNormalizeS2Paper
# ====================================================================
class TestNormalizeS2Paper(unittest.TestCase):

    def test_full_input(self):
        p = {
            "paperId": "abc123",
            "title": "Test Paper",
            "authors": [{"name": "Alice"}, {"name": "Bob"}],
            "year": 2023,
            "venue": "ICML",
            "publicationVenue": {"name": "ICML Conference"},
            "journal": {"name": "ICML", "volume": "5", "pages": "1-10"},
            "externalIds": {"DOI": "10.1234/test", "PubMed": "99999"},
            "abstract": "An abstract.",
            "citationCount": 42,
            "publicationDate": "2023-06-01",
        }
        result = AS.normalize_s2_paper(p)
        self.assertEqual(result["semantic_scholar_id"], "abc123")
        self.assertEqual(result["doi"], "10.1234/test")
        self.assertEqual(result["pmid"], "99999")
        self.assertEqual(result["journal"], "ICML Conference")  # publicationVenue preferred
        self.assertEqual(result["citation_count"], 42)
        self.assertEqual(result["source"], "semantic_scholar")

    def test_minimal_input(self):
        p = {"paperId": "x", "title": "Min"}
        result = AS.normalize_s2_paper(p)
        self.assertEqual(result["semantic_scholar_id"], "x")
        self.assertEqual(result["title"], "Min")
        self.assertIsNone(result["doi"])
        self.assertEqual(result["authors"], [])

    def test_none_external_ids(self):
        p = {"paperId": "x", "title": "T", "externalIds": None}
        result = AS.normalize_s2_paper(p)
        self.assertIsNone(result["doi"])
        self.assertIsNone(result["pmid"])

    def test_venue_priority(self):
        """publicationVenue > journal.name > venue."""
        p = {
            "paperId": "x",
            "title": "T",
            "venue": "V1",
            "journal": {"name": "V2"},
            "publicationVenue": None,
        }
        result = AS.normalize_s2_paper(p)
        self.assertEqual(result["journal"], "V2")


# ====================================================================
# 10. TestNormalizeCrossrefPaper
# ====================================================================
class TestNormalizeCrossrefPaper(unittest.TestCase):

    def test_full_input(self):
        item = {
            "DOI": "10.1234/test",
            "title": ["Test Title"],
            "author": [{"given": "John", "family": "Doe"}],
            "published-print": {"date-parts": [[2023, 6, 1]]},
            "container-title": ["Nature"],
            "volume": "5",
            "issue": "2",
            "page": "10-20",
            "publisher": "NPG",
            "type": "journal-article",
            "is-referenced-by-count": 100,
        }
        result = AS.normalize_crossref_paper(item)
        self.assertEqual(result["doi"], "10.1234/test")
        self.assertEqual(result["title"], "Test Title")
        self.assertEqual(result["authors"], ["John Doe"])
        self.assertEqual(result["year"], 2023)
        self.assertEqual(result["journal"], "Nature")
        self.assertEqual(result["source"], "crossref")

    def test_empty_input(self):
        result = AS.normalize_crossref_paper({})
        self.assertEqual(result["title"], "")
        self.assertEqual(result["authors"], [])
        self.assertIsNone(result["year"])

    def test_html_in_title(self):
        item = {"title": ["Effect of &amp; treatment"], "DOI": "10.1/x"}
        result = AS.normalize_crossref_paper(item)
        self.assertIn("&", result["title"])
        self.assertNotIn("&amp;", result["title"])

    def test_date_fallback(self):
        item = {
            "DOI": "10.1/x",
            "title": ["T"],
            "published-online": {"date-parts": [[2022]]},
        }
        result = AS.normalize_crossref_paper(item)
        self.assertEqual(result["year"], 2022)

    def test_issued_fallback(self):
        item = {
            "DOI": "10.1/x",
            "title": ["T"],
            "issued": {"date-parts": [[2021, 3]]},
        }
        result = AS.normalize_crossref_paper(item)
        self.assertEqual(result["year"], 2021)


# ====================================================================
# 11. TestDeduplicatePapers
# ====================================================================
class TestDeduplicatePapers(unittest.TestCase):

    def _paper(self, **kw):
        base = {
            "title": "", "doi": None, "pmid": None,
            "semantic_scholar_id": None, "source": "test",
            "authors": [], "year": None, "journal": "",
            "volume": None, "issue": None, "pages": None,
            "abstract": "", "citation_count": None,
        }
        base.update(kw)
        return base

    def test_doi_dedup(self):
        s2 = [self._paper(title="A", doi="10.1/a", source="semantic_scholar")]
        pm = [self._paper(title="A", doi="10.1/a", source="pubmed")]
        result = AS.deduplicate_papers(s2, pm)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source"], "both")

    def test_pmid_dedup(self):
        s2 = [self._paper(title="B", pmid="111", source="semantic_scholar")]
        pm = [self._paper(title="B", pmid="111", source="pubmed")]
        result = AS.deduplicate_papers(s2, pm)
        self.assertEqual(len(result), 1)

    def test_title_dedup(self):
        s2 = [self._paper(title="Same Title", source="semantic_scholar")]
        pm = [self._paper(title="Same Title", source="pubmed")]
        result = AS.deduplicate_papers(s2, pm)
        self.assertEqual(len(result), 1)

    def test_no_overlap(self):
        s2 = [self._paper(title="A", doi="10.1/a")]
        pm = [self._paper(title="B", doi="10.1/b")]
        result = AS.deduplicate_papers(s2, pm)
        self.assertEqual(len(result), 2)

    def test_merge_fills_missing(self):
        s2 = [self._paper(title="A", doi="10.1/a", abstract="")]
        pm = [self._paper(title="A", doi="10.1/a", abstract="Full abstract")]
        result = AS.deduplicate_papers(s2, pm)
        self.assertEqual(result[0]["abstract"], "Full abstract")

    def test_empty_inputs(self):
        result = AS.deduplicate_papers([], [])
        self.assertEqual(result, [])

    def test_one_empty(self):
        s2 = [self._paper(title="X", doi="10.1/x")]
        result = AS.deduplicate_papers(s2, [])
        self.assertEqual(len(result), 1)

    def test_empty_key_collision(self):
        """Bug 5 fix: papers with no identifiers and empty titles shouldn't collide."""
        s2 = [
            self._paper(title="", doi=None, pmid=None, semantic_scholar_id=None),
            self._paper(title="", doi=None, pmid=None, semantic_scholar_id=None),
        ]
        result = AS.deduplicate_papers(s2, [])
        self.assertEqual(len(result), 2)


# ====================================================================
# 12. TestFormatPaperTable
# ====================================================================
class TestFormatPaperTable(unittest.TestCase):

    def _paper(self, **kw):
        base = {
            "title": "Test Paper", "authors": ["Author One"],
            "year": 2023, "journal": "J Test", "citation_count": 10,
        }
        base.update(kw)
        return base

    def test_basic_output(self):
        papers = [self._paper()]
        output = AS.format_paper_table(papers)
        self.assertIn("Test Paper", output)
        self.assertIn("2023", output)
        self.assertIn("Author One", output)

    def test_truncation(self):
        papers = [self._paper(title="A" * 100, authors=["B" * 100], journal="C" * 100)]
        output = AS.format_paper_table(papers)
        self.assertIn("..", output)

    def test_max_papers(self):
        papers = [self._paper(title=f"Paper {i}") for i in range(30)]
        output = AS.format_paper_table(papers, max_papers=5)
        lines = [l for l in output.split("\n") if l.strip() and not l.startswith("-")]
        # header + 5 data lines
        self.assertEqual(len(lines), 6)

    def test_missing_fields(self):
        papers = [{"title": "No Author", "year": None, "citation_count": None}]
        output = AS.format_paper_table(papers)
        self.assertIn("Unknown", output)
        self.assertIn("N/A", output)


# ====================================================================
# 13. TestFormatVolIssuePages
# ====================================================================
class TestFormatVolIssuePages(unittest.TestCase):

    def test_all_present(self):
        result = AS._format_vol_issue_pages({"volume": "10", "issue": "4", "pages": "100-110"})
        self.assertEqual(result, ";10(4):100-110")

    def test_volume_only(self):
        result = AS._format_vol_issue_pages({"volume": "10", "issue": None, "pages": None})
        self.assertEqual(result, ";10")

    def test_volume_and_issue(self):
        result = AS._format_vol_issue_pages({"volume": "10", "issue": "4", "pages": None})
        self.assertEqual(result, ";10(4)")

    def test_pages_only(self):
        result = AS._format_vol_issue_pages({"volume": None, "issue": None, "pages": "50-60"})
        self.assertEqual(result, ":50-60")

    def test_volume_and_pages(self):
        result = AS._format_vol_issue_pages({"volume": "10", "issue": None, "pages": "50-60"})
        self.assertEqual(result, ";10:50-60")

    def test_all_none(self):
        result = AS._format_vol_issue_pages({"volume": None, "issue": None, "pages": None})
        self.assertEqual(result, "")

    def test_empty_dict(self):
        result = AS._format_vol_issue_pages({})
        self.assertEqual(result, "")


# ====================================================================
# 14. TestFormatCitationAMA
# ====================================================================
class TestFormatCitationAMA(unittest.TestCase):

    def test_full_citation(self):
        p = {
            "authors": ["John Doe", "Jane Smith"],
            "title": "Test Title",
            "journal": "Test Journal",
            "year": 2023,
            "volume": "10",
            "issue": "4",
            "pages": "100-110",
            "doi": "10.1234/test",
        }
        result = AS.format_citation_ama(p)
        self.assertIn("John Doe, Jane Smith", result)
        self.assertIn("Test Title", result)
        self.assertIn("doi:10.1234/test", result)
        self.assertTrue(result.startswith("1."))

    def test_more_than_6_authors(self):
        p = {
            "authors": ["A1", "A2", "A3", "A4", "A5", "A6", "A7"],
            "title": "T", "journal": "J", "year": 2023,
            "volume": None, "issue": None, "pages": None, "doi": None,
        }
        result = AS.format_citation_ama(p)
        self.assertIn("et al", result)
        self.assertNotIn("A4", result)

    def test_no_doi(self):
        p = {
            "authors": ["A"], "title": "T", "journal": "J",
            "year": 2023, "volume": None, "issue": None, "pages": None, "doi": None,
        }
        result = AS.format_citation_ama(p)
        self.assertNotIn("doi:", result)

    def test_trailing_period(self):
        p = {
            "authors": ["A"], "title": "Title.", "journal": "J",
            "year": 2023, "volume": None, "issue": None, "pages": None, "doi": None,
        }
        result = AS.format_citation_ama(p)
        # Title should have period stripped then re-added by format
        self.assertNotIn("Title..", result)


# ====================================================================
# 15. TestFormatCitationVancouver
# ====================================================================
class TestFormatCitationVancouver(unittest.TestCase):

    def test_basic(self):
        p = {
            "authors": ["John Doe"], "title": "Test", "journal": "J",
            "year": 2023, "volume": "1", "issue": None, "pages": "5",
            "doi": "10.1/x",
        }
        result = AS.format_citation_vancouver(p)
        self.assertIn("John Doe", result)
        self.assertIn("doi: 10.1/x", result)  # Vancouver uses "doi: " with space

    def test_more_than_6_authors(self):
        p = {
            "authors": [f"A{i}" for i in range(8)],
            "title": "T", "journal": "J", "year": 2023,
            "volume": None, "issue": None, "pages": None, "doi": None,
        }
        result = AS.format_citation_vancouver(p)
        self.assertIn("et al", result)
        self.assertIn("A5", result)  # Vancouver keeps 6 authors
        self.assertNotIn("A6", result)

    def test_custom_number(self):
        p = {
            "authors": ["A"], "title": "T", "journal": "J",
            "year": 2023, "volume": None, "issue": None, "pages": None, "doi": None,
        }
        result = AS.format_citation_vancouver(p, number=5)
        self.assertTrue(result.startswith("5."))


# ====================================================================
# 16. TestSessionManagement
# ====================================================================
class TestSessionManagement(unittest.TestCase):

    def test_create_session(self):
        s = AS.create_session("diabetes treatment")
        self.assertIn("session_id", s)
        self.assertEqual(s["topic"], "diabetes treatment")
        self.assertIn("diabetes_treatment", s["filename"])
        self.assertEqual(s["papers"], {})
        self.assertEqual(s["searches_performed"], [])

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            s = AS.create_session("test topic")
            s["filename"] = os.path.join(tmpdir, "test_session.json")
            s["papers"]["k1"] = {"title": "Paper1"}
            filepath = AS.save_session(s)
            loaded = AS.load_session(filepath)
            self.assertEqual(loaded["topic"], "test topic")
            self.assertIn("k1", loaded["papers"])

    def test_add_papers_merge(self):
        s = AS.create_session("test")
        p1 = {"title": "Paper A", "doi": "10.1/a", "abstract": ""}
        AS.add_papers_to_session(s, [p1], "query1", "s2")
        self.assertEqual(len(s["papers"]), 1)
        self.assertEqual(len(s["searches_performed"]), 1)

        # Same DOI with more data should merge
        p2 = {"title": "Paper A", "doi": "10.1/a", "abstract": "Full text", "source": "pubmed"}
        AS.add_papers_to_session(s, [p2], "query2", "pm")
        self.assertEqual(len(s["papers"]), 1)
        self.assertEqual(s["papers"]["10.1/a"]["abstract"], "Full text")
        self.assertEqual(s["papers"]["10.1/a"]["source"], "both")

    def test_add_papers_no_key(self):
        s = AS.create_session("test")
        p = {"title": "", "doi": None, "pmid": None, "semantic_scholar_id": None}
        AS.add_papers_to_session(s, [p], "q", "s2")
        self.assertEqual(len(s["papers"]), 0)  # skipped

    def test_citation_graph(self):
        s = AS.create_session("test")
        papers = [{"semantic_scholar_id": "p1"}, {"doi": "10.1/x"}]
        AS.add_citations_to_session(s, "root_id", "citedBy", papers)
        self.assertIn("root_id", s["citation_graph"])
        self.assertEqual(len(s["citation_graph"]["root_id"]["cited_by"]), 2)

    def test_citation_graph_references(self):
        s = AS.create_session("test")
        papers = [{"semantic_scholar_id": "r1"}]
        AS.add_citations_to_session(s, "root_id", "references", papers)
        self.assertEqual(len(s["citation_graph"]["root_id"]["cites"]), 1)

    def test_session_slug_special_chars(self):
        s = AS.create_session("COVID-19 & mRNA Vaccines!")
        self.assertIn("covid", s["filename"])
        self.assertNotIn("&", s["filename"])

    def test_add_papers_sets_defaults(self):
        s = AS.create_session("test")
        p = {"title": "P", "doi": "10.1/p"}
        AS.add_papers_to_session(s, [p], "q", "s2")
        self.assertIn("tags", s["papers"]["10.1/p"])
        self.assertIn("notes", s["papers"]["10.1/p"])

    def test_multiple_searches_logged(self):
        s = AS.create_session("test")
        AS.add_papers_to_session(s, [], "q1", "s2")
        AS.add_papers_to_session(s, [], "q2", "pm")
        self.assertEqual(len(s["searches_performed"]), 2)


# ====================================================================
# 17. TestParseFlags
# ====================================================================
class TestParseFlags(unittest.TestCase):

    def test_int_flag(self):
        remaining, parsed = AS.parse_flags(
            ["search", "--limit", "10", "query"],
            {"--limit": int}
        )
        self.assertEqual(parsed["--limit"], 10)
        self.assertEqual(remaining, ["search", "query"])

    def test_string_flag(self):
        remaining, parsed = AS.parse_flags(
            ["--year", "2020-2023"],
            {"--year": str}
        )
        self.assertEqual(parsed["--year"], "2020-2023")

    def test_bool_flag(self):
        remaining, parsed = AS.parse_flags(
            ["--no-retraction-check", "file.json"],
            {"--no-retraction-check": None}
        )
        self.assertTrue(parsed["--no-retraction-check"])
        self.assertEqual(remaining, ["file.json"])

    def test_no_flags(self):
        remaining, parsed = AS.parse_flags(["hello", "world"], {"--limit": int})
        self.assertEqual(remaining, ["hello", "world"])
        self.assertEqual(parsed, {})

    def test_missing_value(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            remaining, parsed = AS.parse_flags(["--limit"], {"--limit": int})
        self.assertNotIn("--limit", parsed)
        self.assertIn("requires a value", buf.getvalue())

    def test_invalid_int(self):
        """Bug 1 fix: non-numeric value for int flag should not crash."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            remaining, parsed = AS.parse_flags(
                ["--limit", "abc", "query"],
                {"--limit": int}
            )
        self.assertNotIn("--limit", parsed)
        self.assertIn("invalid value", buf.getvalue())

    def test_multiple_flags(self):
        remaining, parsed = AS.parse_flags(
            ["--limit", "5", "--year", "2020-2023", "cancer"],
            {"--limit": int, "--year": str}
        )
        self.assertEqual(parsed["--limit"], 5)
        self.assertEqual(parsed["--year"], "2020-2023")
        self.assertEqual(remaining, ["cancer"])


# ====================================================================
# 18. TestFormatVerificationReport
# ====================================================================
class TestFormatVerificationReport(unittest.TestCase):

    def _result(self, status="VERIFIED (1 source)", field_checks=None, pmid=None, best_match=None):
        return {
            "index": 1,
            "input": {"title": "Test", "pmid": pmid, "raw": "Test raw"},
            "status": status,
            "sources": {"crossref": {"title": "Test"}} if "VERIFIED" in status else {},
            "field_checks": field_checks or {},
            "best_match": best_match,
        }

    def test_verified(self):
        results = [self._result()]
        report = AS.format_verification_report(results, set())
        self.assertIn("VERIFIED", report)
        self.assertIn("Verified:          1", report)

    def test_errors_found(self):
        checks = {"year": {"status": "mismatch", "manuscript": "2023", "source": "2022"}}
        results = [self._result(status="ERRORS_FOUND (1 source)", field_checks=checks)]
        report = AS.format_verification_report(results, set())
        self.assertIn("ERRORS", report)
        self.assertIn("XX", report)

    def test_not_found(self):
        results = [self._result(status="NOT_FOUND")]
        report = AS.format_verification_report(results, set())
        self.assertIn("NOT FOUND", report)
        self.assertIn("Not found:         1", report)

    def test_retracted(self):
        results = [self._result(pmid="111", best_match={"pmid": "111"})]
        report = AS.format_verification_report(results, {"111"})
        self.assertIn("RETRACTED", report)

    def test_summary_counts(self):
        results = [
            self._result(status="VERIFIED (1 source)"),
            self._result(status="ERRORS_FOUND (1 source)"),
            self._result(status="NOT_FOUND"),
        ]
        results[0]["index"] = 1
        results[1]["index"] = 2
        results[2]["index"] = 3
        report = AS.format_verification_report(results, set())
        self.assertIn("Total references:  3", report)


# ====================================================================
# 19. TestVerifySingleReference
# ====================================================================
class TestVerifySingleReference(unittest.TestCase):

    @patch("academic_search.time.sleep")
    @patch("academic_search.crossref_resolve_doi")
    def test_doi_resolves_via_crossref(self, mock_cr, mock_sleep):
        mock_cr.return_value = {"title": "Found", "doi": "10.1/x", "authors": [], "year": 2023}
        ref = {"doi": "10.1/x", "title": "Found"}
        result = AS.verify_single_reference(ref, 1)
        self.assertIn("crossref", result["sources"])
        self.assertIn("VERIFIED", result["status"])

    @patch("academic_search.time.sleep")
    @patch("academic_search.pm_search")
    @patch("academic_search.s2_get_paper")
    @patch("academic_search.crossref_resolve_doi")
    def test_s2_fallback_on_crossref_fail(self, mock_cr, mock_s2, mock_pm, mock_sleep):
        mock_cr.return_value = {"error": "not found"}
        mock_s2.return_value = {"title": "S2 Paper", "doi": "10.1/x", "authors": [], "year": 2023}
        mock_pm.return_value = {"papers": []}
        ref = {"doi": "10.1/x"}
        result = AS.verify_single_reference(ref, 1)
        self.assertIn("semantic_scholar", result["sources"])

    @patch("academic_search.time.sleep")
    @patch("academic_search.pm_fetch_details")
    def test_pmid_lookup(self, mock_pm, mock_sleep):
        mock_pm.return_value = [{"title": "PM Paper", "pmid": "123", "authors": [], "year": 2023}]
        ref = {"pmid": "123"}
        result = AS.verify_single_reference(ref, 1)
        self.assertIn("pubmed", result["sources"])

    @patch("academic_search.time.sleep")
    @patch("academic_search.pm_search")
    @patch("academic_search.crossref_search")
    def test_title_search_fallback(self, mock_cr_search, mock_pm, mock_sleep):
        mock_cr_search.return_value = {
            "papers": [{"title": "Matching Title", "doi": "10.1/x", "authors": [], "year": 2023}]
        }
        mock_pm.return_value = {"papers": []}
        ref = {"title": "Matching Title"}
        result = AS.verify_single_reference(ref, 1)
        self.assertIn("crossref", result["sources"])

    @patch("academic_search.time.sleep")
    @patch("academic_search.pm_search")
    @patch("academic_search.crossref_search")
    def test_not_found(self, mock_cr_search, mock_pm, mock_sleep):
        mock_cr_search.return_value = {"papers": []}
        mock_pm.return_value = {"papers": []}
        ref = {"title": "Nonexistent Paper XYZ123"}
        result = AS.verify_single_reference(ref, 1)
        self.assertEqual(result["status"], "NOT_FOUND")

    @patch("academic_search.time.sleep")
    @patch("academic_search.crossref_resolve_doi")
    def test_field_mismatch(self, mock_cr, mock_sleep):
        mock_cr.return_value = {
            "title": "Different Title",
            "doi": "10.1/x",
            "authors": ["Wrong Author"],
            "year": 2020,
        }
        ref = {"doi": "10.1/x", "title": "Original Title", "year": 2023}
        result = AS.verify_single_reference(ref, 1)
        self.assertIn("ERRORS", result["status"])
        self.assertEqual(result["field_checks"]["year"]["status"], "mismatch")


# ====================================================================
# 20. TestCommandHandlers
# ====================================================================
class TestCommandHandlers(unittest.TestCase):

    def test_search_empty_args(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            AS.cmd_search([])
        self.assertIn("Usage", buf.getvalue())

    @patch("academic_search.time.sleep")
    @patch("academic_search.save_session")
    @patch("academic_search.pm_search")
    @patch("academic_search.s2_search")
    def test_search_basic(self, mock_s2, mock_pm, mock_save, mock_sleep):
        mock_s2.return_value = {
            "total": 1,
            "papers": [{"title": "S2 Paper", "doi": "10.1/s2", "authors": ["A"],
                        "year": 2023, "journal": "J", "citation_count": 5,
                        "pmid": None, "semantic_scholar_id": "s2id",
                        "abstract": "", "volume": None, "issue": None,
                        "pages": None, "source": "semantic_scholar",
                        "publication_date": None}],
        }
        mock_pm.return_value = {"total": 0, "papers": []}
        mock_save.return_value = "test_session.json"

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            AS.cmd_search(["cancer"])
        output = buf.getvalue()
        self.assertIn("S2 Paper", output)
        self.assertIn("Searching", output)

    @patch("academic_search.time.sleep")
    @patch("academic_search.save_session")
    @patch("academic_search.pm_search")
    @patch("academic_search.s2_search")
    def test_search_invalid_filter(self, mock_s2, mock_pm, mock_save, mock_sleep):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            AS.cmd_search(["cancer", "--filter", "invalid_filter"])
        self.assertIn("Unknown filter", buf.getvalue())

    @patch("academic_search.time.sleep")
    @patch("academic_search.pm_search_author")
    @patch("academic_search.s2_search_author")
    def test_author_fallback(self, mock_s2, mock_pm, mock_sleep):
        mock_s2.return_value = {"error": "timeout"}
        mock_pm.return_value = {
            "total": 1,
            "papers": [{"title": "PM Paper", "authors": ["John Doe"],
                        "year": 2023, "journal": "J", "citation_count": None}],
        }
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            AS.cmd_author(["John", "Doe"])
        output = buf.getvalue()
        self.assertIn("Falling back", output)

    @patch("academic_search.time.sleep")
    @patch("academic_search.crossref_resolve_doi")
    @patch("academic_search.s2_get_paper")
    def test_detail_doi_fallback(self, mock_s2, mock_cr, mock_sleep):
        mock_s2.return_value = {"error": "not found"}
        mock_cr.return_value = {
            "title": "CR Paper", "doi": "10.1234/test",
            "authors": ["A"], "year": 2023, "journal": "J",
            "volume": "1", "issue": "2", "pages": "3-4",
            "abstract": "abs", "source": "crossref",
            "citation_count": 10, "pmid": None,
            "semantic_scholar_id": None,
        }
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            AS.cmd_detail(["10.1234/test"])
        output = buf.getvalue()
        self.assertIn("CR Paper", output)

    def test_detail_empty_args(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            AS.cmd_detail([])
        self.assertIn("Usage", buf.getvalue())

    def test_citations_empty_args(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            AS.cmd_citations([])
        self.assertIn("Usage", buf.getvalue())


# ====================================================================
# 21. TestPmCheckRetractions
# ====================================================================
class TestPmCheckRetractions(unittest.TestCase):

    def test_empty_pmids(self):
        result = AS.pm_check_retractions([])
        self.assertEqual(result, set())

    @patch("academic_search.pubmed_request")
    def test_publication_type_detection(self, mock_req):
        xml = _make_pubmed_xml(
            pmid="111",
            pub_types=["Journal Article", "Retracted Publication"],
        )
        mock_req.return_value = xml
        result = AS.pm_check_retractions(["111"])
        self.assertIn("111", result)

    @patch("academic_search.pubmed_request")
    def test_comments_corrections_detection(self, mock_req):
        xml = _make_pubmed_xml(pmid="222", retraction_in=True)
        mock_req.return_value = xml
        result = AS.pm_check_retractions(["222"])
        self.assertIn("222", result)


if __name__ == "__main__":
    unittest.main()
