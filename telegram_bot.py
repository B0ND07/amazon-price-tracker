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
# Use persistent data directory if available (for Docker), otherwise use local data directory
DATA_DIR = os.getenv('DATA_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
PRODUCTS_FILE = os.path.join(DATA_DIR, 'products.json')
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', 0))

# Product and StoreType classes are now imported from product_manager.py

# ProductManager class moved to product_manager.py for unified management

# Import unified product manager and classes
from product_manager import get_product_manager, Product, StoreType

# Initialize product manager
product_manager = get_product_manager()

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
        "• /help - Show this help message\n"
        "• /restart - Restart the bot (Admin only)\n\n"
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
        
        # Check if it's a valid Amazon URL (Flipkart disabled)
        import re
        amazon_pattern = r'(https?:\/\/)(www\.)?(amazon\.(com|in|co\.uk|de|fr|es|it|nl|pl|ae|sa|com\.br|com\.mx|com\.au|co\.jp|cn)|a\.co|amzn\.to|amzn\.in)'
        # flipkart_pattern = r'(https?:\/\/)(www\.)?(flipkart\.com|dl\.flipkart\.com)'  # Disabled
        
        if not re.match(amazon_pattern, url, re.IGNORECASE):
            await update.message.reply_text(
                "❌ Please provide a valid Amazon product URL.\n"
                "Example: `/add https://amzn.in/d/example 5000 SSD`\n"
                "Note: Flipkart support is currently disabled.",
                parse_mode='Markdown'
            )
            return
            
        # Set store type to Amazon only (Flipkart disabled)
        store_type = StoreType.AMAZON

        product = product_manager.add_product(url, target_price, tag, store_type=store_type)
        await update.message.reply_text(
            f"✅ *Product added!*\n\n"
            f"🔗 *URL:* {url}\n"
            f"🎯 *Target Price:* ₹{target_price:,.2f}\n"
            f"🆔 *ID:* `{product.id}`\n\n"
            f"I'll notify you when the price drops! Restarting to apply changes... 🚀",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        # Trigger a restart to pick up the new product immediately
        logger.info("Triggering restart after adding new product")
        try:
            with open('.restart', 'w') as f:
                f.write(str(time.time()))
            logger.info("Restart file created, waiting for process manager to restart")
        except Exception as e:
            logger.error(f"Failed to create restart file: {e}")
            await update.message.reply_text("⚠️ Added product but failed to trigger restart. Please restart manually.")
        
        # Stop the application to trigger the restart
        context.application.stop_running()
    except ValueError:
        await update.message.reply_text("❌ Please provide a valid price number.")
    except Exception as e:
        logger.error(f"Error adding product: {e}")
        await update.message.reply_text("❌ An error occurred while adding the product.")

def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    if not text:
        return ""
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#x27;')

def validate_html_tags(html: str) -> bool:
    """Validate that HTML tags are properly balanced."""
    try:
        # Count opening and closing tags
        tag_pairs = [
            ('<code>', '</code>'),
            ('<b>', '</b>'),
            ('<i>', '</i>'),
            ('<a', '</a>')
        ]
        
        for open_tag, close_tag in tag_pairs:
            if open_tag == '<a':
                # Special handling for <a> tags
                open_count = html.count('<a ')
                close_count = html.count('</a>')
            else:
                open_count = html.count(open_tag)
                close_count = html.count(close_tag)
                
            if open_count != close_count:
                logger.warning(f"HTML validation failed: {open_tag} count ({open_count}) != {close_tag} count ({close_count})")
                return False
        
        return True
    except Exception as e:
        logger.error(f"Error validating HTML: {e}")
        return False

async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all tracked products."""
    # Reload products from file to ensure we have the latest data
    product_manager.reload()
    products = product_manager.get_all_products()
    
    if not products:
        await update.message.reply_text("No products being tracked yet. Use /add to add a product.")
        return
    
    try:
        message_parts = ["<b>📋 Tracked Products</b>\n\n"]
        
        for product in products:
            try:
                # Get product details and escape them safely
                title = str(product.title or 'Not checked yet')
                url = str(product.url)
                
                # Validate URL format
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url
                
                # Always show current price if available
                price_info = ""
                if product.current_price is not None:
                    price_emoji = "💰"
                    if product.current_price <= product.target_price:
                        price_emoji = "🎯"  # Target price met or better
                    current_price_formatted = f"₹{float(product.current_price):,.2f}"
                    price_info = f"{price_emoji} <b>Current Price:</b> <code>{escape_html(current_price_formatted)}</code>\n"
                
                # Show stock availability (only when out of stock)
                stock_info = ""
                if hasattr(product, 'in_stock') and product.in_stock is not None:
                    if not product.in_stock:  # Only show when out of stock
                        stock_info = "📦 <b>Stock:</b> <code>❌ Out of Stock</code>\n"
                
                # Show coupon information
                coupon_info = ""
                if hasattr(product, 'coupon_info') and product.coupon_info and isinstance(product.coupon_info, dict):
                    coupon_data = product.coupon_info
                    if coupon_data.get('available'):
                        coupon_value = coupon_data.get('value', 0)
                        coupon_desc = coupon_data.get('description', f'₹{coupon_value} coupon')
                        # Ensure coupon description is properly formatted
                        safe_coupon_desc = str(coupon_desc).strip() if coupon_desc else f'₹{coupon_value} coupon'
                        coupon_info = f"🎫 <b>Coupon:</b> <code>{escape_html(safe_coupon_desc)}</code>\n"
                        
                        # Show final price if available
                        if hasattr(product, 'final_price') and product.final_price is not None:
                            final_price_formatted = f"₹{float(product.final_price):,.2f}"
                            final_price_info = f"💵 <b>Final Price:</b> <code>{escape_html(final_price_formatted)}</code> <i>(after coupon)</i>\n"
                            coupon_info += final_price_info
                
                # Format target price
                formatted_price = f"₹{float(product.target_price):,.2f}"
                
                # Get tag if available
                tag_info = f"🏷️ <b>Tag:</b> <code>{escape_html(str(product.tag))}</code>\n" if product.tag else ""
                
                # Build message with HTML formatting
                message_parts.extend([
                    f"🆔 <b>ID:</b> <code>{escape_html(str(product.id))}</code>\n",
                    f"📦 <b>Title:</b> {escape_html(str(title))}\n" if title.strip() else "",
                    f"🔗 <b>URL:</b> <a href='{url}'>{escape_html(url[:50])}{'...' if len(url) > 50 else ''}</a>\n",
                    f"🎯 <b>Target Price:</b> <code>{escape_html(formatted_price)}</code>\n",
                    tag_info,
                    price_info,
                    stock_info,
                    coupon_info,
                    "--------------------------------\n"
                ])
            
            except Exception as e:
                logger.error(f"Error processing product {getattr(product, 'id', 'unknown')}: {e}")
                # Add a simple error entry for this product
                message_parts.extend([
                    f"🆔 <b>ID:</b> <code>{escape_html(str(getattr(product, 'id', 'unknown')))}</code>\n",
                    f"❌ <b>Error:</b> Failed to display product details\n",
                    "--------------------------------\n"
                ])
        
        # Split message if too long (Telegram has a 4096 character limit)
        message = "".join(message_parts)
        
        # Validate HTML before sending
        if not validate_html_tags(message):
            logger.error("HTML validation failed, sending fallback message")
            fallback_message = "<b>📋 Tracked Products</b>\n\nError displaying product list with formatting. Please check logs for details."
            await update.message.reply_text(fallback_message, parse_mode='HTML')
            return
        
        if len(message) > 4000:
            chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
            for i, chunk in enumerate(chunks):
                # Validate each chunk
                if not validate_html_tags(chunk):
                    logger.error(f"HTML validation failed for chunk {i+1}, sending plain text")
                    chunk_plain = chunk.replace('<b>', '').replace('</b>', '').replace('<code>', '').replace('</code>', '').replace('<i>', '').replace('</i>', '')
                    # Remove <a> tags but keep the text
                    import re
                    chunk_plain = re.sub(r'<a[^>]*>([^<]*)</a>', r'\1', chunk_plain)
                    await update.message.reply_text(chunk_plain, disable_web_page_preview=True)
                else:
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
        success = product_manager.remove_product(product_id)
        if success:
            await update.message.reply_text(
                f"✅ Product {product_id} has been removed from tracking.\n"
                f"Restarting to apply changes... 🚀"
            )
            
            # Trigger a restart to apply the removal immediately
            logger.info("Triggering restart after removing product")
            try:
                import time
                with open('.restart', 'w') as f:
                    f.write(str(time.time()))
                logger.info("Restart file created, waiting for process manager to restart")
            except Exception as e:
                logger.error(f"Failed to create restart file: {e}")
                await update.message.reply_text("⚠️ Removed product but failed to trigger restart. Please restart manually.")
            
            # Stop the application to trigger the restart
            context.application.stop_running()
        else:
            await update.message.reply_text(f"❌ Product {product_id} not found. Please check the ID and try again.")
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

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Restart the bot (Admin only)."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ This command is restricted to administrators only.")
        return
    
    await update.message.reply_text("🔄 Restarting the bot...")
    logger.info("Restart requested by admin")
    
    # Signal the main process to restart by creating a restart file
    try:
        with open('.restart', 'w') as f:
            f.write(str(time.time()))
        logger.info("Restart file created, waiting for process manager to restart")
    except Exception as e:
        logger.error(f"Failed to create restart file: {e}")
        await update.message.reply_text("❌ Failed to initiate restart. Please check logs.")
        return
    
    # Stop the application
    context.application.stop_running()

def main() -> None:
    """Start the bot with enhanced connection settings and error handling."""
    # Load environment variables
    load_dotenv(dotenv_path="config.env")
    
    # Configure logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger = logging.getLogger(__name__)

    # Get bot token
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        logger.error("No TELEGRAM_BOT_TOKEN found in environment variables")
        return

    max_retries = 3
    retry_delay = 5  # seconds
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1}/{max_retries} to start the bot...")
            
            # Create the Application with connection pool settings
            application = (
                Application.builder()
                .token(bot_token)
                .connect_timeout(30.0)  # 30 seconds connection timeout
                .pool_timeout(30.0)     # 30 seconds pool timeout
                .read_timeout(30.0)     # 30 seconds read timeout
                .write_timeout(30.0)    # 30 seconds write timeout
                .get_updates_connect_timeout(30.0)  # 30 seconds for getUpdates connection
                .get_updates_pool_timeout(30.0)     # 30 seconds for getUpdates pool
                .get_updates_read_timeout(30.0)     # 30 seconds for getUpdates read
                .build()
            )

            # Add command handlers
            application.add_handler(CommandHandler("start", start))
            application.add_handler(CommandHandler("help", help_command))
            application.add_handler(CommandHandler("add", add_product))
            application.add_handler(CommandHandler("remove", remove_product))
            application.add_handler(CommandHandler("list", list_products))
            application.add_handler(CommandHandler("alertson", global_alerts_on))
            application.add_handler(CommandHandler("alertsoff", global_alerts_off))
            application.add_handler(CommandHandler("status", status))
            application.add_handler(CommandHandler("restart", restart))
            
            # Log all errors
            application.add_error_handler(error_handler)

            # Start the bot with polling
            logger.info("Starting bot with polling...")
            application.run_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,
                close_loop=False,
                pool_timeout=30.0,
                read_timeout=30.0,
                write_timeout=30.0
                # Removed connection_pool_size which is not supported in this version
            )
            break  # If we get here, the bot has stopped gracefully
            
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:  # Last attempt
                logger.error("Max retries reached. Could not start the bot.")
                raise
                
            # Wait before retrying
            logger.info(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
            
            # Increase delay for next retry (exponential backoff)
            retry_delay *= 2

if __name__ == '__main__':
    main()
