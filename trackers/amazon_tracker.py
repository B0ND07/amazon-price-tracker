import logging
import time
import random
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup
from .base import PriceTracker

logger = logging.getLogger(__name__)

class AmazonPriceTracker(PriceTracker):
    """Price tracker for Amazon products."""
    
    def is_valid_url(self, url: str) -> bool:
        """Check if the URL is a valid Amazon product URL.
        
        Args:
            url: URL to validate
            
        Returns:
            bool: True if valid Amazon product URL
        """
        if not url:
            return False
            
        # Check if it's an Amazon domain and has a valid path
        is_amazon_domain = ('amazon.' in url or 'amzn.in' in url)
        has_valid_path = any(path in url for path in ('/dp/', '/gp/', '/d/', '/product/'))
        is_shortened = url.startswith(('http://amzn.in/', 'https://amzn.in/'))
        is_invalid_path = url.endswith(('/cart', '/wishlist', '/account/login', '/account/register'))
        
        return is_amazon_domain and (has_valid_path or is_shortened) and not is_invalid_path
    
    def get_product_info(self, url: str) -> Dict[str, Any]:
        """Get product information from Amazon.
        
        Args:
            url: Product URL
            
        Returns:
            Dict containing product information
            
        Raises:
            Exception: If there's an error fetching or parsing the product page
        """
        if not self.is_valid_url(url):
            raise ValueError("Invalid Amazon product URL")
        
        headers = self._get_random_headers()
        
        try:
            # Add a small delay to avoid being blocked
            time.sleep(random.uniform(1, 3))
            
            response = self.session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Extract product title
            title_elem = (soup.find('span', {'id': 'productTitle'}) or 
                         soup.find('h1', {'id': 'title'}))
            title = title_elem.get_text(strip=True) if title_elem else 'Unknown Product'
            
            # Extract price
            price_elem = (soup.find('span', {'class': 'a-price-whole'}) or 
                         soup.find('span', {'class': 'a-offscreen'}) or
                         soup.find('span', {'id': 'priceblock_ourprice'}))
            
            price_str = price_elem.get_text(strip=True) if price_elem else '0'
            price = self._extract_price(price_str)
            
            # Check for coupon
            coupon = None
            coupon_elem = soup.find('span', {'class': 'couponBadge'})
            if coupon_elem:
                coupon = coupon_elem.get_text(strip=True)
            
            return {
                'title': title,
                'price': price,
                'coupon': coupon,
                'url': url
            }
            
        except Exception as e:
            logger.error(f"Error fetching product info from Amazon: {e}")
            raise
