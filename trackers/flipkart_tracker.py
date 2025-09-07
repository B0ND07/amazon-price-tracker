"""Flipkart Price Tracker

This module provides the FlipkartPriceTracker class which implements price tracking
functionality specifically for Flipkart products with anti-scraping measures.
"""

import logging
import re
import time
import random
import json
import os
from typing import Dict, Any, Optional, Tuple, List, Union
from urllib.parse import urljoin, urlparse, parse_qs
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

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
    It includes various anti-scraping measures to avoid detection using Selenium WebDriver.
    """
    
    # Common Flipkart domain variations
    FLIPKART_DOMAINS = [
        'flipkart.com',
        'www.flipkart.com',
        'dl.flipkart.com',
        'www.flipkart.in',
        'flipkart.in'
    ]
    
    def __init__(self, email: str = None, password: str = None, max_retries: int = 3, delay_range: tuple = (1, 3), headless: bool = True):
        """Initialize the Flipkart price tracker.
        
        Args:
            email: Email for notifications (unused, kept for compatibility)
            password: Password for email (unused, kept for compatibility)
            max_retries: Maximum number of retries for failed requests
            delay_range: Tuple of (min, max) delay between requests in seconds
            headless: Whether to run the browser in headless mode
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
            
        # Selenium WebDriver configuration
        self.headless = headless
        self.driver = None
        self.cookies_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'flipkart_cookies.json')
        
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.cookies_file), exist_ok=True)
    
    def _setup_browser(self) -> webdriver.Chrome:
        """Set up and return a Chrome browser instance"""
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
        
        # Disable automation flags
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        # Initialize the Chrome driver
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            logger.warning(f"Failed to install ChromeDriver using webdriver_manager: {e}")
            # Fallback to system ChromeDriver
            driver = webdriver.Chrome(options=options)
        
        # Additional settings to make selenium less detectable
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Load cookies if they exist
        if os.path.exists(self.cookies_file):
            logger.info("Loading saved cookies...")
            driver.get("https://www.flipkart.com")
            try:
                with open(self.cookies_file, 'r') as f:
                    cookies = json.load(f)
                    for cookie in cookies:
                        driver.add_cookie(cookie)
                logger.info("Cookies loaded successfully")
            except Exception as e:
                logger.warning(f"Error loading cookies: {e}")
        
        self.driver = driver
        return driver
    
    def _save_cookies(self):
        """Save cookies for future use"""
        try:
            if self.driver:
                cookies = self.driver.get_cookies()
                with open(self.cookies_file, 'w') as f:
                    json.dump(cookies, f)
                logger.info(f"Cookies saved to {self.cookies_file}")
        except Exception as e:
            logger.warning(f"Error saving cookies: {e}")
    
    def _random_delay(self) -> None:
        """Add a random delay between requests to avoid rate limiting."""
        delay = random.uniform(*self.delay_range)
        time.sleep(delay)
    
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
        """Get product information from Flipkart using Selenium WebDriver.
        
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
        
        # Initialize the browser if not already done
        if self.driver is None:
            self._setup_browser()
        
        for attempt in range(self.max_retries):
            try:
                # Navigate to the URL
                logger.info(f"Fetching URL: {url} (attempt {attempt + 1}/{self.max_retries})")
                self.driver.get(url)
                
                # Wait for the page to load
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//body"))
                )
                
                # Small delay to ensure JavaScript executes
                self._random_delay()
                
                # Check for login page or CAPTCHA
                if "Login" in self.driver.title or "Enter Email/Mobile number" in self.driver.page_source:
                    logger.warning("Login page detected. Attempting to close login dialog...")
                    try:
                        # Try to close the login dialog if it appears
                        close_buttons = self.driver.find_elements(By.CSS_SELECTOR, "button._2KpZ6l._2doB4z, ._2doB4z, .xr2wzo")
                        if close_buttons:
                            close_buttons[0].click()
                            logger.info("Successfully closed login dialog")
                            self._random_delay()
                        else:
                            logger.warning("Could not find close button for login dialog")
                    except Exception as e:
                        logger.warning(f"Error closing login dialog: {e}")
                
                logger.info(f"Page title: {self.driver.title}")
                
                # Extract product title
                title = self._extract_title_selenium()
                
                # Extract price information
                price_info = self._extract_price_info_selenium()
                
                # Check stock status
                in_stock = self._check_stock_status_selenium()
                
                # Extract image URL
                image_url = self._extract_image_url_selenium()
                
                # Save cookies after successful scraping
                self._save_cookies()
                
                # Build result dictionary
                result = {
                    'title': title,
                    'price': price_info.get('current_price', 0),
                    'original_price': price_info.get('original_price'),
                    'discount': price_info.get('discount'),
                    'coupon': price_info.get('coupon'),
                    'in_stock': in_stock,
                    'url': url,
                    'image_url': image_url,
                    'last_updated': datetime.utcnow().isoformat(),
                    'store': 'flipkart'
                }
                
                logger.info(f"Successfully fetched product info: {title}")
                logger.debug(f"Extracted product info: {result}")
                
                return result
                
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < self.max_retries - 1:
                    self._random_delay()
                    # Restart the browser for the next attempt
                    self._setup_browser()
                else:
                    logger.error(f"Failed to fetch {url} after {self.max_retries} attempts")
                    raise ValueError(f"Failed to fetch product information: {str(e)}")
    
    def _extract_title_selenium(self) -> str:
        """Extract product title from the page using Selenium.
        
        Returns:
            Extracted product title or 'Unknown Product' if not found
        """
        # Try multiple title selectors
        title_selectors = [
            "B_NuCI", 
            ".B_NuCI", 
            "h1._35KyD6", 
            "h1.yhB1nd", 
            "h1", 
            "._35KyD6",
            ".yhB1nd",
            ".VU-ZEz"
        ]
        
        for selector in title_selectors:
            try:
                title_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                title = title_elem.text.strip()
                if title:
                    logger.info(f"Found title: {title}")
                    return title
            except:
                continue
        
        # If we can't find the title, try a more generic approach
        try:
            # Look for any h1 element
            h1_elements = self.driver.find_elements(By.TAG_NAME, "h1")
            if h1_elements:
                title = h1_elements[0].text.strip()
                if title:
                    logger.info(f"Found title from h1: {title}")
                    return title
        except:
            pass
        
        # Finally, try the page title
        try:
            page_title = self.driver.title
            if page_title and page_title.lower() not in ('flipkart', 'online shopping'):
                # Remove common suffixes from page title
                clean_title = re.sub(r'\s*[:-]\s*(Buy|Online|Flipkart|Shop).*$', '', page_title)
                logger.info(f"Using page title: {clean_title}")
                return clean_title
        except:
            pass
        
        logger.warning("Could not extract product title")
        return "Unknown Product"
    
    def _extract_price_info_selenium(self) -> Dict[str, Any]:
        """Extract price information from the page using Selenium.
        
        Returns:
            Dictionary with price information:
            - current_price: Current price (float)
            - original_price: Original/MRP price (float) if available
            - discount: Discount percentage if available
            - coupon: Coupon/discount text if available
        """
        result = {
            'current_price': 0,
            'original_price': None,
            'discount': None,
            'coupon': None
        }
        
        try:
            # Try to extract the current price
            price_selectors = [
                "._30jeq3", 
                "._30jeq3._16Jk6d", 
                "._30jeq3._1_WHN1",
                "._16Jk6d",
                ".CEmiEU div", 
                "[data-testid='price-text']",
                ".DJkZoR", 
                "._3qQ9m1",
                "*[class*='30jeq3']",  # More generic selector
                "*[class*='price']"    # Very generic selector
            ]
            
            # First try CSS selectors
            for selector in price_selectors:
                try:
                    # Wait for price element with a timeout
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    price_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    price_text = price_elem.text.strip()
                    # Remove currency symbol and commas, then convert to float
                    price_text = re.sub(r'[^\d.]', '', price_text.replace(',', ''))
                    if price_text:
                        result['current_price'] = float(price_text)
                        logger.info(f"Found current price via selector: {result['current_price']}")
                        break
                except Exception as e:
                    continue
            
            # If we couldn't find price with selectors, try regex patterns in page source
            if result['current_price'] == 0:
                page_source = self.driver.page_source
                # Try to find price patterns in the page source
                price_patterns = [
                    r'"price":(\d+)', 
                    r'"currentPrice":(\d+)',
                    r'₹(\d+,\d+)',
                    r'₹\s*(\d+,\d+)',
                    r'price">\s*₹\s*(\d+,\d+)'
                ]
                
                for pattern in price_patterns:
                    matches = re.findall(pattern, page_source)
                    if matches:
                        price_text = matches[0].replace(',', '')
                        try:
                            result['current_price'] = float(price_text)
                            logger.info(f"Found current price via regex: {result['current_price']}")
                            break
                        except (ValueError, TypeError):
                            continue
            
            # Try to extract the original price (MRP)
            mrp_selectors = [
                "._3I9_wc", 
                "._3I9_wc._2p6lqe", 
                "._3I9_wc._27UcVY",
                ".CEmiEU > div:nth-child(2)",
                "[data-testid='original-price']"
            ]
            
            for selector in mrp_selectors:
                try:
                    mrp_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    mrp_text = mrp_elem.text.strip()
                    # Remove currency symbol and commas, then convert to float
                    mrp_text = re.sub(r'[^\d.]', '', mrp_text.replace(',', ''))
                    if mrp_text:
                        result['original_price'] = float(mrp_text)
                        logger.info(f"Found original price: {result['original_price']}")
                        break
                except Exception as e:
                    continue
            
            # If we couldn't find original price with selectors, try regex patterns
            if result['original_price'] is None:
                page_source = self.driver.page_source
                mrp_patterns = [
                    r'MRP.*?₹\s*(\d+,\d+)',
                    r'original_price.*?(\d+)',
                    r'strikethrough.*?₹\s*(\d+,\d+)'
                ]
                
                for pattern in mrp_patterns:
                    matches = re.findall(pattern, page_source)
                    if matches:
                        mrp_text = matches[0].replace(',', '')
                        try:
                            result['original_price'] = float(mrp_text)
                            logger.info(f"Found original price via regex: {result['original_price']}")
                            break
                        except (ValueError, TypeError):
                            continue
            
            # Try to extract discount percentage
            discount_selectors = [
                "._3Ay6Sb", 
                "._3Ay6Sb._31Dcoz", 
                "._1V_ZGU",
                "[data-testid='discount-text']"
            ]
            
            for selector in discount_selectors:
                try:
                    discount_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    discount_text = discount_elem.text.strip()
                    # Extract percentage using regex
                    match = re.search(r'(\d+)%', discount_text)
                    if match:
                        result['discount'] = match.group(1) + '%'
                        logger.info(f"Found discount: {result['discount']}")
                        break
                except Exception as e:
                    continue
            
            # If we couldn't find discount with selectors, try regex patterns
            if result['discount'] is None:
                page_source = self.driver.page_source
                discount_patterns = [
                    r'(\d+)%\s*off',
                    r'discount.*?(\d+)%'
                ]
                
                for pattern in discount_patterns:
                    matches = re.findall(pattern, page_source)
                    if matches:
                        try:
                            result['discount'] = matches[0] + '%'
                            logger.info(f"Found discount via regex: {result['discount']}")
                            break
                        except (ValueError, TypeError, IndexError):
                            continue
            
            # Try to extract any coupon/offer text
            coupon_selectors = [
                "._3xFhiH", 
                "._3TT44I", 
                ".dyC4hf",
                "[data-testid='offer-text']"
            ]
            
            for selector in coupon_selectors:
                try:
                    coupon_elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if coupon_elems:
                        result['coupon'] = coupon_elems[0].text.strip()
                        logger.info(f"Found coupon: {result['coupon']}")
                        break
                except Exception as e:
                    continue
                
        except Exception as e:
            logger.warning(f"Error extracting price info: {e}")
            
        return result
    
    def _check_stock_status_selenium(self) -> bool:
        """Check if the product is in stock using Selenium.
        
        Returns:
            Boolean indicating if product is in stock
        """
        try:
            # Look for out-of-stock indicators
            out_of_stock_selectors = [
                "._16FRp0", 
                "._1dVbu9", 
                "._397wMz",
                "[data-testid='out-of-stock']"
            ]
            
            for selector in out_of_stock_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements and any('out of stock' in element.text.lower() for element in elements):
                        logger.info(f"Found out-of-stock indicator: {selector}")
                        return False
                except:
                    continue
                    
            # Check for "sold out" or "out of stock" text in the page
            page_text = self.driver.page_source.lower()
            sold_out_texts = ['sold out', 'out of stock', 'currently unavailable']
            if any(text in page_text for text in sold_out_texts):
                # If we find sold out text, check if buy buttons still exist
                buy_button_selectors = [
                    "._2KpZ6l", 
                    "._2KpZ6l._2U9uOA._3v1-ww", 
                    "._2KpZ6l._1t_O3S",
                    "._1p3MFP._31gJgq",
                    "[data-testid='add-to-cart']",
                    "[data-testid='buy-now']"
                ]
                
                found_buy_button = False
                for selector in buy_button_selectors:
                    try:
                        buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if buttons:
                            found_buy_button = True
                            break
                    except:
                        continue
                        
                if not found_buy_button:
                    logger.info("Found 'sold out' text and no buy buttons")
                    return False
            
            # Check if there's a buy button or add to cart button
            buy_button_selectors = [
                "._2KpZ6l", 
                "._2KpZ6l._2U9uOA._3v1-ww", 
                "._2KpZ6l._1t_O3S",
                "._1p3MFP._31gJgq",
                "[data-testid='add-to-cart']",
                "[data-testid='buy-now']"
            ]
            
            for selector in buy_button_selectors:
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if buttons:
                        for button in buttons:
                            button_text = button.text.lower()
                            if any(text in button_text for text in ['add', 'cart', 'buy']):
                                logger.info(f"Found buy button: {button_text}")
                                return True
                except:
                    continue
            
            # Look for price patterns in the page source - if we find a price, assume in stock
            page_source = self.driver.page_source
            price_patterns = [
                r'"price":(\d+)', 
                r'"currentPrice":(\d+)',
                r'₹(\d+,\d+)',
                r'₹\s*(\d+,\d+)'
            ]
            
            for pattern in price_patterns:
                if re.search(pattern, page_source):
                    logger.info(f"Found price pattern, assuming in stock")
                    return True
                    
            logger.warning("Could not determine stock status, defaulting to False")
            return False
            
        except Exception as e:
            logger.error(f"Error checking stock status: {e}")
            return False
    
    def _extract_image_url_selenium(self) -> Optional[str]:
        """Extract the product image URL using Selenium.
        
        Returns:
            URL of the product image or None if not found
        """
        try:
            # Try different image selectors
            image_selectors = [
                "._396cs4", 
                "._2r_T1I", 
                "#productImage",
                ".CXW8mj img",
                "[data-testid='product-image']",
                "._3GnUWp img",
                "._3GnUWp ._2puWtW._3a3qyb"
            ]
            
            for selector in image_selectors:
                try:
                    img_elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if img_elems:
                        for img in img_elems:
                            src = img.get_attribute('src')
                            if src and src.startswith('http'):
                                logger.info(f"Found image URL: {src}")
                                return src
                            
                            # For elements with background-image in style
                            style = img.get_attribute('style')
                            if style:
                                match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                                if match:
                                    url = match.group(1)
                                    if url.startswith('http'):
                                        logger.info(f"Found image URL in style: {url}")
                                        return url
                except:
                    continue
            
            # Last resort: check for any product image
            try:
                all_images = self.driver.find_elements(By.TAG_NAME, 'img')
                for img in all_images:
                    src = img.get_attribute('src')
                    alt = img.get_attribute('alt') or ''
                    alt = alt.lower()
                    # Look for image with product-related alt text
                    if src and src.startswith('http') and ('product' in alt or 'item' in alt):
                        logger.info(f"Found image URL from alt text: {src}")
                        return src
                        
                # If we still haven't found an image, take the first image that looks like a product
                for img in all_images:
                    src = img.get_attribute('src')
                    if src and src.startswith('http') and any(x in src for x in ['product', 'image', 'photo']):
                        if not ('icon' in src or 'logo' in src or 'banner' in src):
                            logger.info(f"Found potential product image: {src}")
                            return src
                            
                # Last resort: just use any reasonably sized image
                for img in all_images:
                    try:
                        width = int(img.get_attribute('width') or 0)
                        height = int(img.get_attribute('height') or 0)
                        src = img.get_attribute('src')
                        if src and src.startswith('http') and width > 100 and height > 100:
                            logger.info(f"Found sized image: {src}")
                            return src
                    except:
                        continue
            except Exception as e:
                logger.warning(f"Error searching all images: {e}")
                    
            logger.warning("Could not find any product image")
            return None
                
        except Exception as e:
            logger.error(f"Error extracting image URL: {e}")
            return None
    
    def _extract_price(self, price_text: str) -> float:
        """Extract price as float from price text by removing currency symbols and commas.
        
        Args:
            price_text: Price text with currency symbols, commas, etc.
            
        Returns:
            float: Extracted price or 0 if extraction fails
        """
        try:
            # Remove non-numeric characters except the decimal point
            price_text = re.sub(r'[^\d.]', '', price_text.replace(',', ''))
            
            # Convert to float
            if price_text:
                return float(price_text)
        except (ValueError, AttributeError) as e:
            logger.debug(f"Error extracting price from '{price_text}': {e}")
            
        return 0.0
    
    def cleanup(self):
        """Clean up resources when the tracker is no longer needed."""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
        except Exception as e:
            logger.warning(f"Error cleaning up WebDriver: {e}")
            
    def __del__(self):
        """Destructor to ensure resources are properly released."""
        self.cleanup()
