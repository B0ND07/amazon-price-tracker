"""Amazon Price Tracker

This module provides the AmazonPriceTracker class which implements price tracking
functionality specifically for Amazon products with anti-scraping measures.
"""

import logging
import time
import random
import json
import re
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

class AmazonPriceTracker(PriceTracker):
    """Price tracker for Amazon products with anti-scraping measures."""
    
    # Common Amazon domain variations
    AMAZON_DOMAINS = [
        'amazon.com', 'www.amazon.com', 'amazon.in', 'www.amazon.in',
        'amzn.com', 'www.amzn.com', 'amzn.in', 'www.amzn.in'
    ]
    
    def __init__(self, email: str = None, password: str = None, max_retries: int = 3, delay_range: tuple = (1, 3)):
        """Initialize the Amazon price tracker.
        
        Args:
            email: Email for notifications (unused, kept for compatibility)
            password: Password for email (unused, kept for compatibility)
            max_retries: Maximum number of retries for failed requests
            delay_range: Tuple of (min, max) delay between requests in seconds
        """
        super().__init__()
        self.email = email
        self.password = password
        self.max_retries = int(max_retries) if max_retries is not None else 3
        
        try:
            self.delay_range = (float(delay_range[0]), float(delay_range[1]))
        except (TypeError, IndexError, ValueError):
            self.delay_range = (1.0, 3.0)
            
        self._setup_session()
    
    def _setup_session(self) -> None:
        """Set up the requests session with retry logic and headers."""
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update(self._get_random_headers())
    
    def _get_random_headers(self) -> Dict[str, str]:
        """Get random headers to avoid detection."""
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
            'Referer': 'https://www.amazon.com/'
        }
    
    def _random_delay(self) -> None:
        """Add a random delay between requests to avoid rate limiting."""
        delay = random.uniform(*self.delay_range)
        time.sleep(delay)
    
    def _update_headers(self) -> None:
        """Update the session headers with a new random user agent."""
        self.session.headers.update(self._get_random_headers())
    
    def is_valid_url(self, url: str) -> bool:
        """Check if the URL is a valid Amazon product URL.
        
        Args:
            url: URL to validate
            
        Returns:
            bool: True if valid Amazon product URL
            
        Examples:
            >>> tracker = AmazonPriceTracker()
            >>> tracker.is_valid_url("https://www.amazon.in/dp/B0XXXXXX")
            True
            >>> tracker.is_valid_url("https://amzn.in/d/XXXXX")
            True
            >>> tracker.is_valid_url("https://example.com")
            False
        """
        if not url or not isinstance(url, str):
            return False
            
        try:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()
            
            # Check domain
            is_amazon_domain = any(amzn_domain in domain for amzn_domain in self.AMAZON_DOMAINS)
            if not is_amazon_domain and not ('amzn.in' in domain or 'amzn.com' in domain):
                return False
                
            # For short URLs (like amzn.in/...), we'll let them through
            if domain in ('amzn.in', 'amzn.com') and parsed_url.path.startswith(('/d/', '/dp/', '/gp/')):
                return True
                
            # Check path for product identifiers
            path = parsed_url.path.lower()
            is_product_path = any(x in path for x in ['/dp/', '/gp/product/', '/d/', '/product/'])
            
            # Check for excluded paths
            excluded_paths = ['/cart', '/wishlist', '/account/login', '/account/register', '/checkout']
            is_excluded = any(path.endswith(x) for x in excluded_paths)
            
            return is_product_path and not is_excluded
            
        except Exception as e:
            logger.warning(f"Error validating URL {url}: {e}")
            return False
    
    def _extract_price_from_json_ld(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract price from JSON-LD structured data."""
        try:
            # Look for all JSON-LD scripts
            scripts = soup.find_all('script', type='application/ld+json')
            
            # First, try to find the script with the expected product type
            product_data = None
            for script in scripts:
                if not script or not script.string:
                    continue
                
                try:
                    data = json.loads(script.string)
                    
                    # Look for the main product data
                    if isinstance(data, dict) and data.get('@type') in ['Product', 'IndividualProduct']:
                        product_data = data
                        break
                    
                    # Sometimes the product is in a graph array
                    if isinstance(data, dict) and '@graph' in data and isinstance(data['@graph'], list):
                        for item in data['@graph']:
                            if isinstance(item, dict) and item.get('@type') in ['Product', 'IndividualProduct']:
                                product_data = item
                                break
                        if product_data:
                            break
                except:
                    continue
            
            # If we found product data, extract the price
            if product_data and 'offers' in product_data:
                if isinstance(product_data['offers'], list) and product_data['offers']:
                    offer = product_data['offers'][0]
                    price = offer.get('price')
                    if price:
                        return float(price)
                elif isinstance(product_data['offers'], dict):
                    price = product_data['offers'].get('price')
                    if price:
                        return float(price)
            
            # If no specific product data was found, try the first price we can find
            for script in scripts:
                if not script or not script.string:
                    continue
                
                try:
                    data = json.loads(script.string)
                    
                    # Handle different JSON-LD structures
                    if isinstance(data, dict):
                        # Check for direct price property
                        if 'offers' in data:
                            if isinstance(data['offers'], list) and data['offers']:
                                offer = data['offers'][0]
                                price = offer.get('price')
                                if price:
                                    return float(price)
                            elif isinstance(data['offers'], dict):
                                price = data['offers'].get('price')
                                if price:
                                    return float(price)
                        
                        # Sometimes nested in an array
                        if '@graph' in data and isinstance(data['@graph'], list):
                            for item in data['@graph']:
                                if isinstance(item, dict) and 'offers' in item:
                                    if isinstance(item['offers'], list) and item['offers']:
                                        offer = item['offers'][0]
                                        price = offer.get('price')
                                        if price:
                                            return float(price)
                                    elif isinstance(item['offers'], dict):
                                        price = item['offers'].get('price')
                                        if price:
                                            return float(price)
                    elif isinstance(data, list):
                        # Check each item in the array
                        for item in data:
                            if isinstance(item, dict) and 'offers' in item:
                                if isinstance(item['offers'], list) and item['offers']:
                                    offer = item['offers'][0]
                                    price = offer.get('price')
                                    if price:
                                        return float(price)
                                elif isinstance(item['offers'], dict):
                                    price = item['offers'].get('price')
                                    if price:
                                        return float(price)
                except:
                    continue
                    
        except Exception as e:
            logger.debug(f"Error extracting price from JSON-LD: {e}")
        return None
    
    def _extract_price_from_script(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract price from JavaScript data in the page."""
        try:
            # Look for price in the page's JavaScript data, specifically in data elements 
            # that are clearly about the main product
            product_data_scripts = []
            
            # Target price-related scripts
            for script in soup.find_all('script'):
                if not script.string:
                    continue
                    
                script_text = script.string.lower()
                # Filter scripts that are likely to contain main product price
                if any(term in script_text for term in [
                    'priceblock', 
                    'product.price', 
                    'saleprice', 
                    '"price"', 
                    'twister-plus-price',
                    'product-price',
                    'currentprice'
                ]):
                    product_data_scripts.append(script.string)
            
            # Process filtered scripts
            for script_text in product_data_scripts:
                # Amazon often uses these specific patterns for main product price
                price_patterns = [
                    r'"price"\s*:\s*["\']?([\d.,]+)["\']?',  # "price": "123.45"
                    r'"currentPrice"\s*:\s*["\']?([\d.,]+)["\']?',  # "currentPrice": "123.45"
                    r'"listPrice"\s*:\s*["\']?([\d.,]+)["\']?',  # "listPrice": "123.45" 
                    r'"priceAmount"\s*:\s*([\d.,]+)',  # "priceAmount": 123.45
                    r'"dealPrice"\s*:\s*["\']?([\d.,]+)["\']?',  # "dealPrice": "123.45"
                    r'asin\b[^}]+"price"\s*:\s*["\']?([\d.,]+)["\']?'  # Price near ASIN reference
                ]
                
                for pattern in price_patterns:
                    matches = re.search(pattern, script_text)
                    if matches:
                        price_str = matches.group(1).replace(',', '')
                        price = float(price_str)
                        if price > 0:
                            return price
        except (AttributeError, ValueError, TypeError) as e:
            logger.debug(f"Error extracting price from script: {e}")
        return None
    
    def _check_for_captcha(self, soup: BeautifulSoup, response_text: str) -> bool:
        """Check if the response contains a CAPTCHA or bot detection."""
        captcha_indicators = [
            'enter the characters you see below',
            'type the characters you see in this image',
            'robot check',
            'captcha',
            'bot check'
        ]
        
        # Check response text for CAPTCHA indicators
        text_lower = response_text.lower()
        if any(indicator in text_lower for indicator in captcha_indicators):
            return True
            
        # Check for CAPTCHA elements in the HTML
        captcha_elements = soup.find_all(string=re.compile('|'.join(captcha_indicators), re.IGNORECASE))
        if captcha_elements:
            return True
            
        return False
    
    def _extract_asin(self, url: str) -> Optional[str]:
        """Extract the ASIN from an Amazon URL."""
        asin_patterns = [
            r'/dp/([A-Z0-9]{10})(?:/|$)',
            r'/gp/product/([A-Z0-9]{10})(?:/|$)',
            r'/product/([A-Z0-9]{10})(?:/|$)',
            r'/ASIN/([A-Z0-9]{10})(?:/|$)',
            r'asin=([A-Z0-9]{10})(?:&|$)'
        ]
        
        for pattern in asin_patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def _verify_product_page(self, soup: BeautifulSoup, url: str) -> bool:
        """Verify we're on the correct product page, not a search or related items page."""
        # Extract expected ASIN from the URL
        expected_asin = self._extract_asin(url)
        if not expected_asin:
            return True  # Can't verify, assume it's correct
        
        # Check for search results indicators
        search_indicators = [
            soup.find('div', {'id': 'search'}),
            soup.find('div', {'id': 'searchTemplate'}),
            soup.find('span', {'id': 's-result-count'}),
            soup.find('h1', {'class': 'a-size-base s-desktop-toolbar'}),
            soup.find('div', {'class': 's-search-results'})
        ]
        
        if any(indicator for indicator in search_indicators):
            logger.warning(f"Found search page indicators for URL: {url}")
            return False  # We're on a search page, not a product page
        
        # Check for "product not found" or "page not found" indicators
        not_found_indicators = [
            'page not found',
            'product not found',
            'we couldn\'t find that page',
            'looking for something?',
            'sorry, we just need to make sure you\'re not a robot'
        ]
        
        page_text = soup.get_text().lower()
        if any(indicator in page_text for indicator in not_found_indicators):
            logger.warning(f"Found 'not found' indicators for URL: {url}")
            return False
        
        # Check if we're on a category page
        category_indicators = [
            soup.find('div', {'id': 'departments'}),
            soup.find('div', {'id': 'leftNav'}),
            soup.find('div', {'id': 'refinements'})
        ]
        
        if any(indicator for indicator in category_indicators) and not soup.find('div', {'id': 'dp'}):
            logger.warning(f"Found category page indicators for URL: {url}")
            return False
        
        # Positive indicators that we're on a product page
        product_indicators = [
            soup.find('div', {'id': 'dp'}),
            soup.find('div', {'id': 'prodDetails'}),
            soup.find('div', {'id': 'detail-bullets'}),
            soup.find('div', {'id': 'centerCol'}),
            soup.find('div', {'id': 'title_feature_div'})
        ]
        
        if any(indicator for indicator in product_indicators):
            # Try to find ASIN on the page to verify it's the correct product
            page_asin = None
            
            # Method 1: Check data-asin attribute on elements
            elements_with_asin = soup.find_all(attrs={"data-asin": True})
            for elem in elements_with_asin:
                if elem.get('data-asin') == expected_asin:
                    page_asin = elem.get('data-asin')
                    break
            
            # Method 2: Look for ASIN in scripts
            if not page_asin:
                for script in soup.find_all('script'):
                    if script.string and expected_asin in script.string:
                        page_asin = expected_asin
                        break
            
            # Method 3: Check for ASIN in the product details section
            if not page_asin:
                detail_sections = soup.find_all(['div', 'ul', 'table'], class_=['detail', 'details', 'product-details', 'productDetails'])
                for section in detail_sections:
                    if expected_asin in section.get_text():
                        page_asin = expected_asin
                        break
            
            # Method 4: Look for ASIN in the URL of canonical link or other meta elements
            if not page_asin:
                canonical_link = soup.find('link', {'rel': 'canonical'})
                if canonical_link and 'href' in canonical_link.attrs and expected_asin in canonical_link['href']:
                    page_asin = expected_asin
            
            # If we found an ASIN on the page, verify it matches the expected one
            if page_asin:
                return page_asin == expected_asin
        
        # If we're here, we couldn't definitively say it's wrong, so assume it's right
        # but log a warning
        logger.warning(f"Could not definitively verify product page for URL: {url}")
        return True
    
    def get_product_info(self, url: str) -> Dict[str, Any]:
        """Get product information from Amazon with retry logic and anti-scraping measures.
        
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
            - store: Store identifier ('amazon')
            
        Raises:
            ValueError: If the URL is invalid or product information cannot be extracted
            requests.exceptions.RequestException: If there's an error making the request
        """
        if not self.is_valid_url(url):
            raise ValueError(f"Invalid Amazon product URL: {url}")
        
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                # Update headers and add random delay
                self._update_headers()
                self._random_delay()
                
                # Make the request
                response = self.session.get(
                    url,
                    headers=self.session.headers,
                    timeout=15,
                    allow_redirects=True
                )
                
                # Check for HTTP errors
                response.raise_for_status()
                
                # Parse the response
                soup = BeautifulSoup(response.text, 'lxml')
                
                # Check for CAPTCHA or bot detection
                if self._check_for_captcha(soup, response.text):
                    logger.warning("CAPTCHA or bot detection triggered. Retrying with new session...")
                    self._setup_session()  # Reset session to get new headers
                    continue
                
                # Verify we're on the correct product page, not a search or similar items page
                if not self._verify_product_page(soup, url):
                    logger.warning(f"Not on the correct product page for URL: {url}. Retrying...")
                    continue
                
                # Extract product title (try multiple selectors)
                title = 'Unknown Product'
                title_selectors = [
                    ('span', {'id': 'productTitle'}),
                    ('h1', {'id': 'title'}),
                    ('h1', {'id': 'productTitle'}),
                    ('h1', {'class': 'a-size-large'}),
                    ('span', {'class': 'a-size-large product-title-word-break'})
                ]
                
                for tag, attrs in title_selectors:
                    elem = soup.find(tag, attrs)
                    if elem and elem.get_text(strip=True):
                        title = elem.get_text(strip=True)
                        break
                
                # Extract price (try multiple methods)
                price = 0.0
                original_price = None
                discount = None
                
                # Method 1: Try structured data (JSON-LD)
                price = self._extract_price_from_json_ld(soup)
                
                # Method 2: Try various price selectors, ensuring we're getting the main product price
                if not price:
                    # Check if we're in the buybox area - this is the most reliable for the current price
                    buybox_containers = [
                        soup.find('div', {'id': 'buybox'}),
                        soup.find('div', {'id': 'buyNew_noncbb'}),
                        soup.find('div', {'id': 'unqualifiedBuyBox'})
                    ]
                    
                    # Filter out None values
                    buybox_containers = [c for c in buybox_containers if c is not None]
                    
                    if buybox_containers:
                        for container in buybox_containers:
                            # Look for specific buybox price elements
                            price_elements = container.select('.a-color-price, .a-size-medium.a-color-price, .a-price')
                            for elem in price_elements:
                                # Look for the price in this element or its children
                                price_elem = elem.select_one('.a-offscreen') or elem
                                if price_elem:
                                    price_text = price_elem.get_text(strip=True)
                                    try:
                                        price = float(re.sub(r'[^\d.]', '', price_text))
                                        if price > 0:
                                            break
                                    except (ValueError, TypeError):
                                        continue
                            
                            if price and price > 0:
                                break
                    
                    # If not found in buybox, check for the main product price wrapper
                    if not price or price <= 0:
                        main_price_containers = [
                            soup.find('div', {'id': 'corePrice_desktop'}),
                            soup.find('div', {'id': 'corePrice_feature_div'}),
                            soup.find('div', {'id': 'corePriceDisplay_desktop_feature_div'}),
                            soup.find('div', {'id': 'price'}),
                            soup.find('div', {'data-feature-name': 'corePrice'})
                        ]
                        
                        # Filter out None values
                        main_price_containers = [c for c in main_price_containers if c is not None]
                        
                        if main_price_containers:
                            # If we found a main price container, search within it for the price
                            for container in main_price_containers:
                                price_selectors = [
                                    ('span', {'class': 'a-price-whole'}),
                                    ('span', {'id': 'priceblock_ourprice'}),
                                    ('span', {'id': 'priceblock_dealprice'}),
                                    ('span', {'class': 'a-offscreen'}),
                                    ('span', {'class': 'a-color-price'}),
                                    ('span', {'class': 'a-price'})
                                ]
                                
                                for tag, attrs in price_selectors:
                                    elem = container.find(tag, attrs)
                                    if elem:
                                        price_text = elem.get_text(strip=True)
                                        try:
                                            price = float(re.sub(r'[^\d.]', '', price_text))
                                            if price > 0:
                                                break
                                        except (ValueError, TypeError):
                                            continue
                                
                                if price and price > 0:
                                    break
                    
                    # If we still don't have a price, try the broader search but with caution
                    if not price or price <= 0:
                        # These IDs are specific to the main product price
                        specific_price_selectors = [
                            ('span', {'id': 'priceblock_ourprice'}),
                            ('span', {'id': 'priceblock_dealprice'}),
                            ('span', {'id': 'priceblock_saleprice'})
                        ]
                        
                        for tag, attrs in specific_price_selectors:
                            elem = soup.find(tag, attrs)
                            if elem:
                                price_text = elem.get_text(strip=True)
                                try:
                                    price = float(re.sub(r'[^\d.]', '', price_text))
                                    if price > 0:
                                        break
                                except (ValueError, TypeError):
                                    continue
                
                # Method 3: Try extracting from scripts
                if not price or price <= 0:
                    price = self._extract_price_from_script(soup)
                
                # Extract original price and discount if available
                original_price_elem = soup.find('span', {'class': 'a-price a-text-price'})
                if original_price_elem:
                    try:
                        original_price_text = original_price_elem.find('span', {'class': 'a-offscreen'}).text
                        original_price = float(re.sub(r'[^\d.]', '', original_price_text))
                        if price and original_price > price:
                            discount = round(((original_price - price) / original_price) * 100, 1)
                    except (AttributeError, ValueError, TypeError):
                        pass
                
                # Check stock status
                in_stock = True
                stock_indicators = [
                    'in stock',
                    'available from these sellers',
                    'in stock soon',
                    'only left in stock',
                    r'only \d+ left in stock'  # Use raw string for correct escaping
                ]
                
                out_of_stock_indicators = [
                    'currently unavailable',
                    'out of stock',
                    'sold out',
                    'unavailable',
                    'not in stock',
                    'temporarily out of stock'
                ]
                
                page_text = soup.get_text().lower()
                
                if any(indicator in page_text for indicator in out_of_stock_indicators):
                    in_stock = False
                
                # Extract image URL if available
                image_url = None
                image_elem = soup.find('img', {'id': 'landingImage'}) or \
                            soup.find('img', {'class': 'a-dynamic-image'})
                if image_elem and 'src' in image_elem.attrs:
                    image_url = image_elem['src']
                
                # Get canonical URL
                canonical_url = url
                canonical_elem = soup.find('link', {'rel': 'canonical'})
                if canonical_elem and 'href' in canonical_elem.attrs:
                    canonical_url = canonical_elem['href']
                
                # Check for coupon
                coupon = None
                coupon_elem = soup.find('div', {'id': 'snsCoupon'}) or \
                            soup.find('div', {'class': 'couponBadge'}) or \
                            soup.find('span', {'class': 'sns-coupon-text'})
                if coupon_elem:
                    coupon = coupon_elem.get_text(strip=True)
                
                return {
                    'title': title,
                    'price': float(price) if price else 0.0,
                    'original_price': float(original_price) if original_price else None,
                    'discount': discount,
                    'coupon': coupon,
                    'in_stock': in_stock,
                    'url': canonical_url,
                    'image_url': image_url,
                    'last_updated': datetime.utcnow().isoformat(),
                    'store': 'amazon'
                }
                
            except requests.exceptions.RequestException as e:
                last_exception = e
                logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt == self.max_retries - 1:
                    raise
                
                # Exponential backoff
                time.sleep((2 ** attempt) + random.random())
                
            except Exception as e:
                last_exception = e
                logger.error(f"Error getting product info (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt == self.max_retries - 1:
                    raise
                
                # Exponential backoff
                time.sleep((2 ** attempt) + random.random())
        
        # If we get here, all retries failed
        error_msg = f"Failed to get product info after {self.max_retries} attempts"
        if last_exception:
            error_msg += f": {str(last_exception)}"
        raise Exception(error_msg)
