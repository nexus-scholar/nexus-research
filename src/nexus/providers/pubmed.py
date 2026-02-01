"""
PubMed provider implementation.

PubMed comprises more than 36 million citations for biomedical literature from
MEDLINE, life science journals, and online books. This provider implements
search functionality for the NCBI E-Utilities API.

API Documentation: https://www.ncbi.nlm.nih.gov/books/NBK25501/
"""

import logging
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterator, List, Optional

from nexus.core.config import ProviderConfig
from nexus.core.models import Author, Document, ExternalIds, Query
from nexus.providers.base import BaseProvider
from nexus.providers.query_translator import BooleanQueryTranslator, QueryField
from nexus.utils.exceptions import NetworkError, ProviderError

logger = logging.getLogger(__name__)


class PubMedProvider(BaseProvider):
    """Provider for PubMed (NCBI E-Utilities) API."""

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    @property
    def name(self) -> str:
        """Get the provider name."""
        return "pubmed"

    def __init__(self, config: ProviderConfig):
        """Initialize PubMed provider."""
        super().__init__(config)

        # Set default rate limit
        if config.rate_limit == 1.0:
            self.config.rate_limit = 10.0 if config.api_key else 3.0
            self.rate_limiter.rate = self.config.rate_limit

        # Field mapping for PubMed
        field_map = {
            QueryField.TITLE: "Title",
            QueryField.ABSTRACT: "Abstract",
            QueryField.AUTHOR: "Author",
            QueryField.VENUE: "Journal",
            QueryField.YEAR: "Date - Publication",
            QueryField.DOI: "DOI",
        }
        
        self.translator = BooleanQueryTranslator(field_map=field_map)
        
        # Override format logic for PubMed suffix syntax: term[Field]
        def pubmed_format_field_term(field: str, term: str, is_phrase: bool) -> str:
            if not field or field == "any":
                return f'"{term}"' if is_phrase else term
            
            val = f'"{term}"' if is_phrase else term
            return f"{val}[{field}]"

        self.translator.format_field_term = pubmed_format_field_term

        logger.info(f"Initialized PubMed provider (rate_limit={self.config.rate_limit}/s)")

    def search(self, query: Query) -> Iterator[Document]:
        """Execute search on PubMed."""
        esearch_params = self._translate_query(query)
        
        max_results = query.max_results or 1000
        esearch_params["retmax"] = min(max_results, 10000)
        esearch_params["usehistory"] = "y"

        try:
            esearch_url = f"{self.BASE_URL}/esearch.fcgi"
            esearch_response = self._make_request_xml(esearch_url, params=esearch_params)
            esearch_root = ET.fromstring(esearch_response)
            
            error_list = esearch_root.find("ErrorList")
            if error_list is not None:
                phrase_not_found = error_list.find("PhraseNotFound")
                if phrase_not_found is not None:
                    logger.warning(f"PubMed phrase not found: {phrase_not_found.text}")
                    return

            webenv = esearch_root.findtext("WebEnv")
            query_key = esearch_root.findtext("QueryKey")
            count_text = esearch_root.findtext("Count", "0")
            count = int(count_text) if count_text else 0
            
            id_list = [id_elem.text for id_elem in esearch_root.findall(".//IdList/Id")]
            
            if count == 0:
                return

        except Exception as e:
            logger.error(f"PubMed search failed: {e}")
            raise ProviderError(self.name, f"ESearch failed: {e}")

        batch_size = 200
        total_fetched = 0
        
        if webenv and query_key:
            for start in range(0, min(count, max_results), batch_size):
                efetch_params = {
                    "db": "pubmed",
                    "query_key": query_key,
                    "WebEnv": webenv,
                    "retstart": start,
                    "retmax": batch_size,
                    "retmode": "xml"
                }
                if self.config.api_key:
                    efetch_params["api_key"] = self.config.api_key
                    
                yield from self._fetch_and_process_batch(efetch_params)
        else:
            for i in range(0, len(id_list), batch_size):
                if total_fetched >= max_results:
                    break
                batch_ids = id_list[i : i + batch_size]
                efetch_params = {
                    "db": "pubmed",
                    "id": ",".join(batch_ids),
                    "retmode": "xml"
                }
                if self.config.api_key:
                    efetch_params["api_key"] = self.config.api_key
                
                yield from self._fetch_and_process_batch(efetch_params)
                total_fetched += len(batch_ids)

    def _fetch_and_process_batch(self, params: Dict[str, Any]) -> Iterator[Document]:
        """Fetch a batch of records and yield Documents."""
        efetch_url = f"{self.BASE_URL}/efetch.fcgi"
        try:
            response_xml = self._make_request_xml(efetch_url, params=params)
            root = ET.fromstring(response_xml)
            articles = root.findall(".//PubmedArticle")
            for article in articles:
                doc = self._normalize_response(article)
                if doc:
                    yield doc
        except Exception as e:
            logger.error(f"PubMed fetch batch failed: {e}")

    def _translate_query(self, query: Query) -> Dict[str, Any]:
        """Translate Query to PubMed ESearch parameters."""
        translation = self.translator.translate(query)
        base_term = translation["q"]

        params = {
            "db": "pubmed",
            "term": base_term,
            "retmode": "xml"
        }
        
        date_query = ""
        if query.year_min and query.year_max:
            date_query = f" AND {query.year_min}:{query.year_max}[Date - Publication]"
        elif query.year_min:
            date_query = f" AND {query.year_min}:3000[Date - Publication]"
        elif query.year_max:
            date_query = f" AND 1000:{query.year_max}[Date - Publication]"
            
        if date_query:
            params["term"] = f"({params['term']}){date_query}"

        if self.config.api_key:
            params["api_key"] = self.config.api_key
            
        return params

    def _normalize_response(self, element: Any) -> Optional[Document]:
        """Convert PubMed XML element to Document."""
        try:
            medline = element.find("MedlineCitation")
            article = medline.find("Article") if medline is not None else None
            if article is None:
                return None

            title = article.findtext("ArticleTitle")
            if not title:
                return None

            abstract_elem = article.find("Abstract")
            abstract = ""
            if abstract_elem is not None:
                texts = abstract_elem.findall("AbstractText")
                if texts:
                    abstract = " ".join(t.text for t in texts if t.text)

            authors = []
            author_list = article.find("AuthorList")
            if author_list is not None:
                for au in author_list.findall("Author"):
                    last = au.findtext("LastName")
                    fore = au.findtext("ForeName")
                    orcid = None
                    for id_node in au.findall("Identifier"):
                        if id_node.get("Source") == "ORCID":
                            orcid = id_node.text
                            if orcid and "orcid.org/" in orcid:
                                orcid = orcid.split("orcid.org/")[-1]
                    if last:
                        authors.append(Author(family_name=last, given_name=fore, orcid=orcid))

            pub_date = article.find("Journal/JournalIssue/PubDate")
            year = None
            if pub_date is not None:
                year_text = pub_date.findtext("Year")
                if year_text:
                    try:
                        year = int(year_text)
                    except ValueError:
                        pass
                else:
                    medline_date = pub_date.findtext("MedlineDate")
                    if medline_date:
                        import re
                        match = re.search(r"\d{4}", medline_date)
                        if match:
                            year = int(match.group(0))

            venue = article.findtext("Journal/Title")
            pmid = medline.findtext("PMID")
            doi = None
            for eloc in article.findall("ELocationID"):
                if eloc.get("EIdType") == "doi":
                    doi = eloc.text
            if not doi:
                article_ids = element.find("PubmedData/ArticleIdList")
                if article_ids is not None:
                    for aid in article_ids.findall("ArticleId"):
                        if aid.get("IdType") == "doi":
                            doi = aid.text
                            break

            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None
            external_ids = ExternalIds(pubmed_id=pmid, doi=doi)

            return Document(
                title=title,
                year=year,
                abstract=abstract,
                authors=authors,
                venue=venue,
                url=url,
                external_ids=external_ids,
                provider="pubmed",
                provider_id=pmid or (doi or str(hash(title))),
            )
        except Exception as e:
            logger.error(f"Failed to normalize PubMed article: {e}")
            return None

    def _make_request_xml(self, url: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Make HTTP request and return XML text."""
        import requests
        from urllib.parse import urlencode
        
        query_str = f"{url}"
        if params:
            query_str = f"{url}?{urlencode(params)}"
        self._last_query = query_str
        
        if not self.rate_limiter.wait_for_token(timeout=30):
            from nexus.utils.exceptions import RateLimitError
            raise RateLimitError(self.name, "Rate limit timeout for PubMed")

        headers = {"User-Agent": f'SimpleSLR/1.0 ({self.config.mailto or ""})'}
        try:
            response = requests.get(url, params=params, headers=headers, timeout=self.config.timeout)
            response.raise_for_status()
            return response.text
        except Exception as e:
            from nexus.utils.exceptions import NetworkError
            raise NetworkError(self.name, f"Request failed: {e}")