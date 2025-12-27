"""Amazon Price Tracker

This module provides the AmazonPriceTracker class which implements price tracking
functionality specifically for Amazon products with anti-scraping measures.
"""

import logging
import time
import random
import json
import re
import os
from typing import Dict, Any, Optional, Tuple, List, Union
from urllib.parse import urljoin, urlparse, parse_qs
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Import Selenium components
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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
    
    def __init__(self, email: str = None, password: str = None, max_retries: int = 3, delay_range: tuple = (1, 3), headless: bool = True):
        """Initialize the Amazon price tracker.
        
        Args:
            email: Email for notifications (unused, kept for compatibility)
            password: Password for email (unused, kept for compatibility)
            max_retries: Maximum number of retries for failed requests
            delay_range: Tuple of (min, max) delay between requests in seconds
            headless: Whether to run the browser in headless mode
        """
        super().__init__()
        self.email = email
        self.password = password
        self.max_retries = int(max_retries) if max_retries is not None else 3
        
        try:
            self.delay_range = (float(delay_range[0]), float(delay_range[1]))
        except (TypeError, IndexError, ValueError):
            self.delay_range = (1.0, 3.0)
        
        # Selenium configuration
        self.headless = headless
        self.driver = None
        self.cookies_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'amazon_cookies.json')
        
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.cookies_file), exist_ok=True)
            
        # Set up the regular session for fallback
        self._setup_session()
        
    def __del__(self):
        """Clean up resources when the instance is being destroyed."""
        # Make sure to quit the driver when the instance is deleted
        if hasattr(self, 'driver') and self.driver is not None:
            try:
                self.driver.quit()
                logger.info("Selenium driver closed during cleanup")
            except Exception as e:
                logger.warning(f"Error closing Selenium driver during cleanup: {e}")
    
    def _setup_session(self) -> None:
        """Set up the requests session with retry logic and headers."""
        retry_strategy = Retry(
            total=2,  # More retries at the connection level
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            respect_retry_after_header=True,
            raise_on_status=False  # Don't raise exceptions on status, handle them in code
        )
        
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update(self._get_random_headers())
        
        # Add more realistic cookies to appear like a regular browser
        self.session.cookies.set('session-id', f'sess-{random.randint(100000000, 999999999)}')
        self.session.cookies.set('session-token', f'{random.randbytes(16).hex()}')
        self.session.cookies.set('ubid-main', f'chdr-{random.randint(100000000, 999999999)}')
        self.session.cookies.set('i18n-prefs', 'INR')
        self.session.cookies.set('lc-main', 'en_IN')
        self.session.cookies.set('csm-hit', f'tb:{random.randbytes(8).hex()}+s-{random.randbytes(8).hex()}|{int(time.time())}')
        self.session.cookies.set('session-id-time', str(int(time.time() * 1000)))
        
        # Add additional realistic cookies
        self.session.cookies.set('x-amz-captcha-1', f'{random.randbytes(10).hex()}')
        self.session.cookies.set('x-amz-captcha-2', f'{random.randbytes(10).hex()}')
        
        # Use a country-specific Amazon domain as referer
        referer_domains = ['www.amazon.in', 'amazon.in']
        referer_domain = random.choice(referer_domains)
        self.session.headers.update({'Referer': f'https://{referer_domain}/'})
        
        # Add viewport and screen dimensions to mimic a real browser
        viewport_width = random.choice([1280, 1366, 1440, 1536, 1600, 1920])
        viewport_height = random.choice([720, 768, 800, 900, 1080])
        self.session.headers.update({
            'sec-ch-ua-platform': f'"{random.choice(["Windows", "macOS", "Linux"])}"',
            'sec-ch-ua': f'"Google Chrome";v="{random.randint(90, 120)}", "Chromium";v="{random.randint(90, 120)}"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-viewport-width': f'{viewport_width}',
            'sec-ch-viewport-height': f'{viewport_height}',
            'sec-ch-device-memory': f'{random.choice([4, 8, 16])}'
        })
    
    def _setup_browser(self) -> webdriver.Chrome:
        """Set up and return a Chrome browser instance for Selenium-based scraping.
        
        Returns:
            webdriver.Chrome: Configured Chrome WebDriver instance
        """
        if self.driver is not None:
            try:
                self.driver.quit()
            except:
                pass
        
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")  # New headless mode for Chrome
        
        # Add arguments to make browser less detectable
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")
        options.add_argument("--window-size=1920,1080")  # Set a standard resolution
        
        # Amazon-specific options
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-extensions")
        
        # Disable automation flags
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        # Initialize the Chrome driver
        try:
            # Create a service object using the installed chromedriver
            service = Service('/usr/local/bin/chromedriver')
            driver = webdriver.Chrome(service=service, options=options)
            logger.info("Chrome driver initialized successfully for Amazon")
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver for Amazon: {e}")
            try:
                # Fall back to direct initialization if service fails
                driver = webdriver.Chrome(options=options)
                logger.info("Chrome driver initialized with fallback method for Amazon")
            except Exception as e2:
                logger.error(f"All Chrome driver initialization methods failed for Amazon: {e2}")
                raise
        
        # Additional settings to make selenium less detectable
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Load cookies if they exist
        if os.path.exists(self.cookies_file):
            logger.info("Loading saved Amazon cookies...")
            driver.get("https://www.amazon.in")
            try:
                with open(self.cookies_file, 'r') as f:
                    cookies = json.load(f)
                    for cookie in cookies:
                        driver.add_cookie(cookie)
                logger.info("Amazon cookies loaded successfully")
            except Exception as e:
                logger.warning(f"Error loading Amazon cookies: {e}")
        
        self.driver = driver
        return driver
    
    def _save_cookies(self):
        """Save cookies for future use"""
        try:
            if self.driver:
                cookies = self.driver.get_cookies()
                with open(self.cookies_file, 'w') as f:
                    json.dump(cookies, f)
                logger.info(f"Amazon cookies saved to {self.cookies_file}")
        except Exception as e:
            logger.warning(f"Error saving Amazon cookies: {e}")
    
    def _random_delay(self) -> None:
        """Add a random delay between requests to avoid rate limiting."""
    
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
        
    def _handle_server_error(self, status_code, attempt):
        """Handle server-side errors with special handling for 500 responses.
        
        Args:
            status_code: HTTP status code
            attempt: Current attempt number
            
        Returns:
            bool: True if should retry, False otherwise
        """
        if 500 <= status_code < 600:
            logger.warning(f"Received {status_code} server error on attempt {attempt+1}")
            
            # Longer backoff for server errors
            wait_time = (1 ** attempt) + random.uniform(1, 2)
            logger.info(f"Backing off for {wait_time:.2f}s before retry")
            time.sleep(wait_time)
            
            # For 500 errors, create a completely new session
            if status_code == 500:
                logger.info("Creating fresh session after 500 error")
                self._setup_session()
                
            # Try with a completely different approach for certain status codes
            if status_code in [503, 504]:
                logger.info("Service unavailable, using longer backoff")
                time.sleep(random.uniform(2, 6))  # Much longer wait
                
            return True  # Yes, we should retry
            
        return False  # No special handling needed
    
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
            'bot check',
            'suspicious activity',
            'verify you\'re a human',
            'verify your identity',
            'unusual activity',
            'sorry, we just need to make sure',
            'to discuss automated access',
            'please solve this puzzle',
            'automated queries',
            'important message',
            'we\'ve detected unusual activity',
            'please wait'
        ]
        
        # Check response text for CAPTCHA indicators
        text_lower = response_text.lower()
        if any(indicator in text_lower for indicator in captcha_indicators):
            return True
            
        # Check for CAPTCHA elements in the HTML
        captcha_elements = soup.find_all(string=re.compile('|'.join(captcha_indicators), re.IGNORECASE))
        if captcha_elements:
            return True
            
        # Check for CAPTCHA form elements
        captcha_form = soup.find('form', {'id': 'captcha-form'}) or soup.find('form', {'action': re.compile(r'validateCaptcha|verify')})
        if captcha_form:
            return True
            
        # Check for specific CAPTCHA or verification elements
        if soup.find('img', {'src': re.compile(r'captcha|Captcha')}):
            return True
            
        # Check for page title indications of CAPTCHA or blocking
        title_tag = soup.find('title')
        if title_tag and any(indicator in title_tag.text.lower() for indicator in ['robot', 'captcha', 'verify', 'blocked', 'sorry']):
            return True
            
        # Check for redirects to known CAPTCHA pages
        if soup.find('meta', {'http-equiv': 'refresh'}):
            return True
            
        # Check response length (too short responses often indicate blocking)
        if len(response_text) < 5000:  # Typical product pages are much larger
            # Only consider it a captcha if the page doesn't seem to have product info
            if not soup.find('span', {'id': 'productTitle'}) and not soup.find('div', {'id': 'buyBox'}):
                return True
            
        return False
        
    def _try_api_endpoint(self, url: str) -> Optional[Dict[str, Any]]:
        """Try to get product info using Amazon's internal API endpoints as backup.
        
        Args:
            url: The product URL
            
        Returns:
            Optional[Dict]: Product info if successful, None otherwise
        """
        asin = self._extract_asin(url)
        if not asin:
            return None
            
        logger.info(f"Trying to get product info via API endpoint for ASIN: {asin}")
        
        # Use a different session for API calls
        api_session = requests.Session()
        api_session.headers.update({
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'application/json, text/html',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': f'https://www.amazon.in/dp/{asin}',
            'X-Requested-With': 'XMLHttpRequest'
        })
        
        # Try a more direct approach with Amazon's mobile API or alternatives
        api_endpoints = [
            # Try the mobile API endpoints which are less likely to be blocked
            f'https://www.amazon.in/gp/aw/d/{asin}',
            # Try the standard product page with a simplified URL
            f'https://www.amazon.in/dp/{asin}?psc=1',
            # Try the wishlist API which sometimes returns product info
            f'https://www.amazon.in/hz/wishlist/ls/add-item?asin.1={asin}',
            # Try the customer reviews API
            f'https://www.amazon.in/hz/reviews-render/ajax/reviews/get/ref=cm_cr_arp_d_viewopt_sr?ie=UTF8&asin={asin}'
        ]
        
        for endpoint in api_endpoints:
            try:
                # Add random delay between requests
                time.sleep(random.uniform(1, 2))
                
                # Try different headers for each attempt
                api_session.headers.update({
                    'User-Agent': random.choice(USER_AGENTS),
                    'Referer': f'https://www.amazon.in/s?k={asin}'
                })
                
                response = api_session.get(endpoint, timeout=15)
                if response.status_code == 200:
                    # For HTML responses, extract the product title and price
                    soup = BeautifulSoup(response.text, 'lxml')
                    
                    # Try multiple title selectors
                    title = None
                    title_selectors = [
                        ('span', {'id': 'productTitle'}),
                        ('h1', {'id': 'title'}),
                        ('h1', {'class': 'a-size-large'}),
                        ('span', {'class': 'a-size-large'}),
                        ('h2', {'class': 'a-size-mini'})
                    ]
                    
                    for tag, attrs in title_selectors:
                        elem = soup.find(tag, attrs)
                        if elem and elem.get_text(strip=True):
                            title = elem.get_text(strip=True)
                            break
                    
                    # If we got a title, it's a success
                    if title:
                        # Try to get price, but it's optional
                        price = 0.0
                        price_elems = soup.select('.a-price .a-offscreen, #priceblock_ourprice, .a-color-price')
                        for elem in price_elems:
                            price_text = elem.get_text(strip=True)
                            try:
                                price = float(re.sub(r'[^\d.]', '', price_text))
                                if price > 0:
                                    break
                            except (ValueError, TypeError):
                                continue
                        
                        logger.info(f"Successfully extracted product info via API: {title} - ₹{price}")
                        return {
                            'title': title,
                            'price': price,
                            'url': url,
                            'in_stock': True,  # Assume in stock
                            'store': 'amazon',
                            'last_updated': datetime.utcnow().isoformat()
                        }
            except Exception as e:
                logger.warning(f"Error trying API endpoint {endpoint}: {e}")
                continue
                
        # If we reach here, none of the API endpoints worked
        logger.warning("All API endpoints failed to return product info")
        return None
    
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
        
    def normalize_url(self, url: str) -> str:
        """Normalize Amazon URL to a standard format, resolving short URLs.
        
        Args:
            url: Amazon product URL (can be short form like amzn.in/d/xxx)
            
        Returns:
            str: Normalized Amazon product URL
        """
        if not url:
            return url
            
        # Handle short URLs (like amzn.in/d/xxxx)
        if 'amzn.in' in url or 'amzn.com' in url:
            try:
                # For short URLs, we need to follow redirects to get the canonical URL
                logger.info(f"Resolving short URL: {url}")
                
                # Option 1: Use requests session to follow redirects
                try:
                    response = self.session.head(url, allow_redirects=True, timeout=10)
                    if response.status_code == 200 and 'amazon.in' in response.url:
                        logger.info(f"Resolved short URL to: {response.url}")
                        return response.url
                except Exception as e:
                    logger.warning(f"Failed to resolve short URL with requests: {str(e)}")
                
                # Option 2: Use Selenium if the first method fails
                if self.driver is None:
                    self._setup_browser()
                
                try:
                    self.driver.get(url)
                    time.sleep(2)  # Wait for redirect
                    final_url = self.driver.current_url
                    logger.info(f"Resolved short URL using Selenium to: {final_url}")
                    return final_url
                except Exception as e:
                    logger.warning(f"Failed to resolve short URL with Selenium: {str(e)}")
            except Exception as e:
                logger.error(f"Error resolving short URL: {str(e)}")
                # If we can't resolve, return the original URL
                return url
        
        # Extract ASIN and construct a clean URL
        asin = self._extract_asin(url)
        if asin:
            return f"https://www.amazon.in/dp/{asin}"
            
        # If we can't extract ASIN, return the original URL
        return url
    
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
            
        # Standardize the URL to improve success rate
        url = self.normalize_url(url)
        logger.info(f"Using normalized URL: {url}")
        
        last_exception = None
        
        # for attempt in range(self.max_retries):
        #     try:
        #         # Update headers and add random delay
        #         self._update_headers()
        #         self._random_delay()
                
        #         # Exponential backoff based on attempt number
        #         if attempt > 0:
        #             sleep_time = (2 ** attempt) + random.uniform(1, 3)
        #             logger.info(f"Attempt {attempt+1}/{self.max_retries}: Waiting {sleep_time:.2f}s before retry")
        #             time.sleep(sleep_time)
                
        #         # Use a different user agent for each attempt
        #         random_user_agent = random.choice(USER_AGENTS)
        #         self.session.headers.update({"User-Agent": random_user_agent})
                
        #         # Try to use a completely fresh session for a new attempt
        #         if attempt > 0:
        #             logger.info(f"Creating fresh session for attempt {attempt+1}")
        #             self._setup_session()
                    
        #         try:
        #             # Make the request with shorter timeout to avoid hanging
        #             response = self.session.get(
        #                 url,
        #                 headers=self.session.headers,
        #                 timeout=5,  # Shorter timeout
        #                 allow_redirects=True
        #             )
                    
        #             # If we get a 5xx error, use our specialized handler
        #             if 500 <= response.status_code < 600:
        #                 logger.warning(f"Server error {response.status_code} on attempt {attempt+1}/{self.max_retries}")
        #                 if self._handle_server_error(response.status_code, attempt):
        #                     continue  # Skip to next attempt after waiting
                        
        #             # Try to recover from connection errors with a more robust approach
        #         except (requests.exceptions.ConnectionError, 
        #                 requests.exceptions.Timeout, 
        #                 requests.exceptions.TooManyRedirects) as connection_error:
        #             logger.warning(f"Connection error on attempt {attempt+1}/{self.max_retries}: {str(connection_error)}")
        #             # Use a much longer backoff for connection issues
        #             backoff_time = min(30, (5 ** attempt))  # Cap at 30 seconds
        #             logger.info(f"Backing off for {backoff_time}s before retry")
        #             time.sleep(backoff_time)
                    
        #             # Create a completely fresh session
        #             self._setup_session()
        #             continue  # Skip to next attempt
                
        #         # Check for HTTP errors
        #         response.raise_for_status()
                
        #         # Parse the response
        #         soup = BeautifulSoup(response.text, 'lxml')
                
        #         # Check for CAPTCHA or bot detection
        #         if self._check_for_captcha(soup, response.text):
        #             logger.warning("CAPTCHA or bot detection triggered. Retrying with new session...")
        #             self._setup_session()  # Reset session to get new headers
        #             continue
                
        #         # Verify we're on the correct product page, not a search or similar items page
        #         if not self._verify_product_page(soup, url):
        #             logger.warning(f"Not on the correct product page for URL: {url}. Retrying...")
        #             continue
                
        #         # Extract product title (try multiple selectors)
        #         title = 'Unknown Product'
        #         title_selectors = [
        #             ('span', {'id': 'productTitle'}),
        #             ('h1', {'id': 'title'}),
        #             ('h1', {'id': 'productTitle'}),
        #             ('h1', {'class': 'a-size-large'}),
        #             ('span', {'class': 'a-size-large product-title-word-break'})
        #         ]
                
        #         for tag, attrs in title_selectors:
        #             elem = soup.find(tag, attrs)
        #             if elem and elem.get_text(strip=True):
        #                 title = elem.get_text(strip=True)
        #                 break
                
        #         # Extract price (try multiple methods)
        #         price = 0.0
        #         original_price = None
        #         discount = None
                
        #         # Method 1: Try structured data (JSON-LD)
        #         price = self._extract_price_from_json_ld(soup)
                
        #         # Method 2: Try various price selectors, ensuring we're getting the main product price
        #         if not price:
        #             # Check if we're in the buybox area - this is the most reliable for the current price
        #             buybox_containers = [
        #                 soup.find('div', {'id': 'buybox'}),
        #                 soup.find('div', {'id': 'buyNew_noncbb'}),
        #                 soup.find('div', {'id': 'unqualifiedBuyBox'})
        #             ]
                    
        #             # Filter out None values
        #             buybox_containers = [c for c in buybox_containers if c is not None]
                    
        #             if buybox_containers:
        #                 for container in buybox_containers:
        #                     # Look for specific buybox price elements
        #                     price_elements = container.select('.a-color-price, .a-size-medium.a-color-price, .a-price')
        #                     for elem in price_elements:
        #                         # Look for the price in this element or its children
        #                         price_elem = elem.select_one('.a-offscreen') or elem
        #                         if price_elem:
        #                             price_text = price_elem.get_text(strip=True)
        #                             try:
        #                                 price = float(re.sub(r'[^\d.]', '', price_text))
        #                                 if price > 0:
        #                                     break
        #                             except (ValueError, TypeError):
        #                                 continue
                            
        #                     if price and price > 0:
        #                         break
                    
        #             # If not found in buybox, check for the main product price wrapper
        #             if not price or price <= 0:
        #                 main_price_containers = [
        #                     soup.find('div', {'id': 'corePrice_desktop'}),
        #                     soup.find('div', {'id': 'corePrice_feature_div'}),
        #                     soup.find('div', {'id': 'corePriceDisplay_desktop_feature_div'}),
        #                     soup.find('div', {'id': 'price'}),
        #                     soup.find('div', {'data-feature-name': 'corePrice'})
        #                 ]
                        
        #                 # Filter out None values
        #                 main_price_containers = [c for c in main_price_containers if c is not None]
                        
        #                 if main_price_containers:
        #                     # If we found a main price container, search within it for the price
        #                     for container in main_price_containers:
        #                         price_selectors = [
        #                             ('span', {'class': 'a-price-whole'}),
        #                             ('span', {'id': 'priceblock_ourprice'}),
        #                             ('span', {'id': 'priceblock_dealprice'}),
        #                             ('span', {'class': 'a-offscreen'}),
        #                             ('span', {'class': 'a-color-price'}),
        #                             ('span', {'class': 'a-price'})
        #                         ]
                                
        #                         for tag, attrs in price_selectors:
        #                             elem = container.find(tag, attrs)
        #                             if elem:
        #                                 price_text = elem.get_text(strip=True)
        #                                 try:
        #                                     price = float(re.sub(r'[^\d.]', '', price_text))
        #                                     if price > 0:
        #                                         break
        #                                 except (ValueError, TypeError):
        #                                     continue
                                
        #                         if price and price > 0:
        #                             break
                    
        #             # If we still don't have a price, try the broader search but with caution
        #             if not price or price <= 0:
        #                 # These IDs are specific to the main product price
        #                 specific_price_selectors = [
        #                     ('span', {'id': 'priceblock_ourprice'}),
        #                     ('span', {'id': 'priceblock_dealprice'}),
        #                     ('span', {'id': 'priceblock_saleprice'})
        #                 ]
                        
        #                 for tag, attrs in specific_price_selectors:
        #                     elem = soup.find(tag, attrs)
        #                     if elem:
        #                         price_text = elem.get_text(strip=True)
        #                         try:
        #                             price = float(re.sub(r'[^\d.]', '', price_text))
        #                             if price > 0:
        #                                 break
        #                         except (ValueError, TypeError):
        #                             continue
                
        #         # Method 3: Try extracting from scripts
        #         if not price or price <= 0:
        #             price = self._extract_price_from_script(soup)
                
        #         # Extract original price and discount if available
        #         original_price_elem = soup.find('span', {'class': 'a-price a-text-price'})
        #         if original_price_elem:
        #             try:
        #                 original_price_text = original_price_elem.find('span', {'class': 'a-offscreen'}).text
        #                 original_price = float(re.sub(r'[^\d.]', '', original_price_text))
        #                 if price and original_price > price:
        #                     discount = round(((original_price - price) / original_price) * 100, 1)
        #             except (AttributeError, ValueError, TypeError):
        #                 pass
                
        #         # Check stock status
        #         in_stock = True
        #         stock_indicators = [
        #             'in stock',
        #             'available from these sellers',
        #             'in stock soon',
        #             'only left in stock',
        #             r'only \d+ left in stock'  # Use raw string for correct escaping
        #         ]
                
        #         out_of_stock_indicators = [
        #             'currently unavailable',
        #             'out of stock',
        #             'sold out',
        #             'unavailable',
        #             'not in stock',
        #             'temporarily out of stock'
        #         ]
                
        #         page_text = soup.get_text().lower()
                
        #         if any(indicator in page_text for indicator in out_of_stock_indicators):
        #             in_stock = False
                
        #         # Extract image URL if available
        #         image_url = None
        #         image_elem = soup.find('img', {'id': 'landingImage'}) or \
        #                     soup.find('img', {'class': 'a-dynamic-image'})
        #         if image_elem and 'src' in image_elem.attrs:
        #             image_url = image_elem['src']
                
        #         # Get canonical URL
        #         canonical_url = url
        #         canonical_elem = soup.find('link', {'rel': 'canonical'})
        #         if canonical_elem and 'href' in canonical_elem.attrs:
        #             canonical_url = canonical_elem['href']
                
        #         # Check for coupon
        #         coupon = None
        #         coupon_elem = soup.find('div', {'id': 'snsCoupon'}) or \
        #                     soup.find('div', {'class': 'couponBadge'}) or \
        #                     soup.find('span', {'class': 'sns-coupon-text'})
        #         if coupon_elem:
        #             coupon = coupon_elem.get_text(strip=True)
                
        #         return {
        #             'title': title,
        #             'price': float(price) if price else 0.0,
        #             'original_price': float(original_price) if original_price else None,
        #             'discount': discount,
        #             'coupon': coupon,
        #             'in_stock': in_stock,
        #             'url': canonical_url,
        #             'image_url': image_url,
        #             'last_updated': datetime.utcnow().isoformat(),
        #             'store': 'amazon'
        #         }
                
        #     except requests.exceptions.RequestException as e:
        #         last_exception = e
        #         logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
        #         if attempt == self.max_retries - 1:
        #             raise
                
        #         # Exponential backoff
        #         time.sleep((2 ** attempt) + random.random())
                
        #     except Exception as e:
        #         last_exception = e
        #         logger.error(f"Error getting product info (attempt {attempt + 1}/{self.max_retries}): {e}")
        #         if attempt == self.max_retries - 1:
        #             raise
                
        #         # Exponential backoff
        #         time.sleep((2 ** attempt) + random.random())
        
        # If we get here, all retries failed
        # Try Selenium as the first fallback
        logger.warning(f"All {self.max_retries} regular scraping attempts failed. Trying Selenium approach...")
        
        try:
            # Initialize the browser for Selenium-based scraping
            driver = self._setup_browser()
            
            # Navigate to the URL
            logger.info(f"Navigating to {url} using Selenium")
            driver.get(url)
            
            # Wait for the page to load
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Add some random delay to simulate human behavior
            time.sleep(random.uniform(3, 5))
            
            # Extract product title
            title = "Unknown Product"
            try:
                # Wait longer for the page to fully load
                time.sleep(random.uniform(3, 5))
                
                # Check for CAPTCHA detection
                page_source = driver.page_source.lower()
                if "captcha" in page_source or "robot" in page_source or "human" in page_source:
                    logger.warning("CAPTCHA detected in Selenium session. Trying alternative approach...")
                    
                    # Try to handle CAPTCHA if possible
                    try:
                        # Wait for CAPTCHA elements that might need to be clicked
                        captcha_checkboxes = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                        for checkbox in captcha_checkboxes:
                            if checkbox.is_displayed():
                                checkbox.click()
                                time.sleep(2)
                                break
                    except Exception as captcha_error:
                        logger.warning(f"Failed to handle CAPTCHA: {captcha_error}")
                
                # Try multiple approaches to get the title with longer waits
                title_selectors = [
                    (By.ID, "productTitle", 5),
                    (By.CSS_SELECTOR, "h1.a-size-large", 3),
                    (By.CSS_SELECTOR, "span#productTitle", 3),
                    (By.CSS_SELECTOR, "h1#title", 3),
                    (By.CSS_SELECTOR, ".product-title-word-break", 3),
                    (By.CSS_SELECTOR, "h1", 2)  # Last resort - any h1 tag
                ]
                
                for selector_type, selector, wait_time in title_selectors:
                    try:
                        # Wait explicitly for each selector
                        title_element = WebDriverWait(driver, wait_time).until(
                            EC.presence_of_element_located((selector_type, selector))
                        )
                        if title_element and title_element.text.strip():
                            title = title_element.text.strip()
                            logger.info(f"Extracted product title via Selenium: {title}")
                            break
                    except Exception as selector_error:
                        continue
                
                # If still no title, try JavaScript approach
                if title == "Unknown Product":
                    try:
                        title = driver.execute_script(
                            "return document.querySelector('#productTitle, h1.a-size-large, h1#title, .product-title-word-break, h1').textContent.trim()"
                        )
                        if title:
                            logger.info(f"Extracted product title via JavaScript: {title}")
                    except Exception as js_error:
                        logger.warning(f"JavaScript title extraction failed: {js_error}")
            except Exception as title_error:
                logger.warning(f"Failed to extract title with Selenium: {title_error}")
            
            # Extract price
            price = 0.0
            try:
                # Wait a bit for dynamic price elements to load
                time.sleep(1)
                
                # Try various price selectors with explicit waits
                price_selectors = [
                    (By.CSS_SELECTOR, "span.a-price span.a-offscreen", 5),
                    (By.CSS_SELECTOR, ".a-price .a-offscreen", 3),
                    (By.ID, "priceblock_ourprice", 3),
                    (By.ID, "priceblock_dealprice", 3),
                    (By.CSS_SELECTOR, ".a-color-price", 3),
                    (By.CSS_SELECTOR, "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen", 3),
                    (By.CSS_SELECTOR, ".a-section .a-price .a-offscreen", 2)
                ]
                
                for selector_type, selector, wait_time in price_selectors:
                    try:
                        price_element = WebDriverWait(driver, wait_time).until(
                            EC.presence_of_element_located((selector_type, selector))
                        )
                        price_text = price_element.text.strip() or price_element.get_attribute("textContent").strip()
                        
                        # Extract numbers from price text
                        price_text = re.sub(r'[^\d.]', '', price_text)
                        if price_text:
                            price = float(price_text)
                            if price > 0:
                                logger.info(f"Extracted price via Selenium: {price}")
                                break
                    except Exception as selector_error:
                        continue
                
                # If still no price, try JavaScript approach
                if not price or price <= 0:
                    try:
                        js_price = driver.execute_script("""
                            var priceElements = document.querySelectorAll('.a-price .a-offscreen, #priceblock_ourprice, #priceblock_dealprice, .a-color-price');
                            for (var i = 0; i < priceElements.length; i++) {
                                var text = priceElements[i].textContent.trim();
                                if (text.match(/[0-9]/)) return text;
                            }
                            return null;
                        """)
                        
                        if js_price:
                            price_text = re.sub(r'[^\d.]', '', js_price)
                            if price_text:
                                price = float(price_text)
                                logger.info(f"Extracted price via JavaScript: {price}")
                    except Exception as js_price_error:
                        logger.warning(f"JavaScript price extraction failed: {js_price_error}")
            except Exception as price_error:
                logger.warning(f"Failed to extract price with Selenium: {price_error}")
            
            # Check if in stock
            in_stock = True
            try:
                out_of_stock_elements = driver.find_elements(By.CSS_SELECTOR, "#availability span")
                for element in out_of_stock_elements:
                    text = element.text.lower()
                    if "out of stock" in text or "unavailable" in text or "not in stock" in text:
                        in_stock = False
                        break
            except:
                # Assume in stock if we can't determine
                pass
            
            # Save cookies for future use
            self._save_cookies()
            
            # Return the data even if we only got partial information
            selenium_result = {
                'title': title,
                'price': price,
                'in_stock': in_stock,
                'url': url,
                'store': 'amazon',
                'last_updated': datetime.utcnow().isoformat(),
                'extracted_via': 'selenium'
            }
            
            # Try to extract image URL if possible
            try:
                image_elements = driver.find_elements(By.CSS_SELECTOR, "#landingImage, #imgBlkFront, .a-dynamic-image")
                for img in image_elements:
                    if img.is_displayed():
                        image_url = img.get_attribute("src")
                        if image_url:
                            selenium_result['image_url'] = image_url
                            break
            except Exception as img_error:
                logger.warning(f"Could not extract image URL: {img_error}")
            
            logger.info(f"Extracted product info via Selenium: {selenium_result}")
            return selenium_result
                
        except Exception as selenium_error:
            logger.error(f"Selenium fallback failed: {str(selenium_error)}")
        finally:
            # Clean up
            if self.driver:
                try:
                    self.driver.quit()
                    self.driver = None
                except:
                    pass
        
        # If Selenium failed, try API endpoints as last resort
        logger.warning("Selenium fallback failed. Trying API endpoints as last resort...")
        
        try:
            api_result = self._try_api_endpoint(url)
            if api_result:
                logger.info("Successfully got product info from API endpoint!")
                return api_result
        except Exception as api_error:
            logger.error(f"API endpoint fallback also failed: {str(api_error)}")
        
        # If we've exhausted all options, raise the exception
        error_msg = f"Failed to get product info after exhausting all methods"
        if last_exception:
            error_msg += f": {str(last_exception)}"
        raise Exception(error_msg)
