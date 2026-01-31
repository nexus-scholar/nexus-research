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
from nexus.utils.exceptions import NetworkError, ProviderError

logger = logging.getLogger(__name__)


class PubMedProvider(BaseProvider):
    """Provider for PubMed (NCBI E-Utilities) API.

    PubMed is a free resource supporting the search and retrieval of
    biomedical and life sciences literature.

    Rate limit:
    - 3 requests/second without API key
    - 10 requests/second with API key

    Features:
    - Biomedical literature focus
    - MeSH term indexing
    - Clinical query filters
    - LinkOut to full text

    Example:
        >>> config = ProviderConfig(rate_limit=3.0)
        >>> provider = PubMedProvider(config)
        >>> query = Query(text="cancer immunotherapy", year_min=2023)
        >>> for doc in provider.search(query):
        ...     print(doc.title)
    """

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    @property
    def name(self) -> str:
        """Get the provider name.

        Returns:
            Provider name 'pubmed'
        """
        return "pubmed"

    def __init__(self, config: ProviderConfig):
        """Initialize PubMed provider.

        Args:
            config: Provider configuration
        """
        super().__init__(config)

        # Set default rate limit if not specified
        # 3.0 without key, 10.0 with key. Default safe is 3.0.
        if config.rate_limit == 1.0:
            self.config.rate_limit = 10.0 if config.api_key else 3.0
            self.rate_limiter.rate = self.config.rate_limit

        logger.info(f"Initialized PubMed provider (rate_limit={self.config.rate_limit}/s)")

    def search(self, query: Query) -> Iterator[Document]:
        """Execute search on PubMed.

        Uses a 2-step process:
        1. ESearch: Search for terms and retrieve list of UIDs (PMIDs).
        2. EFetch: Retrieve full records for those UIDs.

        Args:
            query: Query object with search parameters

        Yields:
            Document objects matching the query

        Raises:
            ProviderError: On API errors
            RateLimitError: When rate limit exceeded
        """
        # Step 1: ESearch - Get PMIDs
        esearch_params = self._translate_query(query)
        
        # Max results to fetch
        max_results = query.max_results or 1000  # Default cap if not specified
        esearch_params["retmax"] = min(max_results, 10000) # ESearch limit
        esearch_params["usehistory"] = "y" # Use history for large sets

        try:
            esearch_url = f"{self.BASE_URL}/esearch.fcgi"
            esearch_response = self._make_request_xml(esearch_url, params=esearch_params)
            esearch_root = ET.fromstring(esearch_response)
            
            # Check for errors
            error_list = esearch_root.find("ErrorList")
            if error_list is not None:
                phrase_not_found = error_list.find("PhraseNotFound")
                if phrase_not_found is not None:
                    logger.warning(f"PubMed phrase not found: {phrase_not_found.text}")
                    return

            # Get WebEnv and QueryKey for history (if available)
            webenv = esearch_root.findtext("WebEnv")
            query_key = esearch_root.findtext("QueryKey")
            count = int(esearch_root.findtext("Count", "0"))
            
            # If no history, extract ID list directly
            id_list = [id_elem.text for id_elem in esearch_root.findall(".//IdList/Id")]
            
            logger.info(f"PubMed found {count} results")
            
            if count == 0:
                return

        except Exception as e:
            logger.error(f"PubMed search failed: {e}")
            raise ProviderError(self.name, f"ESearch failed: {e}")

        # Step 2: EFetch - Get Details in batches
        # PubMed allows fetching multiple IDs at once. Recommended batch size ~200.
        batch_size = 200
        total_fetched = 0
        
        # If we used history
        if webenv and query_key:
            # Iterate through history
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
            # Use explicit ID list (for small result sets)
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
        """Fetch a batch of records and yield Documents.
        
        Args:
            params: EFetch parameters
            
        Yields:
            Document objects
        """
        efetch_url = f"{self.BASE_URL}/efetch.fcgi"
        try:
            response_xml = self._make_request_xml(efetch_url, params=params)
            root = ET.fromstring(response_xml)
            
            # Process PubmedArticle elements
            articles = root.findall(".//PubmedArticle")
            for article in articles:
                doc = self._normalize_response(article)
                if doc:
                    yield doc
                    
        except Exception as e:
            logger.error(f"PubMed fetch batch failed: {e}")
            # Don't raise here, try to continue with next batch if possible? 
            # Or re-raise to stop. Usually safer to log and skip.
            pass

    def _translate_query(self, query: Query) -> Dict[str, Any]:
        """Translate Query to PubMed ESearch parameters.

        Args:
            query: Query object

        Returns:
            Dictionary of ESearch parameters
        """
        params = {
            "db": "pubmed",
            "term": query.text,
            "retmode": "xml"
        }
        
        # Add filters to term
        filters = []
        if query.year_min:
            filters.append(f"{query.year_min}[Date - Publication]")
        if query.year_max:
            # Range query syntax: YYYY/MM/DD:YYYY/MM/DD[dp]
            # If only min and max are year, we can try range or AND logic
            # PubMed handles ranges like: 2020:2024[dp]
            pass 
            
        # Refine date filtering
        # Ideally, we rewrite 'term' to include date range if present
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
        """Convert PubMed XML element to Document.

        Args:
            element: xml.etree.ElementTree.Element representing PubmedArticle

        Returns:
            Document object or None
        """
        try:
            medline = element.find("MedlineCitation")
            article = medline.find("Article") if medline is not None else None
            
            if article is None:
                return None

            # Title
            title = article.findtext("ArticleTitle")
            if not title:
                return None

            # Abstract
            abstract_elem = article.find("Abstract")
            abstract = ""
            if abstract_elem is not None:
                # Combine multiple AbstractText parts if present
                texts = abstract_elem.findall("AbstractText")
                if texts:
                    abstract = " ".join(t.text for t in texts if t.text)
                else:
                    # Fallback for single text node?
                    # usually AbstractText is present
                    pass

            # Authors
            authors = []
            author_list = article.find("AuthorList")
            if author_list is not None:
                for au in author_list.findall("Author"):
                    last = au.findtext("LastName")
                    fore = au.findtext("ForeName")
                    initials = au.findtext("Initials")
                    
                    # Identifiers (ORCID)
                    orcid = None
                    for id_node in au.findall("Identifier"):
                        if id_node.get("Source") == "ORCID":
                            orcid = id_node.text
                            # clean url prefix
                            if orcid and "orcid.org/" in orcid:
                                orcid = orcid.split("orcid.org/")[-1]
                    
                    if last:
                        authors.append(Author(family_name=last, given_name=fore, orcid=orcid))

            # Year
            # Priority: Journal/JournalIssue/PubDate
            # Fallback: ArticleDate
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
                    # Sometimes MedlineDate is used "2023 Jan-Feb"
                    medline_date = pub_date.findtext("MedlineDate")
                    if medline_date:
                        # Extract first 4 digits
                        import re
                        match = re.search(r"\d{4}", medline_date)
                        if match:
                            year = int(match.group(0))

            # Venue
            venue = article.findtext("Journal/Title")
            
            # IDs
            pmid = medline.findtext("PMID")
            doi = None
            # Scan ELocationID or PubmedData/ArticleIdList
            for eloc in article.findall("ELocationID"):
                if eloc.get("EIdType") == "doi":
                    doi = eloc.text
            
            # If not in ELocationID, check PubmedData
            if not doi:
                article_ids = element.find("PubmedData/ArticleIdList")
                if article_ids is not None:
                    for aid in article_ids.findall("ArticleId"):
                        if aid.get("IdType") == "doi":
                            doi = aid.text
                            break

            # URL
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None

            # External IDs
            external_ids = ExternalIds(
                pubmed_id=pmid,
                doi=doi
            )

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
                # cited_by_count not readily available in standard efetch xml without extra calls
            )

        except Exception as e:
            logger.error(f"Failed to normalize PubMed article: {e}")
            return None

    def _make_request_xml(self, url: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Make HTTP request and return XML text (helper).
        
        Using the base class logic but handling XML text return.
        """
        import requests
        
        # Rate limit
        if not self.rate_limiter.wait_for_token(timeout=30):
            from nexus.utils.exceptions import RateLimitError
            raise RateLimitError(self.name, "Rate limit timeout for PubMed")

        headers = {
            "User-Agent": f'SimpleSLR/1.0 ({self.config.mailto or ""})',
        }

        try:
            response = requests.get(url, params=params, headers=headers, timeout=self.config.timeout)
            response.raise_for_status()
            return response.text
        except Exception as e:
            from nexus.utils.exceptions import NetworkError
            raise NetworkError(self.name, f"Request failed: {e}")
