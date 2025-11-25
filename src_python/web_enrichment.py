"""
Web Enrichment Service
Searches the internet for missing company information (address, country) when data is incomplete.
"""

import re
import requests
from typing import Dict, Optional, Tuple
from logger import logger
import time


class WebEnrichmentService:
    """Searches web for missing company information"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.timeout = 10
    
    def enrich_company_data(self, company_name: str, current_address: str = "", current_country: str = "") -> Dict[str, str]:
        """
        Search web for company address and country if missing.
        
        Args:
            company_name: Company name to search
            current_address: Current address (may be empty)
            current_country: Current country (may be empty)
        
        Returns:
            Dict with enriched 'address' and 'country' fields
        """
        if not company_name or company_name.strip() in ["-", ""]:
            return {"address": current_address, "country": current_country}
        
        # Skip if we already have both
        if current_address and len(current_address) > 10 and current_country:
            return {"address": current_address, "country": current_country}
        
        logger.info(f"🌐 Web enrichment: Searching for '{company_name}'")
        
        try:
            # Try DuckDuckGo Instant Answer API (no API key needed)
            enriched = self._search_duckduckgo(company_name)
            
            if enriched["address"] or enriched["country"]:
                logger.info(f"✅ Found: {enriched['country']} - {enriched['address'][:50]}...")
                return {
                    "address": enriched["address"] or current_address,
                    "country": enriched["country"] or current_country
                }
        except Exception as e:
            logger.warning(f"Web enrichment failed: {e}")
        
        # Return original if search failed
        return {"address": current_address, "country": current_country}
    
    def _search_duckduckgo(self, company_name: str) -> Dict[str, str]:
        """
        Use DuckDuckGo Instant Answer API to find company info.
        Free, no API key required.
        """
        result = {"address": "", "country": ""}
        
        try:
            # DuckDuckGo Instant Answer API
            url = "https://api.duckduckgo.com/"
            params = {
                "q": f"{company_name} address headquarters",
                "format": "json",
                "no_redirect": 1,
                "no_html": 1,
                "skip_disambig": 1
            }
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            # Extract from Abstract or Infobox
            abstract = data.get("Abstract", "")
            infobox = data.get("Infobox", {})
            
            # Try to extract address from abstract
            if abstract:
                address = self._extract_address_from_text(abstract)
                if address:
                    result["address"] = address
                
                country = self._extract_country_from_text(abstract)
                if country:
                    result["country"] = country
            
            # Try infobox (structured data)
            if isinstance(infobox, dict):
                for item in infobox.get("content", []):
                    if isinstance(item, dict):
                        label = item.get("label", "").lower()
                        value = item.get("value", "")
                        
                        if "headquarters" in label or "location" in label or "address" in label:
                            if value and not result["address"]:
                                result["address"] = self._clean_text(value)
                        
                        if "country" in label:
                            if value and not result["country"]:
                                result["country"] = self._clean_text(value)
            
            # Fallback: Try RelatedTopics
            if not result["address"] and not result["country"]:
                for topic in data.get("RelatedTopics", []):
                    if isinstance(topic, dict):
                        text = topic.get("Text", "")
                        if text:
                            if not result["address"]:
                                result["address"] = self._extract_address_from_text(text)
                            if not result["country"]:
                                result["country"] = self._extract_country_from_text(text)
                            
                            if result["address"] and result["country"]:
                                break
        
        except Exception as e:
            logger.debug(f"DuckDuckGo search error: {e}")
        
        return result
    
    def _extract_address_from_text(self, text: str) -> str:
        """Extract address from text using patterns"""
        if not text:
            return ""
        
        # Pattern: "headquarters in [location]" or "located in [location]"
        patterns = [
            r"headquarters?\s+(?:in|at)\s+([^.,]+(?:,\s*[^.,]+){1,3})",
            r"located\s+(?:in|at)\s+([^.,]+(?:,\s*[^.,]+){1,3})",
            r"based\s+(?:in|at)\s+([^.,]+(?:,\s*[^.,]+){1,3})",
            r"office\s+(?:in|at)\s+([^.,]+(?:,\s*[^.,]+){1,3})",
            r"(?:address|Address):\s*([^.]+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                address = match.group(1).strip()
                # Clean up
                address = re.sub(r"\s+", " ", address)
                if len(address) > 15:  # Minimum reasonable address length
                    return address
        
        return ""
    
    def _extract_country_from_text(self, text: str) -> str:
        """Extract country from text"""
        if not text:
            return ""
        
        # List of common countries
        countries = [
            "United States", "USA", "Turkey", "Türkiye", "United Kingdom", "UK",
            "Germany", "France", "Italy", "Spain", "Netherlands", "Belgium",
            "Sweden", "Norway", "Denmark", "Finland", "Poland", "Switzerland",
            "Austria", "Ireland", "Portugal", "Greece", "Czech Republic",
            "India", "China", "Japan", "South Korea", "Singapore", "Malaysia",
            "Australia", "New Zealand", "Canada", "Brazil", "Mexico", "Argentina",
            "Russia", "Ukraine", "Kazakhstan", "UAE", "Saudi Arabia", "Egypt",
            "Israel", "Estonia", "Latvia", "Lithuania", "Romania", "Bulgaria"
        ]
        
        text_lower = text.lower()
        
        for country in countries:
            if country.lower() in text_lower:
                # Normalize variants
                if country in ["USA", "United States"]:
                    return "United States"
                elif country in ["UK", "United Kingdom"]:
                    return "United Kingdom"
                elif country in ["Türkiye", "Turkey"]:
                    return "Turkey"
                else:
                    return country
        
        return ""
    
    def _clean_text(self, text: str) -> str:
        """Clean extracted text"""
        if not text:
            return ""
        
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text)
        # Remove leading/trailing punctuation
        text = text.strip(" .,;")
        
        return text


# Global instance
enrichment_service = WebEnrichmentService()


def enrich_missing_data(company_name: str, address: str, country: str) -> Tuple[str, str]:
    """
    Convenience function to enrich missing address/country.
    
    Returns:
        Tuple[address, country]
    """
    if not company_name or company_name.strip() in ["-", ""]:
        return address, country
    
    # Only enrich if data is missing or insufficient
    needs_enrichment = False
    if not address or len(address.strip()) < 10:
        needs_enrichment = True
    if not country or country.strip() in ["", "Unknown"]:
        needs_enrichment = True
    
    if not needs_enrichment:
        return address, country
    
    try:
        enriched = enrichment_service.enrich_company_data(company_name, address, country)
        return enriched.get("address", address), enriched.get("country", country)
    except Exception as e:
        logger.error(f"Enrichment error: {e}")
        return address, country


if __name__ == "__main__":
    # Test
    import sys
    
    if len(sys.argv) > 1:
        company = " ".join(sys.argv[1:])
        print(f"Searching for: {company}")
        result = enrichment_service.enrich_company_data(company)
        print(f"Address: {result['address']}")
        print(f"Country: {result['country']}")
    else:
        # Test cases
        test_companies = [
            "Microsoft Corporation",
            "Turkcell",
            "Nokia",
        ]
        
        for company in test_companies:
            print(f"\n{'='*60}")
            print(f"Testing: {company}")
            result = enrichment_service.enrich_company_data(company)
            print(f"Address: {result['address']}")
            print(f"Country: {result['country']}")
            time.sleep(2)  # Rate limiting
