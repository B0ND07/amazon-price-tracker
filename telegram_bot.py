import json
import os
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import asdict, dataclass
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, CallbackQueryHandler, ContextTypes
)
from dotenv import load_dotenv, set_key

# Load environment variables
load_dotenv(dotenv_path="config.env")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
PRODUCTS_FILE = 'products.json'
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', 0))

from enum import Enum, auto

class StoreType(Enum):
    AMAZON = 'amazon'
    FLIPKART = 'flipkart'

@dataclass
class Product:
    url: str
    target_price: float
    title: Optional[str] = None
    current_price: Optional[float] = None
    coupon: Optional[str] = None
    id: Optional[str] = None
    tag: Optional[str] = None
    store_type: StoreType = StoreType.AMAZON  # Default to Amazon for backward compatibility

class ProductManager:
    def __init__(self, filename: str = PRODUCTS_FILE):
        self.filename = filename
        self.products: Dict[str, Product] = {}
        self._load_products()
    
    def _product_to_dict(self, product: Product) -> dict:
        """Convert a Product to a dictionary, handling enums properly."""
        data = asdict(product)
        # Convert StoreType enum to its value for JSON serialization
        if 'store_type' in data and data['store_type'] is not None:
            data['store_type'] = data['store_type'].value
        return data
    
    def _dict_to_product(self, data: dict) -> Product:
        """Convert a dictionary to a Product, handling enums properly."""
        # Convert store_type string back to StoreType enum
        if 'store_type' in data and isinstance(data['store_type'], str):
            data['store_type'] = StoreType(data['store_type'])
        return Product(**data)
    
    def _load_products(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    data = json.load(f)
                    self.products = {
                        pid: self._dict_to_product(product_data)
                        for pid, product_data in data.items()
                    }
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding products JSON: {e}")
                # Try to recover by creating a backup of the corrupted file
                try:
                    import shutil
                    backup_file = f"{self.filename}.bak.{int(time.time())}"
                    shutil.copy2(self.filename, backup_file)
                    logger.info(f"Created backup of corrupted file at {backup_file}")
                except Exception as backup_error:
                    logger.error(f"Failed to create backup: {backup_error}")
                self.products = {}
            except Exception as e:
                logger.error(f"Error loading products: {e}")
                self.products = {}
    
    def _save_products(self):
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(os.path.abspath(self.filename)), exist_ok=True)
            
            # Prepare data for JSON serialization
            data_to_save = {
                pid: self._product_to_dict(product)
                for pid, product in self.products.items()
            }
            
            # Write to a temporary file first
            temp_file = f"{self.filename}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(data_to_save, f, indent=2)
            
            # Atomic rename to ensure data integrity
            if os.path.exists(self.filename):
                os.replace(temp_file, self.filename)
            else:
                os.rename(temp_file, self.filename)
                
        except Exception as e:
            logger.error(f"Error saving products: {e}")
            # If there was an error, clean up the temp file if it exists
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as cleanup_error:
                    logger.error(f"Failed to clean up temp file: {cleanup_error}")
    
    def add_product(self, url: str, target_price: float, tag: Optional[str] = None, store_type: StoreType = StoreType.AMAZON) -> Product:
        import uuid
        product_id = str(uuid.uuid4())
        product = Product(
            id=product_id,
            url=url,
            target_price=target_price,
            tag=tag,
            store_type=store_type
        )
        self.products[product_id] = product
        self._save_products()
        return product
    
    def remove_product(self, product_id: str) -> bool:
        if product_id in self.products:
            del self.products[product_id]
            self._save_products()
            return True
        return False
    
    def get_all_products(self) -> List[Product]:
        return list(self.products.values())
    
    def get_product(self, product_id: str) -> Optional[Product]:
        return self.products.get(product_id)

# Initialize product manager
product_manager = ProductManager()

# Helper functions
def update_global_email_alerts(enabled: bool) -> None:
    """Update the global email alerts setting in config.env"""
    config_path = 'config.env'
    try:
        # Read current content
        with open(config_path, 'r') as f:
            lines = f.readlines()
        
        # Update or add GLOBAL_EMAIL_ALERTS
        found = False
        for i, line in enumerate(lines):
            if line.startswith('GLOBAL_EMAIL_ALERTS='):
                lines[i] = f'GLOBAL_EMAIL_ALERTS={enabled}\n'
                found = True
                break
        
        if not found:
            lines.append(f'GLOBAL_EMAIL_ALERTS={enabled}\n')
        
        # Write back to file
        with open(config_path, 'w') as f:
            f.writelines(lines)
        
        # Force reload environment variables
        load_dotenv(config_path, override=True)
        logger.info(f"Updated GLOBAL_EMAIL_ALERTS to {enabled}")
        return True
    except Exception as e:
        logger.error(f"Error updating global email alerts: {e}")
        return False

