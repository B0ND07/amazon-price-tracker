import requests
from bs4 import BeautifulSoup
import lxml
import smtplib
import schedule
import time
import json
import asyncio
from typing import List, Optional
from datetime import datetime
import random
import re
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from dotenv import load_dotenv
import os
import logging
from pathlib import Path
import multiprocessing

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

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_USER_ID')

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
    def __init__(self, filename: str = PRODUCTS_FILE):
        self.filename = filename
        self.products = {}
        self._load_products()
    
    def _load_products(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    self.products = json.load(f)
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
                    self.add_product(url, float(price))
                except ValueError:
                    logger.warning(f"Invalid price for product {i}")
    
    def _save_products(self):
        with open(self.filename, 'w') as f:
            json.dump(self.products, f, indent=2)
    
    def add_product(self, url: str, target_price: float, **kwargs):
        import uuid
        product_id = str(uuid.uuid4())
        self.products[product_id] = {
            'url': url,
            'target_price': target_price,
            'title': kwargs.get('title'),
            'current_price': kwargs.get('current_price'),
            'coupon': kwargs.get('coupon'),
            'id': product_id
        }
        self._save_products()
        return self.products[product_id]
    
    def remove_product(self, product_id: str) -> bool:
        if product_id in self.products:
            del self.products[product_id]
            self._save_products()
            return True
        return False
    
    def get_all_products(self) -> list:
        return list(self.products.values())
    
    def get_product(self, product_id: str) -> Optional[dict]:
        return self.products.get(product_id)
    
    def update_product(self, product_id: str, **kwargs):
        if product_id in self.products:
            logger.info(f"ProductManager: Updating product {product_id} with data: {kwargs}")
            logger.info(f"Product data before update: {self.products[product_id]}")
            self.products[product_id].update(kwargs)
            logger.info(f"Product data after update: {self.products[product_id]}")
            try:
                self._save_products()
                logger.info("Products saved successfully")
                return True
            except Exception as e:
                logger.error(f"Error saving products: {e}")
                return False
        logger.error(f"Product {product_id} not found")
        return False

class AmazonPriceTracker:
    def __init__(self, email: str = None, password: str = None, 
                 smtp_address: str = "smtp.gmail.com", coupon_alert: bool = True):
        self.headers_list = [
            {
                'Accept-Language': "en-IN,en;q=0.9",
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive'
            },
            {
                'Accept-Language': "en-US,en;q=0.9",
                'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive'
            },
            {
                'Accept-Language': "en-GB,en;q=0.9",
                'User-Agent': "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive'
            }
        ]
        self.email = email
        self.password = password
        self.smtp_address = smtp_address
        self.product_manager = ProductManager()
        self.session = self._create_session()
        self.coupon_alert = coupon_alert
        # Load global email alerts setting
        self.global_email_alerts = os.getenv('GLOBAL_EMAIL_ALERTS', 'True').lower() in ('true', '1', 't')
        logger.info(f"Initialized AmazonPriceTracker with global_email_alerts={self.global_email_alerts}")

    def _create_session(self):
        """Create a session with retry strategy"""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,  # number of retries
            backoff_factor=1,  # wait 1, 2, 4 seconds between retries
            status_forcelist=[500, 502, 503, 504, 429]  # status codes to retry on
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _get_random_headers(self):
        """Get random headers from the headers list"""
        return random.choice(self.headers_list)

    def add_product(self, url: str, target_price: float, **kwargs):
        """Add a product to track."""
        return self.product_manager.add_product(url, target_price, **kwargs)
    
    def remove_product(self, product_id: str) -> bool:
        """Remove a product from tracking."""
        return self.product_manager.remove_product(product_id)
    
    def get_all_products(self) -> list:
        """Get all tracked products."""
        return self.product_manager.get_all_products()
    
    def get_product(self, product_id: str) -> Optional[dict]:
        """Get a specific product by ID."""
        return self.product_manager.get_product(product_id)
    
    def update_product(self, product_id: str, **kwargs) -> bool:
        """Update product details."""
        logger.info(f"Updating product {product_id} with data: {kwargs}")
        result = self.product_manager.update_product(product_id, **kwargs)
        logger.info(f"Product {product_id} update result: {result}")
        return result

    def check_price_and_coupon(self, product_data: dict) -> dict:
        """Check price and coupon for a single product. Returns updates if price dropped or coupon found."""
        url = product_data.get('url')
        if not url:
            logger.error("Product URL not found")
            return {}

        # Initialize variables
        updates = {}
        message_parts = []
        
        try:
            # Get random headers
            headers = self._get_random_headers()
            
            # Add a small delay to avoid being blocked
            time.sleep(random.uniform(1, 3))
            
            # Make the request
            response = self.session.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                # Only log 404 errors to console, don't send Telegram notification
                if response.status_code != 404:
                    logger.warning(f"Failed to retrieve page. Status code: {response.status_code}")
                    send_telegram_message(f"❌ Failed to retrieve page (Status: {response.status_code})\n\n🔗 {url}")
                return {}

            soup = BeautifulSoup(response.content, 'lxml')
            
            # Get product title with multiple fallback options
            title = 'Unknown Product'
            title_selectors = [
                ('span', {'id': 'productTitle'}),
                ('span', {'id': 'title'}),
                ('h1', {}),  # Generic h1 as last resort
                ('title', {})  # Fallback to page title
            ]
            
            for tag, attrs in title_selectors:
                element = soup.find(tag, **attrs)
                if element:
                    title = element.get_text().strip()
                    if title and title != 'Amazon.in':  # Skip default/empty titles
                        break
            
            logger.info(f"Extracted title: {title}")
            
            # Update title if we found a valid one and it's different from current
            current_title = product_data.get('title')
            if title and title != 'Unknown Product' and title != 'Amazon.in' and title != current_title:
                updates['title'] = title
                logger.info(f"Title update queued: '{current_title}' -> '{title}'")
                logger.info(f"Updates dict before update: {updates}")
            
            # Get price
            price_element = (
                soup.find('span', class_='a-offscreen') or
                soup.find('span', class_='a-price-whole')
            )
            
            if not price_element:
                logger.warning("Price element not found, trying alternate selectors...")
                # Try alternate selectors
                price_element = soup.find('span', class_=lambda x: x and 'price' in x.lower())
                if price_element:
                    try:
                        price_text = price_element.get_text().strip()
                        if not price_text:
                            logger.warning("Empty price text in alternate selector")
                            return {}
                            
                        digits = ''.join(filter(str.isdigit, price_text))
                        if not digits:
                            logger.warning(f"No digits found in alternate price text: {price_text}")
                            return {}
                            
                        if '.' in price_text[-3:]:
                            price = float(digits)/100
                        else:
                            price = float(digits)
                            
                        updates['current_price'] = price
                        message_parts.append(f"ℹ️ Price found via alternate selector: ₹{price:,.2f}")
                        logger.info(f"Price found via alternate selector: {title} is now ₹{price:,.2f}")
                        
                    except (ValueError, IndexError) as e:
                        logger.error(f"Error parsing alternate price: {e}")
                        return {}
                else:
                    logger.warning("Price not found in alternate selectors either")
                    return {}
            
            price_text = price_element.get_text().strip()
            price = float(re.sub(r'[^\d.]', '', price_text))
            
            updates = {}
            message_parts = []
            
            # Check if price dropped below target
            target_price = product_data.get('target_price')
            if target_price and price <= target_price:
                updates['current_price'] = price
                alert_msg = (
                    f"🎉 <b>Price Drop Alert!</b> 🎉\n\n"
                    f"📦 <b>{title}</b>\n"
                    f"💰 <b>New Price:</b> ₹{price:,.2f}\n"
                    f"🎯 <b>Your Target:</b> ₹{target_price:,.2f}\n"
                    f"💵 <b>You Save:</b> ₹{target_price - price:,.2f} ({(1 - (price / target_price)) * 100:.1f}%)\n\n"
                    f"🔗 <a href='{url}'>Buy Now</a>"
                )
                message_parts.append(alert_msg)
                logger.info(f"Price alert! {title} is now ₹{price:,.2f} (Target: ₹{target_price:,.2f})")
            
            # Check for coupons if enabled
            if self.coupon_alert:
                coupon_element = (
                    soup.find('span', class_=lambda x: x and 'coupon' in x.lower()) or
                    soup.find('span', class_=lambda x: x and 'deal' in x.lower())
                )
                coupon = coupon_element.get_text().strip() if coupon_element else None
                if coupon:
                    updates['coupon'] = coupon
                    coupon_msg = f"🎫 <b>Coupon Available!</b>\n\n{coupon}\n\n🔗 <a href='{url}'>Apply Coupon</a>"
                    message_parts.append(coupon_msg)
                    logger.info(f"Coupon Available: {coupon}")

            # Always update the product with any changes (price, title, etc.)
            if updates:
                logger.info(f"Saving updates for product {product_data.get('id')}: {updates}")
                try:
                    # Get current product data
                    current_product = self.get_product(product_data['id'])
                    if current_product:
                        # Only send email alerts if they are enabled globally
                        if message_parts and ('current_price' in updates or 'coupon' in updates):
                            message = "\n\n---\n\n".join(message_parts)
                            send_telegram_message(message)
                            
                        # Merge updates with current data
                        updated_data = {**current_product, **updates}
                        # Save the merged data
                        updated = self.update_product(product_data['id'], **updated_data)
                        if updated:
                            logger.info(f"Successfully updated product {product_data.get('id')}")
                            # Verify the update was saved
                            updated_product = self.get_product(product_data['id'])
                            if updated_product and all(updated_product.get(k) == v for k, v in updates.items() if k in updated_product):
                                logger.info("Update verified in database")
                            else:
                                logger.error(f"Update verification failed! Expected: {updates}, Got: {updated_product}")
                        else:
                            logger.error("Failed to update product")
                    else:
                        logger.error(f"Could not find product {product_data['id']} to update")
                except Exception as e:
                    logger.error(f"Error updating product: {e}", exc_info=True)

            return updates

        except requests.RequestException as e:
            # Only log request errors, don't send Telegram notification
            error_msg = f"Request error: {e}"
            logger.error(error_msg)
            return {}
        except Exception as e:
            # Only log unexpected errors, don't send Telegram notification
            error_msg = f"Unexpected error: {e}"
            logger.error(error_msg)
            return {}

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

        subject = f"🚨 Price Alert: {product_title}"
        
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
            for idx, product in enumerate(product_list, 1):
                try:
                    if not product or not isinstance(product, dict):
                        logger.error(f"Invalid product data at index {idx}")
                        continue
                        
                    logger.info(f"Checking product {idx}: {product.get('url')}")
                    updates = self.check_price_and_coupon(product)
                    
                    if updates:
                        self.send_email_alert(product, updates)
                    
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
    tracker = AmazonPriceTracker(
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