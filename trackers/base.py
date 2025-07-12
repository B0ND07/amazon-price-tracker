import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import asdict

logger = logging.getLogger(__name__)

class PriceTracker(ABC):
    """Base class for price trackers."""
    
    def __init__(self, email: str = None, password: str = None):
        """Initialize the price tracker.
        
        Args:
            email: Email for notifications (optional)
            password: Password for email (optional)
        """
        self.email = email
        self.password = password
        self.session = self._create_session()
    
    @abstractmethod
    def get_product_info(self, url: str) -> Dict[str, Any]:
        """Get product information from the store.
        
        Args:
            url: Product URL
            
        Returns:
            Dict containing product information (title, price, etc.)
        """
        pass
    
    @abstractmethod
    def is_valid_url(self, url: str) -> bool:
        """Check if a URL is valid for this tracker.
        
        Args:
            url: URL to validate
            
        Returns:
            bool: True if URL is valid for this tracker
        """
        pass
    
    def _create_session(self):
        """Create a requests session with retry logic."""
        import requests
        from requests.adapters import HTTPAdapter
        from requests.packages.urllib3.util.retry import Retry
        
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session
    
    def _get_random_headers(self) -> Dict[str, str]:
        """Get random headers for requests."""
        import random
        
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
        ]
        
        return {
            'Accept-Language': 'en-US,en;q=0.9',
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'DNT': '1',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
        }
    
    def _extract_price(self, price_str: str) -> float:
        """Extract price from string.
        
        Args:
            price_str: Price as string (e.g., "₹12,345.67")
            
        Returns:
            float: Extracted price
        """
        if not price_str:
            return 0.0
            
        import re
        # Remove all non-numeric characters except decimal point
        price_str = re.sub(r'[^\d.]', '', price_str)
        try:
            return float(price_str)
        except (ValueError, TypeError):
            return 0.0