def get_global_email_alerts() -> bool:
    """Get the current global email alerts setting"""
    return os.getenv('GLOBAL_EMAIL_ALERTS', 'True').lower() in ('true', '1', 't')

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_USER_ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when the command /start is issued."""
    welcome_message = (
        "🤖 *Amazon Price Tracker Bot*\n\n"
        "I can help you track Amazon product prices and notify you when they drop below your target price.\n\n"
        "*Available commands:*\n"
        "`/add <url> <price> [tag]` - Add a product to track with an optional tag\n"
        "`/list` - List all tracked products\n"
        "`/remove <id>` - Remove a product\n"
        "`/alert_on <id>` - Enable email alerts for a product\n"
        "`/alert_off <id>` - Disable email alerts for a product\n"
        "`/help` - Show this help message\n\n"
        "*Examples:*\n"
        "• `/add https://amzn.in/d/example 5000 SSD`\n"
        "• `/add https://amzn.in/d/example 10000` (without tag)"
    )
    await update.message.reply_text(
        welcome_message,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    help_text = (
        "🤖 <b>Amazon Price Tracker Bot</b>\n\n"
        "<b>Available commands:</b>\n"
        "• /start - Start the bot\n"
        "• /help - Show this help message\n\n"
        "<b>Product Management:</b>\n"
        "• /add [url] [target_price] [tag] - Add a product to track\n"
        "• /remove [product_id] - Remove a product from tracking\n"
        "• /list - List all tracked products\n\n"
        "<b>Email Alerts (Global):</b>\n"
        "• /alertson - Enable all email alerts\n"
        "• /alertsoff - Disable all email alerts\n"
        "• /status - Show current status of global email alerts"
    )
    await update.message.reply_text(
        help_text,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a product to track."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Please provide a URL, target price, and optional tag.\n"
            "Example: `/add https://amzn.in/d/example 5000 SSD`\n"
            "Or: `/add https://www.amazon.in/dp/B0XXXXXX 10000 Laptop`",
            parse_mode='Markdown'
        )
        return

    try:
        url = context.args[0]
        try:
            target_price = float(context.args[1])
        except (IndexError, ValueError):
            await update.message.reply_text(
                "❌ Please provide a valid target price.\n"
                "Example: `/add https://amzn.in/d/example 5000 SSD`",
                parse_mode='Markdown'
            )
            return
            
        # Get tag if provided (all remaining arguments after price)
        tag = ' '.join(context.args[2:]) if len(context.args) > 2 else None
        
        # Basic URL validation and normalization
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Check if it's a valid Amazon or Flipkart URL
        import re
        amazon_pattern = r'(https?:\/\/)(www\.)?(amazon\.(com|in|co\.uk|de|fr|es|it|nl|pl|ae|sa|com\.br|com\.mx|com\.au|co\.jp|cn)|a\.co|amzn\.to|amzn\.in)'
        flipkart_pattern = r'(https?:\/\/)(www\.)?(flipkart\.com|dl\.flipkart\.com)'
        
        if not (re.match(amazon_pattern, url, re.IGNORECASE) or re.match(flipkart_pattern, url, re.IGNORECASE)):
            await update.message.reply_text(
                "❌ Please provide a valid Amazon or Flipkart product URL.\n"
                "Example Amazon: `/add https://amzn.in/d/example 5000 SSD`\n"
                "Example Flipkart: `/add https://www.flipkart.com/example 15000 Phone`",
                parse_mode='Markdown'
            )
            return
            
        # Set store type based on URL
        store_type = StoreType.FLIPKART if 'flipkart.com' in url.lower() else StoreType.AMAZON

        product = product_manager.add_product(url, target_price, tag, store_type=store_type)
        await update.message.reply_text(
            f"✅ *Product added!*\n\n"
            f"🔗 *URL:* {url}\n"
            f"🎯 *Target Price:* ₹{target_price:,.2f}\n"
            f"🆔 *ID:* `{product.id}`\n\n"
            f"I'll notify you when the price drops! 🚀",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    except ValueError:
        await update.message.reply_text("❌ Please provide a valid price number.")
    except Exception as e:
        logger.error(f"Error adding product: {e}")
        await update.message.reply_text("❌ An error occurred while adding the product.")

def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    if not text:
        return ""
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all tracked products."""
    products = product_manager.get_all_products()
    
    if not products:
        await update.message.reply_text("No products being tracked yet. Use /add to add a product.")
        return
    
    try:
        message_parts = ["<b>📋 Tracked Products</b>\n\n"]
        
        for product in products:
            # Get product details and escape them
            title = str(product.title or 'Not checked yet')
            url = str(product.url)
            
            # Always show current price if available
            price_info = ""
            if product.current_price is not None:
                price_emoji = "💰"
                if product.current_price <= product.target_price:
                    price_emoji = "🎯"  # Target price met or better
                price_info = f"{price_emoji} <b>Current Price:</b> <code>₹{float(product.current_price):,.2f}</code>\n"
            
            # Format target price
            formatted_price = f"₹{float(product.target_price):,.2f}"
            
            # Get tag if available
            tag_info = f"🏷️ <b>Tag:</b> <code>{escape_html(product.tag)}</code>\n" if product.tag else ""
            
            # Build message with HTML formatting
            message_parts.extend([
                f"🆔 <b>ID:</b> <code>{escape_html(str(product.id))}</code>\n",
                f"📦 <b>Title:</b> {escape_html(title)}\n" if title.strip() else "",
                f"🔗 <b>URL:</b> <a href='{escape_html(url)}'>{escape_html(url)}</a>\n",
                f"🎯 <b>Target Price:</b> <code>{escape_html(formatted_price)}</code>\n",
                tag_info,
                price_info,
                "--------------------------------\n"
            ])
        
        # Split message if too long (Telegram has a 4096 character limit)
        message = "".join(message_parts)
        if len(message) > 4000:
            chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
            for chunk in chunks:
                await update.message.reply_text(
                    chunk,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
        else:
            await update.message.reply_text(
                message,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            
    except Exception as e:
        logger.error(f"Error listing products: {e}")
        await update.message.reply_text(
            "❌ An error occurred while listing products. The message may contain invalid characters.",
            parse_mode='Markdown'
        )

async def remove_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a product from tracking."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ You don't have permission to remove products.")
        return

    if not context.args:
        await update.message.reply_text("❌ Please provide a product ID to remove. Use /list to see all products.")
        return

    try:
        product_id = context.args[0]
        product_manager.remove_product(product_id)
        await update.message.reply_text(f"✅ Product {product_id} has been removed from tracking.")
    except Exception as e:
        logger.error(f"Error removing product: {e}")
        await update.message.reply_text("❌ Failed to remove the product. Please check the ID and try again.")

async def global_alerts_on(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enable global email alerts."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    if update_global_email_alerts(True):
        await update.message.reply_text("✅ Global email alerts have been enabled.")
        logger.info(f"Global email alerts enabled by user {update.effective_user.id}")
    else:
        await update.message.reply_text("❌ Failed to enable global email alerts. Please check logs.")
        logger.error(f"Failed to enable global email alerts for user {update.effective_user.id}")

async def global_alerts_off(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Disable global email alerts."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    if update_global_email_alerts(False):
        await update.message.reply_text("❌ Global email alerts have been disabled.")
        logger.info(f"Global email alerts disabled by user {update.effective_user.id}")
    else:
        await update.message.reply_text("❌ Failed to disable global email alerts. Please check logs.")
        logger.error(f"Failed to disable global email alerts for user {update.effective_user.id}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the current status of global email alerts."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Force reload environment variables to get the latest value
    load_dotenv('config.env', override=True)
    current_status = get_global_email_alerts()
    logger.info(f"Current global email alerts status: {current_status}")
    
    status_text = "enabled ✅" if current_status else "disabled ❌"
    message = (
        "📊 <b>Global Email Alerts Status</b>\n\n"
        f"Status: {status_text}\n"
        f"Config file: {os.path.abspath('config.env')}\n\n"
        "<b>Commands:</b>\n"
        "/alertson - Enable all email alerts\n"
        "/alertsoff - Disable all email alerts\n"
        "/status - Show this status"
    )
    await update.message.reply_text(message, parse_mode='HTML')
    logger.info(f"Status sent to user {update.effective_user.id}")

def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main() -> None:
    """Start the bot."""
    # Load environment variables
    load_dotenv(dotenv_path="config.env")
    
    # Configure logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger = logging.getLogger(__name__)

    try:
        # Create the Application
        application = Application.builder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()

        # Add command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("add", add_product))
        application.add_handler(CommandHandler("remove", remove_product))
        application.add_handler(CommandHandler("list", list_products))
        application.add_handler(CommandHandler("alertson", global_alerts_on))
        application.add_handler(CommandHandler("alertsoff", global_alerts_off))
        application.add_handler(CommandHandler("status", status))
        
        # Log all errors
        application.add_error_handler(error_handler)

        # Start the bot
        logger.info("Starting bot...")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == '__main__':
    main()
