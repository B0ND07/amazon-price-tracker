import requests
import time
import random
import re
import logging
import json
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse
import base64

logger = logging.getLogger(__name__)

class AmazonPriceTracker:
    """
    Amazon Price Tracker with enhanced out-of-stock detection
    """
    
    def __init__(self, email: Optional[str] = None, password: Optional[str] = None):
        """Initialize the Amazon tracker with session and headers"""
        self.session = requests.Session()
        self._setup_advanced_session()
        self.request_count = 0
        self.last_request_time = 0
        logger.info("✅ Advanced Amazon Price Tracker initialized")
    
    def _setup_advanced_session(self) -> None:
        """Configure advanced session with realistic browser behavior"""
        # Set up realistic cookies first
        self._setup_realistic_cookies()
        
        # Rotating user agents that work well with Amazon
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        
        # Start with a random user agent
        self.current_ua = random.choice(self.user_agents)
        
        # Advanced headers that bypass detection
        self.session.headers.update({
            'User-Agent': self.current_ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'max-age=0',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'DNT': '1',
            'Connection': 'keep-alive'
        })
    
    def _setup_realistic_cookies(self) -> None:
        """Set up realistic Amazon cookies to appear as legitimate user"""
        realistic_cookies = {
            'session-id': f'147-{random.randint(1000000, 9999999)}-{random.randint(1000000, 9999999)}',
            'session-id-time': str(int(time.time())),
            'i18n-prefs': 'INR',
            'sp-cdn': 'L5Z9:IN',
            'skin': 'noskin',
            'ubid-acbin': f'{random.randint(100, 999)}-{random.randint(1000000, 9999999)}-{random.randint(1000000, 9999999)}',
            'lc-acbin': 'en_IN',
            'csm-hit': f'adb:{random.randint(1000000000, 9999999999)}+{random.randint(100, 999)}',
        }
        
        for name, value in realistic_cookies.items():
            self.session.cookies.set(name, value, domain='.amazon.in')
    
    def get_product_info(self, url: str) -> Dict:
        """
        Extract product information from Amazon URL with advanced bypass techniques
        
        Args:
            url: Amazon product URL
            
        Returns:
            Dictionary containing product information
        """
        logger.info(f"🚀 Starting advanced extraction for: {url}")
        
        # Try multiple sophisticated strategies
        strategies = [
            self._strategy_basic_request,
            self._strategy_with_referrer,
            self._strategy_search_redirect,
            self._strategy_mobile_version,
            self._strategy_api_endpoint
        ]
        
        for strategy_num, strategy in enumerate(strategies, 1):
            try:
                logger.info(f"🎯 Strategy {strategy_num}: {strategy.__name__}")
                # Use retry logic for HTTP 500 errors
                result = self._execute_strategy_with_retries(strategy, url)
                
                if result and result.get('success'):
                    logger.info(f"✅ Strategy {strategy_num} succeeded!")
                    return result
                elif result and not result.get('success') and 'CAPTCHA' not in result.get('error', ''):
                    # Return non-CAPTCHA failures immediately (like genuine unavailability)
                    return result
                    
                # If CAPTCHA or no result, try next strategy
                logger.warning(f"⚠️  Strategy {strategy_num} failed, trying next...")
                
            except Exception as e:
                logger.warning(f"💥 Strategy {strategy_num} exception: {e}")
                continue
        
        return self._create_error_result(url, "All bypass strategies failed")
    
    def _realistic_delay(self) -> None:
        """Implement realistic human-like delays"""
        self.request_count += 1
        current_time = time.time()
        
        # Progressive delays - appear more human
        base_delay = random.uniform(3, 8)
        if self.request_count > 3:
            base_delay += random.uniform(2, 5)
        if self.request_count > 5:
            base_delay += random.uniform(5, 10)
            
        # Minimum time between requests
        if self.last_request_time > 0:
            time_since_last = current_time - self.last_request_time
            if time_since_last < base_delay:
                additional_delay = base_delay - time_since_last
                logger.info(f"⏳ Human-like delay: {additional_delay:.1f}s")
                time.sleep(additional_delay)
        
        self.last_request_time = time.time()
    
    def _rotate_user_agent(self) -> None:
        """Rotate user agent to avoid fingerprinting"""
        self.current_ua = random.choice(self.user_agents)
        self.session.headers['User-Agent'] = self.current_ua
    
    def _execute_strategy_with_retries(self, strategy_func, url: str, max_retries: int = 2) -> Dict:
        """Execute a strategy with retries on HTTP 500 errors"""
        for attempt in range(max_retries):
            try:
                # Execute the strategy
                result = strategy_func(url)
                
                # Check if it's an HTTP 500 error that should be retried
                if (result and not result.get('success') and 
                    'HTTP 500' in result.get('error', '')):
                    
                    if attempt < max_retries - 1:  # Not the last attempt
                        logger.warning(f"🔄 HTTP 500 error, retrying in 4 seconds... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(4)  # 4 second delay as requested
                        continue
                    else:
                        logger.error(f"❌ Max retries reached for HTTP 500 error")
                        return result
                else:
                    # Success or other error types, return the result
                    return result
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"🔄 Strategy exception, retrying in 4 seconds... (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(4)
                    continue
                else:
                    return self._create_error_result(url, f"Strategy failed after {max_retries} attempts: {e}")
        
        return self._create_error_result(url, f"Failed after {max_retries} attempts")
    
    def _strategy_basic_request(self, url: str) -> Dict:
        """Strategy 1: Enhanced basic request with realistic behavior"""
        self._realistic_delay()
        self._rotate_user_agent()
        
        try:
            response = self.session.get(url, timeout=25, allow_redirects=True)
            logger.info(f"📡 Basic request: {response.status_code}")
            
            if response.status_code == 200:
                return self._extract_product_data(response, url)
            else:
                return self._create_error_result(url, f"HTTP {response.status_code}")
                
        except Exception as e:
            return self._create_error_result(url, f"Basic request failed: {e}")
    
    def _strategy_with_referrer(self, url: str) -> Dict:
        """Strategy 2: Request with Google referrer to appear organic"""
        self._realistic_delay()
        self._rotate_user_agent()
        
        # Mimic coming from Google search
        original_headers = self.session.headers.copy()
        self.session.headers.update({
            'Referer': 'https://www.google.com/',
            'sec-fetch-site': 'cross-site'
        })
        
        try:
            response = self.session.get(url, timeout=25, allow_redirects=True)
            logger.info(f"📡 Referrer request: {response.status_code}")
            
            if response.status_code == 200:
                return self._extract_product_data(response, url)
            else:
                return self._create_error_result(url, f"HTTP {response.status_code}")
                
        except Exception as e:
            return self._create_error_result(url, f"Referrer request failed: {e}")
        finally:
            # Restore original headers
            self.session.headers = original_headers
    
    def _strategy_search_redirect(self, url: str) -> Dict:
        """Strategy 3: First visit Amazon homepage, then navigate to product"""
        self._realistic_delay()
        
        try:
            # First visit Amazon homepage to establish session
            logger.info("🏠 Visiting Amazon homepage first...")
            homepage_response = self.session.get('https://www.amazon.in', timeout=20)
            
            if homepage_response.status_code != 200:
                return self._create_error_result(url, "Homepage visit failed")
            
            # Small delay before product page
            time.sleep(random.uniform(1, 3))
            
            # Now visit product page as if navigating from homepage
            self.session.headers.update({
                'Referer': 'https://www.amazon.in/',
                'sec-fetch-site': 'same-origin'
            })
            
            response = self.session.get(url, timeout=25, allow_redirects=True)
            logger.info(f"📡 Search redirect: {response.status_code}")
            
            if response.status_code == 200:
                return self._extract_product_data(response, url)
            else:
                return self._create_error_result(url, f"HTTP {response.status_code}")
                
        except Exception as e:
            return self._create_error_result(url, f"Search redirect failed: {e}")
    
    def _strategy_mobile_version(self, url: str) -> Dict:
        """Strategy 4: Try mobile version which is often less protected"""
        self._realistic_delay()
        
        # Convert to mobile URL
        mobile_url = url.replace('www.amazon.in', 'm.amazon.in')
        
        # Mobile headers
        original_headers = self.session.headers.copy()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1',
            'sec-ch-ua': None,
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"iOS"'
        })
        
        try:
            response = self.session.get(mobile_url, timeout=25, allow_redirects=True)
            logger.info(f"📱 Mobile request: {response.status_code}")
            
            if response.status_code == 200:
                return self._extract_product_data(response, url)
            else:
                return self._create_error_result(url, f"HTTP {response.status_code}")
                
        except Exception as e:
            return self._create_error_result(url, f"Mobile request failed: {e}")
        finally:
            # Restore original headers
            self.session.headers = original_headers
    
    def _strategy_api_endpoint(self, url: str) -> Dict:
        """Strategy 5: Try alternative Amazon endpoints"""
        self._realistic_delay()
        
        # Extract ASIN from URL
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        if not asin_match:
            return self._create_error_result(url, "Could not extract ASIN")
        
        asin = asin_match.group(1)
        
        # Try different URL formats
        alternative_urls = [
            f'https://www.amazon.in/gp/product/{asin}',
            f'https://www.amazon.in/dp/{asin}/',
            f'https://www.amazon.in/exec/obidos/ASIN/{asin}'
        ]
        
        for alt_url in alternative_urls:
            try:
                self._realistic_delay()
                response = self.session.get(alt_url, timeout=25, allow_redirects=True)
                logger.info(f"🔄 Alternative URL {alt_url}: {response.status_code}")
                
                if response.status_code == 200:
                    result = self._extract_product_data(response, url)
                    if result.get('success'):
                        return result
                    
            except Exception as e:
                logger.warning(f"Alternative URL failed: {e}")
                continue
        
        return self._create_error_result(url, "All alternative URLs failed")
    
    def _extract_product_data(self, response: requests.Response, url: str) -> Dict:
        """
        Extract product data from HTML response
        
        Args:
            response: HTTP response object
            url: Product URL
            
        Returns:
            Dictionary with product information
        """
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Check for CAPTCHA/Robot check first
        if self._is_captcha_page(soup, response.text):
            logger.warning("🤖 Amazon CAPTCHA/Robot check detected")
            return self._create_error_result(url, "Amazon CAPTCHA/Robot check - automated access blocked")
        
        # Extract title
        title = self._extract_title(soup)
        
        # Check availability status first
        availability_status = self._check_availability(soup, response.text)
        
        if not availability_status['in_stock']:
            logger.info(f"❌ Product unavailable: {availability_status['reason']}")
            return {
                'title': title,
                'price': 0.0,
                'in_stock': False,
                'url': url,
                'store': 'amazon',
                'last_updated': datetime.utcnow().isoformat(),
                'extracted_via': 'requests',
                'success': True,
                'availability_reason': availability_status['reason']
            }
        
        # Extract price
        price = self._extract_price(soup, response.text)
        
        # Extract coupon information
        coupon_info = self._extract_coupon_info(soup)
        
        if price > 0:
            coupon_text = f" (Coupon: ₹{coupon_info['value']})" if coupon_info['available'] else ""
            logger.info(f"✅ {title[:50]}... - ₹{price}{coupon_text}")
            
            result = {
                'title': title,
                'price': price,
                'in_stock': True,
                'url': url,
                'store': 'amazon',
                'last_updated': datetime.utcnow().isoformat(),
                'extracted_via': 'requests',
                'success': True
            }
            
            # Add coupon information if available
            if coupon_info['available']:
                result['coupon'] = coupon_info
                result['final_price'] = price - coupon_info['value']
                
            return result
        else:
            logger.warning(f"⚠️  No price found for: {title[:50]}...")
            return self._create_error_result(url, "No valid price found")
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract product title from soup"""
        title_selectors = [
            '#productTitle',
            '.product-title',
            'h1.a-size-large',
            'h1[data-automation-id="product-title"]'
        ]
        
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text(strip=True)
                if title:
                    return title[:200]  # Limit length
        
        return "Unknown Product"
    
    def _is_captcha_page(self, soup: BeautifulSoup, html_text: str) -> bool:
        """
        Check if the response is a CAPTCHA or robot check page
        
        Args:
            soup: BeautifulSoup object
            html_text: Raw HTML text
            
        Returns:
            True if CAPTCHA page detected
        """
        captcha_indicators = [
            'validateCaptcha',
            'Robot Check',
            'automated access',
            'api-services-support@amazon.com',
            'Continue shopping',
            'Click the button below to continue',
            'Service Unavailable Error',
            'opfcaptcha.amazon'
        ]
        
        # Check text content
        html_lower = html_text.lower()
        for indicator in captcha_indicators:
            if indicator.lower() in html_lower:
                return True
        
        # Check for CAPTCHA form elements
        captcha_forms = soup.select('form[action*="validateCaptcha"], form[action*="captcha"]')
        if captcha_forms:
            return True
        
        # Check for very short responses (often indicates blocking)
        if len(html_text) < 10000 and soup.select('.a-alert'):
            return True
        
        return False
    
    def _check_availability(self, soup: BeautifulSoup, html_text: str) -> Dict:
        """
        Enhanced availability checking with critical unavailability indicators first
        
        Args:
            soup: BeautifulSoup object
            html_text: Raw HTML text
            
        Returns:
            Dictionary with availability status and reason
        """
        # FIRST: Check for CRITICAL unavailability indicators (these override everything)
        
        # 1. Check for specific outOfStock div (user's example) - HIGHEST PRIORITY
        out_of_stock_div = soup.select_one('#outOfStock')
        if out_of_stock_div:
            out_of_stock_text = out_of_stock_div.get_text(strip=True).lower()
            if 'currently unavailable' in out_of_stock_text:
                logger.info("❌ CRITICAL: outOfStock div found - overrides all other indicators")
                return {'in_stock': False, 'reason': 'outOfStock div - Currently unavailable'}
        
        # 2. Check for explicit unavailability messages in availability section
        availability_elem = soup.select_one('#availability span, [data-feature-name="availability"] span')
        if availability_elem:
            availability_text = availability_elem.get_text(strip=True).lower()
            critical_unavailable = [
                'currently unavailable', 'out of stock', 'temporarily out of stock',
                'not available', 'discontinued', 'no longer available'
            ]
            for indicator in critical_unavailable:
                if indicator in availability_text:
                    logger.info(f"❌ CRITICAL: Unavailable in availability section: {availability_text}")
                    return {'in_stock': False, 'reason': f'availability critical - {indicator}'}
        
        # 3. Check if NO buy buttons exist at all (strong unavailability indicator)
        all_buy_buttons = soup.select('#buy-now-button, #add-to-cart-button, [name="submit.buy-now"]')
        if not all_buy_buttons:
            logger.info("❌ CRITICAL: No buy buttons found anywhere")
            return {'in_stock': False, 'reason': 'no buy buttons present'}
        
        # Now check for POSITIVE availability indicators
        
        # 4. Check for working buy buttons (strongest positive indicator)
        working_buy_buttons = soup.select('#buy-now-button:not([disabled]), #add-to-cart-button:not([disabled])')
        if working_buy_buttons:
            for button in working_buy_buttons:
                button_text = button.get_text(strip=True).lower()
                if 'add to cart' in button_text or 'buy now' in button_text:
                    logger.info(f"✅ Found working buy button: {button_text}")
                    return {'in_stock': True, 'reason': 'working buy button found'}
        
        # 5. Check for positive availability messages
        if availability_elem:
            availability_text = availability_elem.get_text(strip=True).lower()
            positive_indicators = [
                'in stock', 'available', 'ships from', 'sold by amazon', 
                'get it by', 'fastest delivery', 'free delivery'
            ]
            for indicator in positive_indicators:
                if indicator in availability_text:
                    logger.info(f"✅ Positive availability: {availability_text}")
                    return {'in_stock': True, 'reason': f'availability positive - {indicator}'}
        
        # 6. Check for quantity selectors (indicates stock)
        quantity_selectors = soup.select('select[name="quantity"], #quantity')
        if quantity_selectors:
            logger.info("✅ Quantity selector found")
            return {'in_stock': True, 'reason': 'quantity selector present'}
        
        # 7. Check for delivery information (indicates availability)
        delivery_elements = soup.select('[data-feature-name="delivery"], .a-section:contains("delivery")')
        for elem in delivery_elements:
            delivery_text = elem.get_text(strip=True).lower()
            if any(phrase in delivery_text for phrase in ['delivery', 'ships', 'arrives']):
                logger.info(f"✅ Delivery info found: {delivery_text[:50]}...")
                return {'in_stock': True, 'reason': 'delivery information present'}
        
        # Secondary negative checks (only if no critical indicators found)
        
        # 8. Check for disabled buy buttons
        disabled_buttons = soup.select('#buy-now-button[disabled], #add-to-cart-button[disabled]')
        if disabled_buttons and not working_buy_buttons:
            logger.info("❌ All buy buttons disabled")
            return {'in_stock': False, 'reason': 'buy buttons disabled'}
        
        # 9. Check for error alert boxes (but be more specific)
        error_boxes = soup.select('div.a-box.a-alert.a-alert-error')
        for box in error_boxes:
            box_text = box.get_text(strip=True).lower()
            # Only consider it unavailable if it explicitly mentions stock/availability
            if any(phrase in box_text for phrase in ['unavailable', 'out of stock', 'not available']):
                logger.info(f"❌ Error box with stock message: {box_text[:50]}...")
                return {'in_stock': False, 'reason': f'error alert - stock related'}
        
        # 10. Check for marketplace-only availability
        marketplace_indicators = soup.select('.olp-link, .a-link-normal[href*="offer-listing"]')
        if marketplace_indicators and not soup.select('#add-to-cart-button:not([disabled])'):
            logger.info("❌ Only marketplace sellers")
            return {'in_stock': False, 'reason': 'only marketplace sellers available'}
        
        # 11. Final fallback - check page text for critical phrases
        page_text_lower = soup.get_text(' ').lower()
        critical_phrases = ['currently unavailable', 'temporarily unavailable', 'out of stock']
        for phrase in critical_phrases:
            if phrase in page_text_lower:
                logger.info(f"❌ Critical phrase in page: {phrase}")
                return {'in_stock': False, 'reason': f'page text contains: {phrase}'}
        
        # If we reach here and found some positive indicators but no negatives, assume available
        logger.info("✅ No strong unavailability indicators found, assuming available")
        return {'in_stock': True, 'reason': 'no unavailability indicators found'}
    
    def _extract_price(self, soup: BeautifulSoup, html_text: str) -> float:
        """
        Precise price extraction focusing on main product only, avoiding related/similar products
        
        Args:
            soup: BeautifulSoup object
            html_text: Raw HTML text
            
        Returns:
            Price as float, 0.0 if not found
        """
        logger.info("🔍 Starting precise price extraction for main product only...")
        
        # STRATEGY 1: Look for price in main product context areas (highest priority)
        main_product_contexts = [
            '#corePrice_feature_div',  # Main price section
            '#corePrice_desktop',      # Desktop price display
            '#apex_desktop',           # Product info area
            '#centerCol',              # Main content column
            '#dp-container',           # Product detail container
            '[data-feature-name="corePrice"]',
            '[data-feature-name="apex_desktop"]'
        ]
        
        for context_selector in main_product_contexts:
            context_elem = soup.select_one(context_selector)
            if context_elem:
                price = self._extract_price_from_context(context_elem, f"main context ({context_selector})")
                if price > 0:
                    return price
        
        # STRATEGY 2: Look for price near product title (very reliable)
        product_title = soup.select_one('#productTitle')
        if product_title:
            # Look for prices within reasonable distance of title
            title_container = product_title.find_parent(['div', 'section'])
            if title_container:
                price = self._extract_price_from_context(title_container, "near product title")
                if price > 0:
                    return price
        
        # STRATEGY 3: Specific high-confidence selectors (avoiding generic ones)
        precise_selectors = [
            '#corePrice_feature_div .a-price .a-offscreen',
            '#corePrice_desktop .a-price .a-offscreen',
            '#apex_desktop .a-price .a-offscreen',
            '.a-price.a-text-price.a-size-medium.a-color-base .a-offscreen',
            '[data-feature-name="corePrice"] .a-price .a-offscreen',
            '#priceblock_dealprice',
            '#priceblock_ourprice'
        ]
        
        for i, selector in enumerate(precise_selectors, 1):
            price_elem = soup.select_one(selector)
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price = self._parse_price_text(price_text)
                if price > 0 and self._validate_price_context(price_elem):
                    logger.info(f"✅ Precise price found with selector {i} ({selector}): ₹{price}")
                    return price
        
        # STRATEGY 4: Avoid common false positive areas and look in safe zones
        safe_price_elements = []
        all_price_elements = soup.select('.a-price .a-offscreen, .a-price-whole')
        
        for elem in all_price_elements:
            if self._is_safe_price_element(elem):
                safe_price_elements.append(elem)
        
        # Get the first safe price (likely the main product price)
        for elem in safe_price_elements[:1]:  # Only take the first safe one
            price = self._parse_price_text(elem.get_text(strip=True))
            if price > 0:
                logger.info(f"✅ Safe price element found: ₹{price}")
                return price
        
        logger.warning("❌ No reliable main product price found")
        return 0.0
    
    def _extract_price_from_context(self, context_elem, context_name: str) -> float:
        """Extract price from a specific context element"""
        price_selectors = [
            '.a-price .a-offscreen',
            '.a-price-whole', 
            '.a-color-price',
            '[data-a-price-value]'
        ]
        
        for selector in price_selectors:
            price_elem = context_elem.select_one(selector)
            if price_elem:
                price = self._parse_price_text(price_elem.get_text(strip=True))
                if price > 0:
                    logger.info(f"✅ Price found in {context_name}: ₹{price}")
                    return price
        return 0.0
    
    def _validate_price_context(self, price_elem) -> bool:
        """Validate that price element is in main product context, not related products"""
        # Get the element's context by looking at parent containers
        current = price_elem
        for _ in range(5):  # Check up to 5 parent levels
            if current is None:
                break
                
            # Check if we're in a related/similar products section
            classes = current.get('class', [])
            ids = current.get('id', '')
            
            # Common patterns for related/similar product sections
            avoid_patterns = [
                'related', 'similar', 'recommended', 'sponsored', 'ads',
                'customers-also', 'frequently-bought', 'bundle', 'accessory',
                'comparison', 'alternative', 'suggestion', 'carousel'
            ]
            
            context_text = ' '.join(classes + [ids]).lower()
            if any(pattern in context_text for pattern in avoid_patterns):
                logger.debug(f"❌ Price in related products section: {context_text}")
                return False
                
            current = current.parent
            
        return True
    
    def _is_safe_price_element(self, price_elem) -> bool:
        """Check if price element is safe (not in related products, ads, etc.)"""
        # Check element and its parents for suspicious contexts
        current = price_elem
        for _ in range(8):  # Check up to 8 parent levels
            if current is None:
                break
                
            # Get all text content and attributes
            element_text = current.get_text(strip=True).lower() if hasattr(current, 'get_text') else ''
            classes = ' '.join(current.get('class', [])).lower()
            element_id = current.get('id', '').lower()
            
            # Patterns that indicate this is NOT the main product price
            unsafe_patterns = [
                'customers who viewed', 'customers also bought', 'frequently bought together',
                'related products', 'similar items', 'recommended', 'sponsored',
                'compare with similar', 'product comparison', 'alternatives',
                'bundle', 'accessory', 'add-on', 'carousel', 'slider',
                'advertisement', 'promotion', 'deal of the day'
            ]
            
            all_context = f"{element_text} {classes} {element_id}"
            if any(pattern in all_context for pattern in unsafe_patterns):
                logger.debug(f"❌ Unsafe price context detected: {pattern}")
                return False
                
            current = current.parent
            
        return True
    
    def _extract_coupon_info(self, soup: BeautifulSoup) -> Dict:
        """
        Extract coupon information with high accuracy, focusing on main product only
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Dictionary with coupon availability and value
        """
        logger.info("🎫 Checking for main product coupons only...")
        
        coupon_result = {
            'available': False,
            'value': 0.0,
            'description': '',
            'type': ''
        }
        
        # Strategy 1: Look for coupons in main product context areas ONLY
        main_product_contexts = [
            '#corePrice_feature_div',  # Main price section
            '#corePrice_desktop',      # Desktop price display
            '#apex_desktop',           # Product info area
            '#centerCol',              # Main content column
            '#dp-container',           # Product detail container
            '[data-feature-name="corePrice"]',
            '[data-feature-name="apex_desktop"]'
        ]
        
        for context_selector in main_product_contexts:
            context_elem = soup.select_one(context_selector)
            if context_elem:
                coupon = self._extract_coupon_from_context(context_elem, f"main context ({context_selector})")
                if coupon['available']:
                    return coupon
        
        # Strategy 2: Look for coupon checkbox near main product (with strict context validation)
        coupon_checkboxes = soup.select('input[type="checkbox"][name*="coupon"], .coupon-checkbox, [data-coupon-value]')
        for checkbox in coupon_checkboxes:
            # Check if coupon is available and in main product context
            if not checkbox.has_attr('disabled') and self._is_main_product_coupon(checkbox):
                coupon_container = checkbox.find_parent(['div', 'span', 'label'])
                if coupon_container:
                    coupon_text = coupon_container.get_text(strip=True)
                    coupon_value = self._parse_coupon_value(coupon_text)
                    if coupon_value > 0:
                        logger.info(f"✅ Main product coupon found via checkbox: ₹{coupon_value}")
                        coupon_result.update({
                            'available': True,
                            'value': coupon_value,
                            'description': coupon_text,
                            'type': 'main_product_checkbox'
                        })
                        return coupon_result
        
        # Strategy 3: Look for coupon near product title (highly reliable for main product)
        product_title = soup.select_one('#productTitle')
        if product_title:
            # Search within reasonable distance of the title
            title_parent = product_title.find_parent(['div', 'section'])
            if title_parent:
                # Look for next siblings that might contain coupon info
                for sibling in title_parent.find_next_siblings(['div', 'section'])[:5]:  # Check first 5 siblings
                    coupon = self._extract_coupon_from_context(sibling, "near product title")
                    if coupon['available']:
                        return coupon
        
        logger.info("❌ No main product coupons found")
        return coupon_result
    
    def _extract_coupon_from_context(self, context_elem, context_name: str) -> Dict:
        """Extract coupon from a specific context element, avoiding related products"""
        coupon_result = {
            'available': False,
            'value': 0.0,
            'description': '',
            'type': ''
        }
        
        # First check if this context contains related products (avoid these)
        context_text = context_elem.get_text(' ').lower()
        avoid_sections = [
            'related products', 'customers who viewed', 'customers also bought',
            'frequently bought together', 'sponsored', 'compare with similar',
            'similar items', 'recommended', 'you might also like'
        ]
        
        if any(section in context_text for section in avoid_sections):
            logger.debug(f"❌ Skipping coupon extraction from related products section: {context_name}")
            return coupon_result
        
        # Look for coupon patterns in this specific context
        coupon_patterns = [
            r'apply\s*₹\s*([0-9,]+)\s*coupon',
            r'₹\s*([0-9,]+)\s*coupon',
            r'save\s*₹\s*([0-9,]+)\s*with\s*coupon',
            r'clip\s*₹\s*([0-9,]+)\s*coupon'
        ]
        
        for pattern in coupon_patterns:
            matches = re.findall(pattern, context_text, re.IGNORECASE)
            if matches:
                try:
                    coupon_value = float(matches[0].replace(',', ''))
                    if coupon_value > 0:
                        logger.info(f"✅ Main product coupon found in {context_name}: ₹{coupon_value}")
                        coupon_result.update({
                            'available': True,
                            'value': coupon_value,
                            'description': f'Apply ₹{coupon_value} coupon',
                            'type': f'context_{context_name.replace(" ", "_")}'
                        })
                        return coupon_result
                except (ValueError, IndexError):
                    continue
        
        # Look for percentage coupons in main product context
        percentage_patterns = [
            r'(\d+)%\s*off\s*coupon',
            r'coupon.*?(\d+)%\s*off',
            r'save\s*(\d+)%\s*with\s*coupon'
        ]
        
        for pattern in percentage_patterns:
            matches = re.findall(pattern, context_text, re.IGNORECASE)
            if matches:
                try:
                    percentage = int(matches[0])
                    if 0 < percentage <= 100:
                        logger.info(f"✅ Main product percentage coupon found in {context_name}: {percentage}% off")
                        coupon_result.update({
                            'available': True,
                            'value': 0.0,
                            'percentage': percentage,
                            'description': f'{percentage}% off coupon',
                            'type': f'percentage_{context_name.replace(" ", "_")}'
                        })
                        return coupon_result
                except (ValueError, IndexError):
                    continue
        
        return coupon_result
    
    def _is_main_product_coupon(self, coupon_elem) -> bool:
        """Check if coupon element belongs to main product, not related products"""
        # Check element and its parents for related products context
        current = coupon_elem
        for _ in range(10):  # Check up to 10 parent levels
            if current is None:
                break
                
            # Get all text content and attributes
            element_text = current.get_text(' ').lower() if hasattr(current, 'get_text') else ''
            classes = ' '.join(current.get('class', [])).lower()
            element_id = current.get('id', '').lower()
            
            # Patterns that indicate this is NOT a main product coupon
            related_product_patterns = [
                'related products', 'customers who viewed', 'customers also bought',
                'frequently bought together', 'similar items', 'recommended',
                'sponsored', 'compare with similar', 'carousel', 'slider',
                'you might also like', 'bundle', 'accessory'
            ]
            
            all_context = f"{element_text} {classes} {element_id}"
            if any(pattern in all_context for pattern in related_product_patterns):
                logger.debug(f"❌ Coupon in related products section detected")
                return False
                
            current = current.parent
            
        return True
    
    def _parse_coupon_value(self, text: str) -> float:
        """
        Parse coupon value from text
        
        Args:
            text: Text containing potential coupon value
            
        Returns:
            Coupon value as float, 0.0 if not found
        """
        if not text:
            return 0.0
        
        # Look for currency amounts in the text
        currency_patterns = [
            r'₹\s*([0-9,]+(?:\.[0-9]{2})?)',
            r'Rs\.?\s*([0-9,]+(?:\.[0-9]{2})?)',
            r'INR\s*([0-9,]+(?:\.[0-9]{2})?)'
        ]
        
        for pattern in currency_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    # Take the first match and clean it
                    value_text = matches[0].replace(',', '')
                    value = float(value_text)
                    # Reasonable coupon range check
                    if 1 <= value <= 50000:  # ₹1 to ₹50,000
                        return value
                except (ValueError, IndexError):
                    continue
        
        return 0.0
    
    def _parse_price_text(self, price_text: str) -> float:
        """
        Parse price from text string
        
        Args:
            price_text: Text containing price
            
        Returns:
            Price as float, 0.0 if parsing fails
        """
        if not price_text:
            return 0.0
        
        try:
            # Remove currency symbols and whitespace
            clean_text = re.sub(r'[₹,\s$£€]', '', price_text)
            
            # Extract numeric part
            price_match = re.search(r'(\d+(?:\.\d{2})?)', clean_text)
            if price_match:
                price = float(price_match.group(1))
                # Sanity check: reasonable price range
                if 0 < price < 10000000:  # Up to 1 crore
                    return price
        except (ValueError, AttributeError):
            pass
        
        return 0.0
    
    def _create_error_result(self, url: str, error: str) -> Dict:
        """Create standardized error result"""
        logger.error(f"❌ Error for {url}: {error}")
        return {
                'title': 'Unknown Product',
                'price': 0.0,
                'in_stock': False,
                'url': url,
                'store': 'amazon',
                'last_updated': datetime.utcnow().isoformat(),
                'extracted_via': 'requests',
                'success': False,
                'error': error
            }
    
    def cleanup(self) -> None:
        """Cleanup method for compatibility"""
        if hasattr(self.session, 'close'):
            self.session.close()
        logger.info("🧹 Amazon tracker cleanup completed")
    
    @classmethod
    def cleanup_all_drivers(cls) -> None:
        """Class method for cleanup compatibility"""
        logger.info("🧹 All drivers cleanup completed")