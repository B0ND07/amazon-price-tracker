import os
import time
import logging
import schedule
import asyncio
import multiprocessing
import random
import json
import requests
import smtplib
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

# Third-party imports
from dotenv import load_dotenv

# Local imports
from product_manager import get_product_manager, Product, StoreType
from tracker_manager import TrackerManager

# Load environment variables from .env file
load_dotenv(dotenv_path="config.env")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
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

# Use persistent data directory if available (for Docker), otherwise use local data directory
DATA_DIR = os.getenv('DATA_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
PRODUCTS_FILE = os.path.join(DATA_DIR, 'products.json')

# ProductManager class moved to product_manager.py for unified management

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
        self.product_manager = get_product_manager()
        self.tracker_manager = TrackerManager(email, password)
        
        # Reload environment variables
        from dotenv import load_dotenv
        load_dotenv(dotenv_path="config.env", override=True)
        
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
            
            # Store coupon information (no notification needed)
            if result.get('coupon'):
                updates['coupon_info'] = result['coupon']  # Store full coupon details
                if 'final_price' in result:
                    updates['final_price'] = result['final_price']
            
            # Store stock availability
            if 'in_stock' in result:
                updates['in_stock'] = result['in_stock']
            
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
            
            # Check for coupon information
            coupon_info = ""
            final_price_info = ""
            
            if result.get('coupon') and isinstance(result['coupon'], dict):
                coupon_data = result['coupon']
                if coupon_data.get('available'):
                    coupon_value = coupon_data.get('value', 0)
                    coupon_desc = coupon_data.get('description', f'₹{coupon_value} coupon')
                    coupon_info = f"🎫 <b>Coupon Available:</b> {coupon_desc}\n"
                    
                    # Show final price if available
                    if result.get('final_price') and result['final_price'] != current_price:
                        final_price_info = f"💵 <b>Final Price (after coupon):</b> ₹{result['final_price']:,.2f}\n"
            
            # Prepare message
            message = (
                f"🎉 <b>Price Drop Alert!</b> 🎉\n\n"
                f"📦 <b>{title}</b>\n"
                f"🎯 <b>Target Price:</b> ₹{product.target_price:,.2f}\n"
                f"💰 <b>New Price:</b> ₹{current_price:,.2f}\n"
                f"{coupon_info}"
                f"{final_price_info}"
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
            send_telegram_message(message)
            
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
            # Reload products from file to ensure we have the latest data
            self.product_manager.reload()
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
                        # Save the updates (like title, current_price) back to the product
                        if hasattr(product, 'id') and product.id:
                            self.update_product(
                                product.id,
                                **{k: v for k, v in updates.items() if v is not None}
                            )
                        # self.send_email_alert(vars(product) if hasattr(product, '__dict__') else product, updates)
                    
                    # Add delay between products (but not after the last one)
                    if idx < len(product_list):
                        delay = random.uniform(10, 15)
                        logger.info(f"⏳ Waiting {delay:.1f} seconds before next product check...")
                        time.sleep(delay)
                    
                except Exception as e:
                    logger.error(f"Error checking product {idx}: {e}")
                    # Still add delay even if there was an error, unless it's the last product
                    if idx < len(product_list):
                        delay = random.uniform(10, 15)
                        logger.info(f"⏳ Error occurred, still waiting {delay:.1f} seconds before next product...")
                        time.sleep(delay)
                    continue

            logger.info(f"✅ Completed checking {len(product_list)} products")
            logger.info("⏱️ Next check in 10 minutes...")
            
        except Exception as e:
            logger.error(f"Fatal error in check_all_products: {e}")
            raise

def cleanup_chrome_processes():
    """Clean up orphaned Chrome processes periodically"""
    try:
        import psutil
        cleaned_count = 0
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            try:
                if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                    # Kill very old Chrome processes (older than 2 hours)
                    if proc.create_time() < time.time() - 7200:
                        logger.info(f"Killing old Chrome process: {proc.pid}")
                        proc.kill()
                        cleaned_count += 1
                    # Kill zombie processes
                    elif proc.status() == psutil.STATUS_ZOMBIE:
                        logger.info(f"Killing zombie Chrome process: {proc.pid}")
                        proc.kill()
                        cleaned_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                continue
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} Chrome processes")
            
    except Exception as e:
        logger.debug(f"Error during Chrome process cleanup: {e}")

def run_tracker():
    """Run the price tracker in a separate process with enhanced stability."""
    # Initialize tracker
    tracker = PriceTracker(
        email=os.getenv('SMTP_EMAIL'),
        password=os.getenv('SMTP_PASSWORD'),
        coupon_alert=os.getenv('COUPON_ALERT', 'False').lower() == 'true'
    )
    
    # Schedule the price check to run every 10-20 minutes (randomized)
    schedule.every(random.randint(10, 20)).minutes.do(tracker.check_all_products)
    
    # Schedule periodic Chrome process cleanup every hour
    schedule.every().hour.do(cleanup_chrome_processes)
    
    # Schedule driver pool cleanup every 2 hours
    def cleanup_driver_pools():
        try:
            from trackers.amazon_tracker import AmazonPriceTracker
            from trackers.flipkart_tracker import FlipkartPriceTracker
            AmazonPriceTracker.cleanup_all_drivers()
            FlipkartPriceTracker.cleanup_all_drivers()
            logger.info("Periodic driver pool cleanup completed")
        except Exception as e:
            logger.error(f"Error during driver pool cleanup: {e}")
    
    schedule.every(2).hours.do(cleanup_driver_pools)
    
    # Initial cleanup
    cleanup_chrome_processes()
    
    # Initial run
    tracker.check_all_products()
    
    # Keep the process running with health monitoring
    last_health_check = time.time()
    
    while True:
        try:
            schedule.run_pending()
            
            # Health check every 30 minutes
            current_time = time.time()
            if current_time - last_health_check > 1800:  # 30 minutes
                logger.info("Performing health check...")
                
                # Force garbage collection
                import gc
                gc.collect()
                
                # Log memory usage if psutil is available
                try:
                    import psutil
                    process = psutil.Process()
                    memory_mb = process.memory_info().rss / 1024 / 1024
                    logger.info(f"Memory usage: {memory_mb:.1f} MB")
                    
                    # Restart if memory usage is too high (over 1GB)
                    if memory_mb > 1024:
                        logger.warning(f"High memory usage detected: {memory_mb:.1f} MB. Cleaning up...")
                        cleanup_driver_pools()
                        cleanup_chrome_processes()
                        gc.collect()
                        
                except ImportError:
                    pass
                
                last_health_check = current_time
                
            time.sleep(1)
            
        except KeyboardInterrupt:
            logger.info("Tracker process interrupted, cleaning up...")
            cleanup_driver_pools()
            cleanup_chrome_processes()
            break
        except Exception as e:
            logger.error(f"Error in tracker main loop: {e}")
            time.sleep(5)  # Brief pause before continuing

def run_telegram_bot():
    """Run the Telegram bot in a separate process."""
    from telegram_bot import main as telegram_main
    try:
        telegram_main()  # telegram_main is not async, so no need for asyncio.run()
    except (SystemExit, KeyboardInterrupt):
        logger.info("Telegram bot process terminated")
    except Exception as e:
        logger.error(f"Error in Telegram bot process: {e}")
        raise
def main():
    """Main function to run both the Telegram bot and price tracker in separate processes."""
    while True:  # Main restart loop
        # Remove any existing restart file
        if os.path.exists('.restart'):
            try:
                os.remove('.restart')
            except Exception as e:
                logger.warning(f"Failed to remove restart file: {e}")
        
        # Create processes
        tracker_process = multiprocessing.Process(target=run_tracker, name="tracker")
        bot_process = multiprocessing.Process(target=run_telegram_bot, name="telegram_bot")
        
        logger.info("Starting processes...")
        tracker_process.start()
        bot_process.start()
        
        try:
            # Monitor processes and check for restart signal
            while True:
                time.sleep(5)  # Check every 5 seconds
                
                # Check if either process has died
                if not tracker_process.is_alive() or not bot_process.is_alive():
                    logger.error("One of the processes has died")
                    break
                    
                # Check for restart signal
                if os.path.exists('.restart'):
                    logger.info("Restart signal received, initiating restart...")
                    break
                    
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
            
        finally:
            # Terminate child processes
            logger.info("Terminating processes...")
            for proc in [tracker_process, bot_process]:
                if proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=5)
                    if proc.exitcode is None:
                        logger.warning(f"Process {proc.name} did not terminate gracefully, forcing exit")
                        proc.kill()
            
            # Check if we should restart
            should_restart = os.path.exists('.restart')
            
            # Clean up restart file if it exists
            if should_restart:
                try:
                    os.remove('.restart')
                    logger.info("Restart file cleaned up")
                except Exception as e:
                    logger.warning(f"Failed to clean up restart file: {e}")
            
            # If we're here because of a restart, continue the outer loop
            if should_restart:
                logger.info("Restarting application...")
                continue
                
            # If we're here because of a process death or keyboard interrupt, exit
            logger.info("Shutting down application...")
            break
    
    logger.info("Application shutdown complete")

if __name__ == "__main__":
    main()