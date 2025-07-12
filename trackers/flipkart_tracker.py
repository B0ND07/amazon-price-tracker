"""Flipkart Price Tracker

This module provides the FlipkartPriceTracker class which implements price tracking
functionality specifically for Flipkart products.
"""

"""Flipkart Price Tracker

This module provides the FlipkartPriceTracker class which implements price tracking
functionality specifically for Flipkart products with anti-scraping measures.
"""

import logging
import re
import time
import random
import json
from typing import Dict, Any, Optional, Tuple, List, Union
from urllib.parse import urljoin, urlparse, parse_qs
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base import PriceTracker

logger = logging.getLogger(__name__)

# Common user agents to rotate
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

class FlipkartPriceTracker(PriceTracker):
    """Price tracker for Flipkart products with anti-scraping measures.
    
    This class implements the price tracking functionality specifically for Flipkart,
    including URL validation, price extraction, and stock status detection.
    It includes various anti-scraping measures to avoid detection.
    """
    
    # Common Flipkart domain variations
    FLIPKART_DOMAINS = [
        'flipkart.com',
        'www.flipkart.com',
        'dl.flipkart.com',
        'www.flipkart.in',
        'flipkart.in'
    ]
    
    def __init__(self, email: str = None, password: str = None, max_retries: int = 3, delay_range: tuple = (1, 3)):
        """Initialize the Flipkart price tracker.
        
        Args:
            email: Email for notifications (unused, kept for compatibility)
            password: Password for email (unused, kept for compatibility)
            max_retries: Maximum number of retries for failed requests
            delay_range: Tuple of (min, max) delay between requests in seconds
        """
        super().__init__()
        # Store email and password (not used currently but kept for compatibility)
        self.email = email
        self.password = password
        
        # Ensure max_retries is an integer
        self.max_retries = int(max_retries) if max_retries is not None else 3
        
        # Ensure delay_range is a valid tuple of numbers
        try:
            self.delay_range = (float(delay_range[0]), float(delay_range[1]))
        except (TypeError, IndexError, ValueError):
            self.delay_range = (1.0, 3.0)
            
        self._setup_session()
    
    def _setup_session(self) -> None:
        """Set up the requests session with retry logic and headers."""
        # Configure retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        
        # Create a session with retry
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        self.session.headers.update(self._get_random_headers())
    
    def _get_random_headers(self) -> Dict[str, str]:
        """Get random headers to avoid detection.
        
        Returns:
            Dict of HTTP headers
        """
        return {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'TE': 'trailers',
            'DNT': '1',
            'Referer': 'https://www.flipkart.com/'
        }
    
    def _random_delay(self) -> None:
        """Add a random delay between requests to avoid rate limiting."""
        delay = random.uniform(*self.delay_range)
        time.sleep(delay)
        
    def _update_headers(self) -> None:
        """Update the session headers with a new random user agent."""
        self.session.headers.update(self._get_random_headers())
    
    def is_valid_url(self, url: str) -> bool:
        """Check if the URL is a valid Flipkart product URL.
        
        Args:
            url: URL to validate
            
        Returns:
            bool: True if valid Flipkart product URL
            
        Examples:
            >>> tracker = FlipkartPriceTracker()
            >>> tracker.is_valid_url("https://www.flipkart.com/samsung-galaxy-s23-ultra-5g/p/itm1234")
            True
            >>> tracker.is_valid_url("https://dl.flipkart.com/s/!KteybNNNN")
            True
            >>> tracker.is_valid_url("https://example.com")
            False
        """
        if not url or not isinstance(url, str):
            return False
            
        try:
            parsed_url = urlparse(url)
            
            # Check domain
            domain = parsed_url.netloc.lower()
            is_flipkart_domain = any(flipkart_domain in domain 
                                   for flipkart_domain in self.FLIPKART_DOMAINS)
            
            if not is_flipkart_domain:
                return False
                
            # For short URLs (like dl.flipkart.com/s/...), we'll let them through
            # and handle the redirection in the get_product_info method
            if domain == 'dl.flipkart.com' and parsed_url.path.startswith('/s/'):
                return True
                
            # Check path for product identifiers
            path = parsed_url.path.lower()
            is_product_path = any(x in path for x in ['/p/', '/product/'])
            
            # Check for excluded paths
            excluded_paths = ['/cart', '/account/login', '/account/register', '/checkout']
            is_excluded = any(path.endswith(x) for x in excluded_paths)
            
            return is_product_path and not is_excluded
            
        except Exception as e:
            logger.warning(f"Error validating URL {url}: {e}")
            return False
    
    def get_product_info(self, url: str) -> Dict[str, Any]:
        """Get product information from Flipkart with retry logic and anti-scraping measures.
        
        Args:
            url: Product URL to fetch information from
            
        Returns:
            Dict containing product information with keys:
            - title: Product title
            - price: Current price (float)
            - original_price: Original/MRP price (float) if available
            - discount: Discount percentage if available
            - coupon: Coupon/discount text if available
            - in_stock: Boolean indicating if product is in stock
            - url: Canonical product URL
            - image_url: URL of the product image if available
            - last_updated: Timestamp of when the information was fetched
            
        Raises:
            ValueError: If URL is invalid or product not found
            Exception: For other errors during fetching/parsing
        """
        if not self.is_valid_url(url):
            raise ValueError("Invalid Flipkart product URL")
        
        # For short URLs, we'll get the final URL after redirects
        parsed_url = urlparse(url)
        if parsed_url.netloc == 'dl.flipkart.com' and parsed_url.path.startswith('/s/'):
            try:
                # Make a HEAD request to get the final URL with a shorter timeout
                response = requests.head(
                    url,
                    headers=self._get_random_headers(),
                    allow_redirects=True,
                    timeout=5  # Shorter timeout for URL resolution
                )
                clean_url = response.url
                logger.debug(f"Resolved short URL {url} to {clean_url}")
                
                # If we got redirected to the home page, the short URL might be invalid
                if 'flipkart.com' in clean_url and not any(x in clean_url for x in ['/p/', '/product/']):
                    logger.warning(f"Short URL {url} redirected to home page, might be invalid")
                    raise ValueError("Invalid product URL - redirected to home page")
                    
            except requests.Timeout:
                logger.warning(f"Timeout while resolving short URL {url}, will try with full request")
                clean_url = url  # Fall back to original URL
            except Exception as e:
                logger.warning(f"Failed to resolve short URL {url}: {e}")
                clean_url = url  # Fall back to original URL
        else:
            # Normalize URL (remove tracking parameters, fragments, etc.)
            clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
        
        for attempt in range(self.max_retries + 1):
            try:
                # Add a random delay between requests
                self._random_delay()
                
                # Update headers with a new user agent
                self._update_headers()
                
                logger.debug(f"Attempt {attempt + 1}/{self.max_retries + 1} - Fetching URL: {clean_url}")
                
                # Make the request
                response = self.session.get(
                    clean_url,
                    timeout=15,
                    allow_redirects=True,
                    headers={
                        'Referer': 'https://www.flipkart.com/',
                        'DNT': '1',
                    }
                )
                
                # Check for rate limiting or blocking
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 30))
                    logger.warning(f"Rate limited. Waiting {retry_after} seconds before retry...")
                    time.sleep(retry_after)
                    continue
                    
                response.raise_for_status()
                
                # Check if we got redirected to a different page (e.g., product not found)
                if response.url != clean_url and not self.is_valid_url(response.url):
                    if 'captcha' in response.url.lower():
                        raise ValueError("CAPTCHA encountered. Please try again later.")
                    raise ValueError("Product not found or invalid URL")
                
                # Parse the response
                soup = BeautifulSoup(response.text, 'lxml')
                
                # Check for CAPTCHA page
                if any(tag.name == 'title' and 'captcha' in tag.text.lower() for tag in soup.find_all('title')):
                    raise ValueError("CAPTCHA encountered. Please try again later.")
                
                break
                
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries:
                    logger.error(f"Failed to fetch product info after {self.max_retries} attempts: {e}")
                    raise
                
                wait_time = (2 ** attempt) + random.random()  # Exponential backoff with jitter
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time:.1f} seconds...")
                time.sleep(wait_time)
        else:
            raise Exception(f"Failed to fetch product info after {self.max_retries + 1} attempts")
            
        try:
            # Extract product information
            title = self._extract_title(soup)
            price_info = self._extract_price_info(soup)
            in_stock = self._check_stock_status(soup)
            image_url = self._extract_image_url(soup)
            
            # Build result dictionary
            result = {
                'title': title,
                'price': price_info.get('current_price', 0),
                'original_price': price_info.get('original_price'),
                'discount': price_info.get('discount'),
                'coupon': price_info.get('coupon'),
                'in_stock': in_stock,
                'url': clean_url,
                'image_url': image_url,
                'last_updated': datetime.utcnow().isoformat(),
                'store': 'flipkart'
            }
            
            logger.info(f"Successfully fetched product info: {title}")
            logger.debug(f"Extracted product info: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing product info from {url}: {str(e)}")
            raise ValueError(f"Failed to parse product information: {str(e)}")
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract product title from the page.
        
        Args:
            soup: BeautifulSoup object of the product page
            
        Returns:
            Extracted product title or 'Unknown Product' if not found
        """
        # Try multiple selectors in order of preference
        title_selectors = [
            ('span', {'class': 'B_NuCI'}),  # Main title
            ('h1', {'class': 'yhB1nd'}),    # Alternative title
            ('h1', {'class': 'VU-ZEz'}),    # Another alternative
            ('span', {'class': 'VU-ZEz'}),  # Sometimes in span
            ('h1', {}),                     # Generic h1 as last resort
            ('title', {})                   # Fallback to page title
        ]
        
        for tag, attrs in title_selectors:
            element = soup.find(tag, **attrs)
            if element:
                title = element.get_text(strip=True)
                # Skip generic or empty titles
                if title and title.lower() not in ('flipkart', 'online shopping'):
                    return title
        
        return 'Unknown Product'
    
    def _extract_price_info(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract price information from the product page.
        
        Args:
            soup: BeautifulSoup object of the product page
            
        Returns:
            Dict with price information (current_price, original_price, discount, coupon)
        """
        result = {
            'current_price': 0,
            'original_price': None,
            'discount': None,
            'coupon': None
        }
        
        try:
            # Try to find the price in the main price container
            price_container = soup.find('div', {'class': '_30jeq3 _16Jk6d'}) or \
                            soup.find('div', {'class': '_30jeq3'}) or \
                            soup.find('div', {'class': '_1vC4OE _3qQ9m1'}) or \
                            soup.find('div', {'class': '_30jeq3 _16Jk6d _2tVp4j'})  # Another common price class
            
            if price_container:
                price_text = price_container.get_text(strip=True)
                result['current_price'] = self._extract_price(price_text)
                
                # If we found a price, try to find the original price (striked out)
                if result['current_price'] > 0:
                    original_price_elem = (
                        soup.find('div', {'class': '_3I9_wc _2p6lqe'}) or  # New UI
                        soup.find('div', {'class': '_3I9_wc _2p6lqe _30jeq3'}) or
                        soup.find('div', {'class': '_3auQ3N _1POkHg'}) or  # Old UI
                        soup.find('div', {'class': '_3I9_wc _2p6lqe'})    # Another variant
                    )
                    
                    if original_price_elem:
                        original_price_text = original_price_elem.get_text(strip=True)
                        result['original_price'] = self._extract_price(original_price_text)
                    
                    # Try to find discount percentage
                    discount_elem = (
                        soup.find('div', {'class': '_3Ay6Sb'}) or  # New UI
                        soup.find('div', {'class': 'VGWI6T'}) or    # Another variant
                        soup.find('span', {'class': '_3Ay6Sb'}) or  # Sometimes in span
                        soup.find('div', {'class': '_3I9_wc'}).find_next_sibling('div')  # Next to price
                        if soup.find('div', {'class': '_3I9_wc'}) else None
                    )
                    
                    if discount_elem:
                        discount_text = discount_elem.get_text(strip=True)
                        # Extract percentage (e.g., "10% off" -> 10)
                        match = re.search(r'(\d+)%', discount_text)
                        if match:
                            result['discount'] = int(match.group(1))
                        
                        # If we have a discount but no original price, try to calculate it
                        if result['discount'] and not result['original_price'] and result['current_price']:
                            try:
                                discount_factor = 1 - (result['discount'] / 100)
                                result['original_price'] = round(result['current_price'] / discount_factor, 2)
                            except (ZeroDivisionError, TypeError):
                                pass
            
            # If we still don't have a price, try alternative selectors
            if result['current_price'] <= 0:
                # Try to find price in script tags (common for dynamic content)
                script_tags = soup.find_all('script', type='application/ld+json')
                for script in script_tags:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict) and 'offers' in data and 'price' in data['offers']:
                            result['current_price'] = float(data['offers']['price'])
                            break
                        elif isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict) and 'offers' in item and 'price' in item['offers']:
                                    result['current_price'] = float(item['offers']['price'])
                                    break
                    except (json.JSONDecodeError, (AttributeError, KeyError, ValueError)):
                        continue
            
            # Original price (MRP)
            original_price_elem = (
                soup.find('div', {'class': '_3I9_wc _2p6lqe'}) or  # New UI
                soup.find('div', {'class': '_3auQ3N _1POkHg'})     # Old UI
            )
            
            if original_price_elem:
                original_price_str = original_price_elem.get_text(strip=True)
                result['original_price'] = self._extract_price(original_price_str)
            
            # Discount percentage
            discount_elem = soup.find('div', {'class': '_3Ay6Sb'}) or soup.find('div', {'class': 'VGWI6T'})
            if discount_elem:
                discount_text = discount_elem.get_text(strip=True)
                # Extract percentage (e.g., "10% off" -> 10)
                match = re.search(r'(\d+)%', discount_text)
                if match:
                    result['discount'] = int(match.group(1))
                
                # If we have a discount but no original price, try to calculate it
                if result['discount'] and result['current_price'] and not result['original_price']:
                    try:
                        discount_factor = 1 - (result['discount'] / 100)
                        result['original_price'] = round(result['current_price'] / discount_factor, 2)
                    except (ZeroDivisionError, TypeError):
                        pass
            
            # Coupon/discount information
            coupon_elem = (
                soup.find('div', {'class': '_3D89xM'}) or  # Coupon text
                soup.find('div', {'class': '_2TpdnF'})     # Bank offers
            )
            
            if coupon_elem:
                result['coupon'] = coupon_elem.get_text(strip=True)
                
        except Exception as e:
            logger.warning(f"Error extracting price info: {e}")
        
        return result
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if the product is in stock.
        
        Args:
            soup: BeautifulSoup object of the product page
            
        Returns:
            bool: True if in stock, False otherwise
        """
        # Check for out of stock indicators
        out_of_stock_indicators = [
            ('div', {'class': '_9aUb2-'}),  # Out of stock message
            ('button', {'class': '_2KpZ6l _2U9uOA _3v1-ww _3W_3L- disabled'}),  # Disabled Add to Cart
            ('button', {'class': '_2KpZ6l _2U9uOA _3v1-ww _3W_3L-'}),  # Out of stock button
            ('div', {'class': '_2sKwjB'})  # Notify me when available
        ]
        
        for tag, attrs in out_of_stock_indicators:
            if soup.find(tag, attrs):
                return False
        
        # Check for in-stock indicators
        in_stock_indicators = [
            ('button', {'class': '_2KpZ6l _2U9uOA _3v1-ww'}),  # Add to Cart button
            ('button', {'class': '_2KpZ6l _2U9uOA _3v1-ww _3W_3L-'}),  # Add to Cart button (variant)
            ('div', {'class': '_16FRp0'})  # Available offers
        ]
        
        for tag, attrs in in_stock_indicators:
            if soup.find(tag, attrs):
                return True
        
        # Default to in-stock if no clear indicators found
        return True
    
    def _extract_image_url(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract the product image URL.
        
        Args:
            soup: BeautifulSoup object of the product page
            
        Returns:
            URL of the product image or None if not found
        """
        try:
            # Try to find the main product image
            img_elem = (
                soup.find('img', {'class': '_396cs4'}) or  # New UI
                soup.find('img', {'class': '_1Nyybr'}) or  # Alternative
                soup.find('div', {'class': 'CXW8mj'}).find('img') if soup.find('div', {'class': 'CXW8mj'}) else None  # Container with img
            )
            
            if img_elem and img_elem.get('src'):
                return img_elem['src']
                
            # Try background image in style attribute
            container = soup.find('div', {'class': '_3BTv9X'}) or soup.find('div', {'class': 'q6DClP'})
            if container and container.get('style'):
                # Extract URL from style="background-image:url('...')
                match = re.search(r"url\('([^']+)'\)", container['style'])
                if match:
                    return match.group(1)
                    
        except Exception as e:
            logger.debug(f"Error extracting image URL: {e}")
            
        return None
