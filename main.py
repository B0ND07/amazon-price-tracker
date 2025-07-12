import os
import time
import logging
import schedule
import asyncio
import multiprocessing
import random
import json
import requests
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

# Third-party imports
from dotenv import load_dotenv

# Local imports
from telegram_bot import Product, StoreType
from tracker_manager import TrackerManager

# Load environment variables from .env file
load_dotenv(dotenv_path="config.env")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('price_tracker.log')
    ]
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_USER_ID')
SMTP_EMAIL = os.getenv('SMTP_EMAIL')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
COUPON_ALERT = os.getenv('COUPON_ALERT', 'False').lower() == 'true'

def send_telegram_message(message: str) -> bool:
    """Send a message to the admin via Telegram bot.
    
    Args:
        message: The message to send
        
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    if not TELEGRAM_BOT_TOKEN or not ADMIN_CHAT_ID:
        logger.warning("Telegram bot token or admin chat ID not configured")
        return False
        
    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': ADMIN_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False

PRODUCTS_FILE = 'products.json'

class ProductManager:
    """Manages product data storage and retrieval."""
    def __init__(self, filename: str = PRODUCTS_FILE):
        """Initialize the product manager.
        
        Args:
            filename: Path to the products JSON file
        """
        self.filename = filename
        self.products = {}
        self._load_products()
    
    def _load_products(self):
        """Load products from the JSON file."""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    data = json.load(f)
                    # Convert dict to Product objects
                    for product_id, product_data in data.items():
                        # Handle legacy products without store_type
                        if 'store_type' not in product_data:
                            product_data['store_type'] = StoreType.AMAZON
                        else:
                            product_data['store_type'] = StoreType(product_data['store_type'])
                        self.products[product_id] = Product(**product_data)
            except Exception as e:
                logger.error(f"Error loading products: {e}")
                self.products = {}
        else:
            # Load from environment variables if products.json doesn't exist
            self._migrate_from_env()
    
    def _migrate_from_env(self):
        """Migrate products from environment variables to JSON file."""
        for i in range(1, 4):
            url = os.getenv(f'PRODUCT_{i}_URL')
            price = os.getenv(f'PRODUCT_{i}_TARGET_PRICE')
            if url and price:
                try:
                    # Detect store type from URL
                    store_type = TrackerManager.detect_store_type(url)
                    if not store_type:
                        logger.warning(f"Could not determine store type for URL: {url}")
                        store_type = StoreType.AMAZON  # Default to Amazon for backward compatibility
                    
                    self.add_product(url, float(price), store_type=store_type)
                except ValueError as e:
                    logger.warning(f"Invalid price for product {i}: {e}")
                except Exception as e:
                    logger.error(f"Error migrating product {i}: {e}")
    
    def _save_products(self):
        """Save products to the JSON file."""
        with open(self.filename, 'w') as f:
            json.dump(
                {pid: asdict(product) 
                 for pid, product in self.products.items()}, 
                f, 
                indent=2
            )
    
    def add_product(self, url: str, target_price: float, **kwargs) -> Product:
        """Add a new product to track.
        
        Args:
            url: Product URL
            target_price: Target price for alerts
            **kwargs: Additional product attributes
            
        Returns:
            Product: The created product
            
        Raises:
            ValueError: If store type cannot be determined from URL
        """
        import uuid
        from telegram_bot import Product, StoreType
        
        # Get store type from kwargs or detect from URL
        store_type = kwargs.pop('store_type', None)
        if not store_type:
            store_type = TrackerManager.detect_store_type(url)
            if not store_type:
                raise ValueError("Could not determine store type from URL")
        
        product_id = str(uuid.uuid4())
        product = Product(
            id=product_id,
            url=url,
            target_price=target_price,
            title=kwargs.get('title'),
            current_price=kwargs.get('current_price'),
            coupon=kwargs.get('coupon'),
            tag=kwargs.get('tag'),
            store_type=store_type
        )
        self.products[product_id] = product
        self._save_products()
        return product
    
    def remove_product(self, product_id: str) -> bool:
        """Remove a product from tracking.
        
        Args:
            product_id: ID of the product to remove
            
        Returns:
            bool: True if product was removed, False if not found
        """
        if product_id in self.products:
            del self.products[product_id]
            self._save_products()
            return True
        return False
    
    def get_all_products(self) -> List[Product]:
        """Get all tracked products.
        
        Returns:
            List[Product]: List of all tracked products
        """
        return list(self.products.values())
    
    def get_product(self, product_id: str) -> Optional[Product]:
        """Get a product by ID.
        
        Args:
            product_id: ID of the product to get
            
        Returns:
            Optional[Product]: The product if found, None otherwise
        """
        return self.products.get(product_id)
    
    def update_product(self, product_id: str, **kwargs) -> bool:
        """Update product attributes.
        
        Args:
            product_id: ID of the product to update
            **kwargs: Attributes to update
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        if product_id in self.products:
            product = self.products[product_id]
            logger.info(f"Updating product {product_id} with data: {kwargs}")
            
            # Update product attributes
            for key, value in kwargs.items():
                if value is not None:  # Don't update with None values
                    setattr(product, key, value)
            
            try:
                self._save_products()
                logger.info("Product updated successfully")
                return True
            except Exception as e:
                logger.error(f"Error saving product updates: {e}")
                return False
        
        logger.error(f"Product {product_id} not found")
        return False

