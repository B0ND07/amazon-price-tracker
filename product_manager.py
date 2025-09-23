"""
Unified Product Manager for Amazon Price Tracker

This module provides a centralized ProductManager class to prevent
synchronization issues between the Telegram bot and price tracker.
"""

import json
import os
import logging
import time
import uuid
from typing import Dict, List, Optional
from dataclasses import asdict
from pathlib import Path

from enum import Enum
from dataclasses import dataclass

class StoreType(Enum):
    AMAZON = 'amazon'
    FLIPKART = 'flipkart'

@dataclass
class Product:
    url: str
    target_price: float
    title: Optional[str] = None
    current_price: Optional[float] = None
    coupon: Optional[str] = None  # Kept for backward compatibility
    coupon_info: Optional[Dict] = None  # New field for detailed coupon information
    final_price: Optional[float] = None  # Price after applying coupon
    in_stock: Optional[bool] = None  # Stock availability
    id: Optional[str] = None
    tag: Optional[str] = None
    store_type: StoreType = StoreType.AMAZON  # Default to Amazon for backward compatibility
    last_updated: Optional[str] = None  # Timestamp of last update
    
    def to_dict(self) -> dict:
        """Convert Product to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert StoreType enum to its value for JSON serialization
        if 'store_type' in data and data['store_type'] is not None:
            data['store_type'] = data['store_type'].value
        return data

logger = logging.getLogger(__name__)

class ProductManager:
    """Unified product manager for handling product data storage and retrieval."""
    
    def __init__(self, filename: str = None):
        """Initialize the product manager.
        
        Args:
            filename: Path to the products JSON file. If None, uses default location.
        """
        if filename is None:
            # Use persistent data directory if available (for Docker), otherwise use local data directory
            data_dir = os.getenv('DATA_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
            filename = os.path.join(data_dir, 'products.json')
        
        self.filename = filename
        self.products: Dict[str, Product] = {}
        self._load_products()
    
    def _product_to_dict(self, product: Product) -> dict:
        """Convert a Product to a dictionary, handling enums properly."""
        if hasattr(product, 'to_dict'):
            return product.to_dict()
        
        data = asdict(product)
        # Convert StoreType enum to its value for JSON serialization
        if 'store_type' in data and data['store_type'] is not None:
            if hasattr(data['store_type'], 'value'):
                data['store_type'] = data['store_type'].value
        return data
    
    def _dict_to_product(self, data: dict) -> Product:
        """Convert a dictionary to a Product, handling enums properly."""
        # Make a copy to avoid modifying the original data
        data = data.copy()
        
        # Convert store_type string back to StoreType enum
        if 'store_type' in data and isinstance(data['store_type'], str):
            try:
                data['store_type'] = StoreType(data['store_type'])
            except ValueError:
                logger.warning(f"Invalid store_type '{data['store_type']}', defaulting to AMAZON")
                data['store_type'] = StoreType.AMAZON
        elif 'store_type' not in data:
            data['store_type'] = StoreType.AMAZON
        
        # Handle legacy coupon data format
        if 'coupon' in data and isinstance(data['coupon'], dict):
            # Old format where coupon was a dict, move to coupon_info
            if 'coupon_info' not in data or data['coupon_info'] is None:
                data['coupon_info'] = data['coupon']
            data['coupon'] = None  # Clear old field
        
        # Remove any unknown fields that might cause issues
        from dataclasses import fields
        valid_fields = {field.name for field in fields(Product)}
        cleaned_data = {k: v for k, v in data.items() if k in valid_fields}
        
        return Product(**cleaned_data)
    
    def _load_products(self):
        """Load products from the JSON file."""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.products = {
                        pid: self._dict_to_product(product_data)
                        for pid, product_data in data.items()
                    }
                logger.info(f"Loaded {len(self.products)} products from {self.filename}")
                
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
                logger.error(f"Error loading products from {self.filename}: {e}")
                self.products = {}
        else:
            # Initialize empty products dictionary if no file exists
            self.products = {}
            logger.info("No products.json found, starting with empty product list")
    
    def _save_products(self):
        """Save products to the JSON file with atomic write."""
        try:
            # Ensure the data directory exists
            os.makedirs(os.path.dirname(os.path.abspath(self.filename)), exist_ok=True)
            
            # Prepare data for JSON serialization
            data_to_save = {
                pid: self._product_to_dict(product)
                for pid, product in self.products.items()
            }
            
            # Write to a temporary file first (atomic write)
            temp_file = f"{self.filename}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)
            
            # Atomic rename to ensure data integrity
            if os.path.exists(self.filename):
                os.replace(temp_file, self.filename)
            else:
                os.rename(temp_file, self.filename)
            
            logger.info(f"Saved {len(self.products)} products to {self.filename}")
                
        except Exception as e:
            logger.error(f"Error saving products to {self.filename}: {e}")
            # Clean up temp file if it exists
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as cleanup_error:
                    logger.error(f"Failed to clean up temp file: {cleanup_error}")
            raise
    
    def add_product(self, url: str, target_price: float, tag: Optional[str] = None, 
                   store_type: StoreType = StoreType.AMAZON, **kwargs) -> Product:
        """Add a new product to track.
        
        Args:
            url: Product URL
            target_price: Target price for alerts
            tag: Optional tag for the product
            store_type: Store type (AMAZON or FLIPKART)
            **kwargs: Additional product attributes
            
        Returns:
            Product: The created product
        """
        product_id = str(uuid.uuid4())
        from datetime import datetime
        
        product = Product(
            id=product_id,
            url=url,
            target_price=target_price,
            tag=tag,
            store_type=store_type,
            title=kwargs.get('title'),
            current_price=kwargs.get('current_price'),
            coupon=kwargs.get('coupon'),
            coupon_info=kwargs.get('coupon_info'),
            final_price=kwargs.get('final_price'),
            in_stock=kwargs.get('in_stock'),
            last_updated=datetime.now().isoformat()
        )
        
        self.products[product_id] = product
        self._save_products()
        logger.info(f"Added product {product_id}: {url} (target: ₹{target_price})")
        return product
    
    def remove_product(self, product_id: str) -> bool:
        """Remove a product from tracking.
        
        Args:
            product_id: ID of the product to remove
            
        Returns:
            bool: True if product was removed, False if not found
        """
        if product_id in self.products:
            product = self.products[product_id]
            del self.products[product_id]
            self._save_products()
            logger.info(f"Removed product {product_id}: {getattr(product, 'title', 'Unknown')}")
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
            logger.debug(f"Updating product {product_id} with data: {kwargs}")
            
            # Update product attributes
            for key, value in kwargs.items():
                if value is not None:  # Don't update with None values
                    setattr(product, key, value)
            
            # Update last_updated timestamp
            from datetime import datetime
            setattr(product, 'last_updated', datetime.now().isoformat())
            
            try:
                self._save_products()
                logger.debug("Product updated successfully")
                return True
            except Exception as e:
                logger.error(f"Error saving product updates: {e}")
                return False
        
        logger.error(f"Product {product_id} not found")
        return False
    
    def reload(self):
        """Reload products from file to get latest data."""
        self._load_products()
    
    def get_product_count(self) -> int:
        """Get the number of tracked products."""
        return len(self.products)

# Global instance for shared use
_product_manager_instance = None

def get_product_manager() -> ProductManager:
    """Get the global ProductManager instance."""
    global _product_manager_instance
    if _product_manager_instance is None:
        _product_manager_instance = ProductManager()
    return _product_manager_instance
