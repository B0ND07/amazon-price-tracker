"""Tracker Manager for handling multiple store-specific price trackers.

This module provides the TrackerManager class which acts as a facade for
interacting with different store-specific price trackers (Amazon only - Flipkart disabled).
"""

import logging
import random
import time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import asdict

from product_manager import Product, StoreType
from trackers.amazon_tracker import AmazonPriceTracker
# from trackers.flipkart_tracker import FlipkartPriceTracker  # Disabled

logger = logging.getLogger(__name__)

class TrackerManager:
    """Manages different price trackers based on store type.
    
    This class serves as a facade that routes product tracking requests
    to the appropriate store-specific tracker based on the product's store type.
    """
    
    def __init__(self, email: str = None, password: str = None):
        """Initialize the tracker manager.
        
        Args:
            email: Email for notifications (optional)
            password: Password for email (optional)
        """
        self.email = email
        self.password = password
        
        # Initialize trackers for each supported store type
        self.trackers = {
            StoreType.AMAZON: AmazonPriceTracker(email, password)
            # StoreType.FLIPKART: FlipkartPriceTracker(email, password)  # Disabled
        }
    
    def get_tracker(self, store_type):
        """Get the appropriate tracker for the given store type.
        
        Args:
            store_type: Store type (AMAZON only - FLIPKART disabled) - can be enum or string
            
        Returns:
            The appropriate price tracker instance
            
        Raises:
            ValueError: If no tracker is available for the given store type
        """
        # Handle both string and enum store_type values
        if isinstance(store_type, str):
            try:
                store_type = StoreType(store_type)
            except ValueError:
                raise ValueError(f"Invalid store type string: {store_type}")
        
        tracker = self.trackers.get(store_type)
        if not tracker:
            raise ValueError(f"No tracker available for store type: {store_type}")
        return tracker
    
    def get_product_info(self, product: Product) -> Dict[str, Any]:
        """Get product information using the appropriate tracker.
        
        Args:
            product: Product to get info for
            
        Returns:
            Dict containing product information with keys:
            - price: Current price (float)
            - title: Product title (str)
            - coupon: Optional coupon/discount text (str or None)
            - url: Product URL (str)
            - in_stock: Whether the product is in stock (bool)
            
        Raises:
            ValueError: If product data is invalid or tracker not found
            Exception: For any errors during product info retrieval
        """
        if not product or not product.url:
            raise ValueError("Invalid product or missing URL")
            
        tracker = self.get_tracker(product.store_type)
        
        # Add a small delay to avoid overwhelming the target site
        time.sleep(random.uniform(1, 3))
        
        try:
            product_info = tracker.get_product_info(product.url)
            logger.info(f"Retrieved product info: {product_info}")
            return product_info
        except Exception as e:
            logger.error(f"Error getting product info for {product.url}: {e}")
            
            # Return fallback information instead of raising exception
            # This ensures the application continues running even with errors
            if hasattr(product, 'title') and product.title:
                # If we already have a product title in the database, use it for the fallback
                fallback_info = {
                    'title': product.title,
                    'price': 0,  # We can't determine the price during an error
                    'in_stock': False,  # Assume not in stock during error
                    'url': product.url,
                    'store': product.store_type.value.lower(),
                    'last_updated': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    'error': str(e)
                }
                
                # Add bot detection info if applicable
                if 'bot detection' in str(e).lower() or 'captcha' in str(e).lower():
                    fallback_info['bot_detected'] = True
                    fallback_info['title'] = f"{product.title} (Tracking Blocked)"
                    logger.warning(f"Amazon bot detection for product: {product.title}")
                
                logger.info(f"Using fallback product information for {product.url}")
                return fallback_info
            else:
                # If we don't have the product in the database yet, we need to raise
                # so it doesn't get added with incomplete information
                raise
    
    def check_price_drop(self, product: Product) -> Dict[str, Any]:
        """Check if the price has dropped for a product.
        
        Args:
            product: Product to check
            
        Returns:
            Dict containing:
                - price_dropped: bool - Whether the price dropped below target
                - current_price: float - Current price (0 if not available)
                - previous_price: float - Previous known price
                - coupon: Optional[str] - Any available coupon/discount text
                - title: str - Product title (if available)
                - in_stock: bool - Whether the product is in stock
                - error: Optional[str] - Error message if any occurred
        """
        if not product or not product.url:
            return {
                'price_dropped': False,
                'current_price': 0,
                'previous_price': getattr(product, 'current_price', 0),
                'error': 'Invalid product or missing URL'
            }
            
        try:
            info = self.get_product_info(product)
            
            # Safely get and convert prices, defaulting to None if not available
            try:
                current_price = float(info.get('price')) if info.get('price') is not None else None
            except (TypeError, ValueError):
                current_price = None
                
            try:
                previous_price = float(product.current_price) if hasattr(product, 'current_price') and product.current_price is not None else None
            except (TypeError, ValueError):
                previous_price = None
            
            # Only consider it a price drop if we have both current and target prices
            price_dropped = False
            if current_price is not None and hasattr(product, 'target_price') and product.target_price is not None:
                try:
                    price_dropped = (current_price > 0 and 
                                   float(product.target_price) > 0 and
                                   current_price <= float(product.target_price))
                except (TypeError, ValueError):
                    logger.warning(f"Invalid target price for product: {getattr(product, 'title', '')}")
            
            # Get a meaningful product identifier for logging
            product_identifier = 'product'
            if hasattr(product, 'title') and product.title:
                product_identifier = product.title
            elif hasattr(product, 'url') and product.url:
                # Use the last part of the URL as identifier if no title
                product_identifier = product.url.split('/')[-1][:30]  # Truncate long URLs
                if len(product_identifier) < 3:  # If too short, use a different approach
                    product_identifier = f"product at {product.url[:20]}..."
            
            # Log price change if we have both current and previous prices
            if current_price is not None and previous_price is not None and previous_price > 0:
                if current_price != previous_price:
                    change = current_price - previous_price
                    change_pct = (change / previous_price) * 100
                    change_type = "decreased" if change < 0 else "increased"
                    logger.info(
                        f"Price {change_type} for {product_identifier}: "
                        f"₹{previous_price:,.2f} → ₹{current_price:,.2f} "
                        f"({change_pct:+.1f}%)"
                    )
            elif current_price is not None and previous_price is None:
                logger.info(
                    f"Initial price for {product_identifier}: "
                    f"₹{current_price:,.2f}"
                )
            
            return {
                'price_dropped': price_dropped,
                'current_price': current_price,
                'previous_price': previous_price,
                'coupon': info.get('coupon'),
                'title': info.get('title', getattr(product, 'title', '')),
                'in_stock': info.get('in_stock', True),
                'url': info.get('url', getattr(product, 'url', ''))
            }
            
        except Exception as e:
            logger.error(f"Error checking price drop for {getattr(product, 'url', 'unknown')}: {e}", 
                        exc_info=True)
            return {
                'price_dropped': False,
                'current_price': 0,
                'previous_price': getattr(product, 'current_price', 0),
                'coupon': None,
                'title': getattr(product, 'title', ''),
                'in_stock': False,
                'error': str(e)
            }
    
    @staticmethod
    def detect_store_type(url: str) -> Optional[StoreType]:
        """Detect the store type from a URL.
        
        Args:
            url: Product URL to analyze
            
        Returns:
            StoreType or None if not recognized
            
        Examples:
            >>> TrackerManager.detect_store_type("https://www.amazon.in/dp/B0ABC12345")
            <StoreType.AMAZON: 'amazon'>
            # >>> TrackerManager.detect_store_type("https://www.flipkart.com/p/xyz")  # Disabled
            # <StoreType.FLIPKART: 'flipkart'>  # Disabled
            >>> TrackerManager.detect_store_type("https://example.com") is None
            True
        """
        if not url or not isinstance(url, str):
            return None
            
        url = url.lower().strip()
        
        # Check for Amazon URLs
        if 'amazon.' in url and any(x in url for x in ['/dp/', '/gp/', '/product/']):
            return StoreType.AMAZON
            
        # Check for Flipkart URLs - DISABLED
        # if 'flipkart.com' in url and any(x in url for x in ['/p/', '/product/']):
        #     return StoreType.FLIPKART
            
        # Try to match common patterns that might be missing standard paths
        if 'amzn.' in url or '/amazon.' in url:
            return StoreType.AMAZON
            
        # if 'flipkart.' in url or '/fk/' in url:
        #     return StoreType.FLIPKART
            
        logger.warning(f"Could not detect store type for URL: {url}")
        return None
