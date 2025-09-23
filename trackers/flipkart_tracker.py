"""Flipkart Price Tracker - Stable Selenium implementation with improved Docker compatibility"""

import logging
import time
import random
import json
import re
import os
import psutil
import threading
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .base import PriceTracker

logger = logging.getLogger(__name__)

# Simple user agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

class FlipkartPriceTracker(PriceTracker):
    """Stable Flipkart price tracker with improved Docker compatibility"""
    
    # Class-level driver pool (shared with Amazon for simplicity)
    _driver_pool = []
    _pool_lock = threading.Lock()
    _driver_creation_time = {}
    _max_driver_age = timedelta(hours=1)
    _max_pool_size = 2
    
    def __init__(self, email: str = None, password: str = None, headless: bool = True):
        super().__init__(email, password)
        self.headless = headless
        self.driver = None
        self.driver_id = None
        # Use persistent data directory if available (for Docker), otherwise use local data directory
        data_dir = os.getenv('DATA_DIR', os.path.join(os.path.dirname(__file__), '../data'))
        self.cookies_file = os.path.join(data_dir, 'flipkart_cookies.json')
        
        # Health monitoring
        self.last_successful_request = datetime.now()
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3
    
    def is_valid_url(self, url: str) -> bool:
        """Check if URL is a valid Flipkart URL"""
        return 'flipkart.com' in url or 'dl.flipkart.com' in url
    
    def _create_new_driver(self) -> webdriver.Chrome:
        """Create a new Chrome driver optimized for Docker"""
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        
        # Docker-optimized Chrome options
        docker_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--memory-pressure-off",
            "--max_old_space_size=2048",
            "--aggressive-cache-discard",
            "--disable-background-tasks",
            "--disable-component-update",
            "--disable-hang-monitor",
            "--disable-blink-features=AutomationControlled",
            "--disable-search-engine-choice-screen"
        ]
        
        for arg in docker_args:
            options.add_argument(arg)
            
        options.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")
        options.add_argument("--window-size=1366,768")
        
        # Disable automation flags
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Try system driver first (most stable in Docker)
        driver = None
        try:
            driver = webdriver.Chrome(options=options)
            logger.info("✓ Flipkart Chrome driver initialized using system driver")
        except Exception as e:
            logger.warning(f"System driver failed: {e}")
            # Try fallback paths
            chrome_paths = ['/usr/bin/chromedriver', '/usr/local/bin/chromedriver']
            for path in chrome_paths:
                if os.path.exists(path):
                    try:
                        service = Service(path)
                        driver = webdriver.Chrome(service=service, options=options)
                        logger.info(f"✓ Flipkart driver initialized using {path}")
                        break
                    except Exception as path_error:
                        logger.warning(f"Path {path} failed: {path_error}")
        
        if not driver:
            raise Exception("Could not initialize Chrome driver for Flipkart")
        
        # Essential stealth
        try:
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except:
            pass
        
        return driver
    
    def _get_or_create_driver(self) -> webdriver.Chrome:
        """Get driver from pool or create new one"""
        with self._pool_lock:
            # Clean expired drivers
            current_time = datetime.now()
            expired = [i for i, creation_time in enumerate(self._driver_creation_time.values()) 
                      if current_time - creation_time > self._max_driver_age]
            
            for i in reversed(expired):
                try:
                    old_driver = self._driver_pool.pop(i)
                    old_driver.quit()
                except:
                    pass
            
            # Get available driver
            if self._driver_pool:
                driver = self._driver_pool.pop(0)
                self.driver_id = id(driver)
                logger.info("Reusing driver from pool for Flipkart")
                return driver
            
            # Create new driver
            driver = self._create_new_driver()
            self.driver_id = id(driver)
            self._driver_creation_time[self.driver_id] = datetime.now()
            return driver
    
    def _setup_browser(self):
        """Setup Chrome browser with pool management"""
        if self.driver:
            self._return_driver_to_pool()
        
        self.driver = self._get_or_create_driver()
        
        # Load cookies if available
        if os.path.exists(self.cookies_file):
            try:
                logger.info("Loading saved Flipkart cookies...")
                self.driver.get("https://www.flipkart.com")
                time.sleep(2)
                with open(self.cookies_file, 'r') as f:
                    cookies = json.load(f)
                    for cookie in cookies:
                        try:
                            self.driver.add_cookie(cookie)
                        except:
                            pass
                logger.info("Flipkart cookies loaded")
            except Exception as e:
                logger.warning(f"Error loading cookies: {e}")
        
        return self.driver
    
    def _return_driver_to_pool(self):
        """Return driver to pool for reuse"""
        if self.driver and len(self._driver_pool) < self._max_pool_size:
            with self._pool_lock:
                try:
                    # Test driver health
                    self.driver.current_url
                    self._driver_pool.append(self.driver)
                    logger.info("Returned healthy Flipkart driver to pool")
                except:
                    try:
                        self.driver.quit()
                    except:
                        pass
                    logger.info("Discarded unhealthy Flipkart driver")
        else:
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                logger.info("Flipkart driver pool full, discarded driver")
        
        self.driver = None
        self.driver_id = None
    
    def normalize_url(self, url: str) -> str:
        """Normalize Flipkart URL to standard format"""
        # If it's a short URL, resolve it
        if 'dl.flipkart.com' in url:
            if not self.driver:
                self._setup_browser()
            
            logger.info(f"Resolving Flipkart URL: {url}")
            self.driver.get(url)
            time.sleep(3)
            resolved_url = self.driver.current_url
            logger.info(f"Resolved to: {resolved_url}")
            return resolved_url
        
        return url
    
    def get_product_info(self, url: str) -> Dict[str, Any]:
        """Get product information from Flipkart using Selenium only"""
        try:
            clean_url = self.normalize_url(url)
            driver = self._setup_browser()
            
            logger.info(f"Navigating to {clean_url}")
            driver.get(clean_url)
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            time.sleep(3)
            
            # Extract title
            title = "Unknown Product"
            title_selectors = [
                'span.VU-ZEz',
                'h1.x-product-title-label',
                '.pdp-product-name',
                'h1._6EBuvT'
            ]
            
            for selector in title_selectors:
                try:
                    element = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    title = element.text.strip()
                    if title:
                        break
                except:
                    continue
            
            logger.info(f"Extracted title: {title}")
            
            # Extract price
            price = 0.0
            price_selectors = [
                '.Nx9bqj',
                '._1_WHN1',
                '.CEmiEU .Nx9bqj',
                '._16Jk6d'
            ]
            
            for selector in price_selectors:
                try:
                    element = driver.find_element(By.CSS_SELECTOR, selector)
                    price_text = element.text.strip()
                    if price_text:
                        # Extract numbers from price text
                        clean_price = re.sub(r'[^\d.]', '', price_text.replace(',', '').replace('₹', ''))
                        if clean_price:
                            try:
                                price = float(clean_price)
                                break
                            except:
                                pass
                except:
                    continue
            
            logger.info(f"Extracted price: ₹{price}")
            
            # Extract discount if available
            discount = None
            try:
                discount_element = driver.find_element(By.CSS_SELECTOR, '.UkUFwK')
                discount_text = discount_element.text.strip()
                if '% off' in discount_text:
                    discount = discount_text
            except:
                pass
            
            # Check stock status
            in_stock = True
            try:
                out_of_stock_indicators = driver.find_elements(By.XPATH, "//*[contains(text(), 'Currently unavailable') or contains(text(), 'Out of stock')]")
                if out_of_stock_indicators:
                    in_stock = False
            except:
                pass
            
            # Extract image URL
            image_url = None
            try:
                img_element = driver.find_element(By.CSS_SELECTOR, '._396cs4 img, ._2r_T1I img')
                image_url = img_element.get_attribute('src')
            except:
                pass
            
            # Save cookies
            try:
                os.makedirs(os.path.dirname(self.cookies_file), exist_ok=True)
                with open(self.cookies_file, 'w') as f:
                    json.dump(driver.get_cookies(), f)
                logger.info("Flipkart cookies saved")
            except Exception as e:
                logger.warning(f"Error saving cookies: {e}")
            
            result = {
                'title': title,
                'price': price,
                'in_stock': in_stock,
                'url': clean_url,
                'store': 'flipkart',
                'last_updated': datetime.utcnow().isoformat(),
                'extracted_via': 'selenium'
            }
            
            if discount:
                result['discount'] = discount
            
            if image_url:
                result['image_url'] = image_url
            
            logger.info(f"Successfully extracted: {title} - ₹{price}")
            return result
            
        except Exception as e:
            logger.error(f"Error extracting Flipkart product info: {e}")
            return {
                'title': 'Unknown Product',
                'price': 0.0,
                'in_stock': False,
                'url': url,
                'store': 'flipkart',
                'last_updated': datetime.utcnow().isoformat(),
                'extracted_via': 'selenium',
                'error': str(e)
            }
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up browser resources - handled by pool management"""
        if self.driver:
            self._return_driver_to_pool()
    
    @classmethod
    def cleanup_all_drivers(cls):
        """Class method to clean up all drivers in the pool"""
        with cls._pool_lock:
            for driver in cls._driver_pool:
                try:
                    driver.quit()
                except:
                    pass
            cls._driver_pool.clear()
            cls._driver_creation_time.clear()
        logger.info("All Flipkart drivers cleaned up")
    
    def __del__(self):
        """Cleanup on object destruction"""
        self.cleanup()