class PriceTracker:
    """Main price tracker class that supports multiple store types."""
    
    def __init__(self, email: str = None, password: str = None, 
                 smtp_address: str = "smtp.gmail.com", coupon_alert: bool = True):
        """Initialize the price tracker.
        
        Args:
            email: Email for notifications (optional)
            password: Password for email (optional)
            smtp_address: SMTP server address (default: smtp.gmail.com)
            coupon_alert: Whether to check for coupons (default: True)
        """
        self.email = email
        self.password = password
        self.smtp_address = smtp_address
        self.coupon_alert = coupon_alert
        self.product_manager = ProductManager()
        self.tracker_manager = TrackerManager(email, password)
        
        # Load global email alerts setting
        self.global_email_alerts = os.getenv('GLOBAL_EMAIL_ALERTS', 'True').lower() in ('true', '1', 't')
        logger.info(f"Initialized PriceTracker with global_email_alerts={self.global_email_alerts}")
    
    def add_product(self, url: str, target_price: float, **kwargs) -> Optional[Product]:
        """Add a product to track.
        
        Args:
            url: Product URL
            target_price: Target price for alerts
            **kwargs: Additional product attributes
            
        Returns:
            Optional[Product]: The created product or None if failed
        """
        try:
            return self.product_manager.add_product(url, target_price, **kwargs)
        except Exception as e:
            logger.error(f"Failed to add product: {e}")
            return None
    
    def remove_product(self, product_id: str) -> bool:
        """Remove a product from tracking.
        
        Args:
            product_id: ID of the product to remove
            
        Returns:
            bool: True if successful, False otherwise
        """
        return self.product_manager.remove_product(product_id)
    
    def get_all_products(self) -> List[Product]:
        """Get all tracked products.
        
        Returns:
            List[Product]: List of all tracked products
        """
        return self.product_manager.get_all_products()
    
    def get_product(self, product_id: str) -> Optional[Product]:
        """Get a specific product by ID.
        
        Args:
            product_id: ID of the product to get
            
        Returns:
            Optional[Product]: The product if found, None otherwise
        """
        return self.product_manager.get_product(product_id)
    
    def update_product(self, product_id: str, **kwargs) -> bool:
        """Update product details.
        
        Args:
            product_id: ID of the product to update
            **kwargs: Attributes to update
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        return self.product_manager.update_product(product_id, **kwargs)
    
    def check_price_and_coupon(self, product: Product) -> Dict:
        """Check price and coupon for a single product.
        
        Args:
            product: Product to check
            
        Returns:
            Dict containing updates if price dropped or coupon found
        """
        try:
            result = self.tracker_manager.check_price_drop(product)
            
            if not result:
                logger.error(f"No result returned for product {product.id}")
                return {}
            
            # Prepare updates
            updates = {
                'current_price': result.get('current_price'),
                'title': result.get('title', product.title)
            }
            
            if result.get('price_dropped', False):
                self._send_price_drop_notification(product, result)
            
            if result.get('coupon') and result.get('coupon') != getattr(product, 'coupon', None):
                if not result.get('price_dropped'):  # Don't send duplicate notifications
                    self._send_coupon_notification(product, result)
            
            return updates
            
        except requests.RequestException as e:
            # Only log request errors, don't send Telegram notification
            error_msg = f"Request error: {e}"
            logger.error(error_msg)
            return {}
            
        except Exception as e:
            # Only log unexpected errors, don't send Telegram notification
            error_msg = f"Unexpected error: {e}"
            logger.error(error_msg, exc_info=True)
            return {}

    def _send_price_drop_notification(self, product: Product, result: Dict) -> None:
        """Send a notification when a product's price drops below the target price.
        
        Args:
            product: The product with price drop
            result: Dictionary containing price drop details
        """
        try:
            current_price = result.get('current_price', 0) or 0
            previous_price = result.get('previous_price', 0) or 0
            title = result.get('title', getattr(product, 'title', 'Unknown Product'))
            
            # Calculate price difference and percentage
            if previous_price and previous_price > 0:
                price_diff = previous_price - current_price
                percent_off = (price_diff / previous_price) * 100 if previous_price > 0 else 0
                price_info = (
                    f"Price dropped from ₹{previous_price:,.2f} to ₹{current_price:,.2f} "
                    f"(Save: ₹{price_diff:,.2f}, {percent_off:.1f}% off)"
                )
            else:
                price_info = f"Price: ₹{current_price:,.2f}"
            
            # Prepare message
            message = (
                f"🎉 <b>Price Drop Alert!</b> 🎉\n\n"
                f"📦 <b>{title}</b>\n"
                f"🎯 <b>Target Price:</b> ₹{product.target_price:,.2f}\n"
                f"💰 <b>New Price:</b> ₹{current_price:,.2f}\n"
                f"🔗 <a href='{product.url}'>View Product</a>"
            )

            # Send email alert if enabled
            if self.global_email_alerts and self.email and self.password:
                self.send_email_alert(
                    {
                        'title': title,
                        'url': product.url,
                        'target_price': product.target_price
                    },
                    {
                        'current_price': current_price,
                        'previous_price': previous_price,
                        'coupon': result.get('coupon')
                    }
                )
            
            # Send Telegram notification
            asyncio.run(send_telegram_message(message))
            
            logger.info(f"Sent price drop notification for {title}")
            
        except Exception as e:
            logger.error(f"Error sending price drop notification: {e}", exc_info=True)

    def send_email_alert(self, product_data: dict, updates: dict) -> None:
        """Send an email alert for a product if email alerts are enabled."""
        # Check if global email alerts are enabled
        if not self.global_email_alerts:
            logger.info("Global email alerts are disabled. Skipping email alert.")
            return
            
        if not self.email or not self.password:
            logger.warning("Email credentials not configured. Skipping email alert.")
            return

        product_url = product_data.get('url', 'Unknown URL')
        product_title = product_data.get('title', 'Unknown Product')
        target_price = product_data.get('target_price', 0)
        current_price = updates.get('current_price', 0)
        coupon = updates.get('coupon')

        subject = f"🚨 Price Alert 🚨"
        
        # Create email body with HTML formatting
        body = f"""
        <html>
            <body>
                <h2>🚨 Price Alert for {product_title}</h2>
                <p>The price has dropped below your target price!</p>
                <p>Current Price: <strong>₹{current_price:,.2f}</strong></p>
                <p>Target Price: ₹{target_price:,.2f}</p>
        """
        
        if coupon:
            body += f"<p>🎉 <strong>COUPON AVAILABLE:</strong> {coupon}</p>"
        
        body += f"""
                <p><a href="{product_url}">View Product on Amazon</a></p>
                <p>Happy Shopping! 🛍️</p>
            </body>
        </html>
        """

        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as connection:
                connection.login(self.email, self.password)
                
                # Create message
                msg = f"Subject: {subject}\n"
                msg += "MIME-Version: 1.0\n"
                msg += "Content-type: text/html\n"
                msg += f"\n{body}"
                
                connection.sendmail(
                    from_addr=self.email,
                    to_addrs=self.email,
                    msg=msg.encode('utf-8')
                )
                
            logger.info(f"📧 Email alert sent for {product_title}")
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False

    def check_all_products(self):
        """Check all products and send alerts if necessary."""
        try:
            products = self.product_manager.get_all_products()
            if not products:
                logger.info("No products to track. Use /add to add a product.")
                return

            logger.info(f"\n⏰ Starting price check at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 50)

            # Convert any Product objects to dictionaries
            product_list = []
            for product in products:
                if hasattr(product, 'to_dict'):  # If it's a Product object with to_dict method
                    product_list.append(product.to_dict())
                elif isinstance(product, dict):  # If it's already a dictionary
                    product_list.append(product)
                else:  # Try to convert using vars() as fallback
                    try:
                        product_list.append(vars(product))
                    except Exception as e:
                        logger.error(f"Could not convert product to dict: {e}")
                        continue

            # Process each product
            for idx, product_data in enumerate(product_list, 1):
                try:
                    if not product_data:
                        logger.error(f"Empty product data at index {idx}")
                        continue
                        
                    # Convert to Product object if it's a dict
                    from telegram_bot import Product  # Import from telegram_bot where Product is defined
                    if isinstance(product_data, dict):
                        try:
                            product = Product(**product_data)
                        except Exception as e:
                            logger.error(f"Failed to create Product from dict at index {idx}: {e}")
                            continue
                    else:
                        product = product_data
                        
                    if not hasattr(product, 'url'):
                        logger.error(f"Product at index {idx} has no URL")
                        continue
                        
                    logger.info(f"Checking product {idx}: {product.url}")
                    updates = self.check_price_and_coupon(product)
                    
                    if updates:
                        self.send_email_alert(vars(product) if hasattr(product, '__dict__') else product, updates)
                    
                    # Random delay between 3-7 seconds to avoid being blocked
                    time.sleep(random.uniform(3, 7))
                    
                except Exception as e:
                    logger.error(f"Error checking product {idx}: {e}")
                    continue

            logger.info(f"✅ Completed checking {len(product_list)} products")
            logger.info("⏱️ Next check in 10 minutes...")
            
        except Exception as e:
            logger.error(f"Fatal error in check_all_products: {e}")
            raise

def run_tracker():
    """Run the price tracker in a separate process."""
    # Initialize tracker
    tracker = PriceTracker(
        email=os.getenv('SMTP_EMAIL'),
        password=os.getenv('SMTP_PASSWORD'),
        coupon_alert=os.getenv('COUPON_ALERT', 'False').lower() == 'true'
    )
    
    # Schedule the price check to run every 10 minutes
    schedule.every(10).minutes.do(tracker.check_all_products)
    
    # Initial run
    tracker.check_all_products()
    
    # Keep the process running
    while True:
        schedule.run_pending()
        time.sleep(1)

def run_telegram_bot():
    """Run the Telegram bot in a separate process."""
    from telegram_bot import main as telegram_main
    asyncio.run(telegram_main())

def main():
    """Main function to run both the Telegram bot and price tracker in separate processes."""
    # Create processes
    tracker_process = multiprocessing.Process(target=run_tracker)
    bot_process = multiprocessing.Process(target=run_telegram_bot)
    
    # Start processes
    tracker_process.start()
    bot_process.start()
    
    try:
        # Keep the main process running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # Terminate child processes on keyboard interrupt
        tracker_process.terminate()
        bot_process.terminate()
        tracker_process.join()
        bot_process.join()
        logger.info("Processes terminated")

if __name__ == "__main__":
    main()