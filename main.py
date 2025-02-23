import requests
from bs4 import BeautifulSoup
import lxml
import smtplib
import schedule
import time
from dataclasses import dataclass
from typing import List, Optional
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import random
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

@dataclass
class Product:
    url: str
    target_price: float
    title: Optional[str] = None
    current_price: Optional[float] = None
    coupon: Optional[str] = None

class AmazonPriceTracker:
    def __init__(self, email: str, password: str, smtp_address: str = "smtp.gmail.com"):
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
        self.products: List[Product] = []
        self.session = self._create_session()

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

    def add_product(self, url: str, target_price: float):
        """Add a product to track."""
        self.products.append(Product(url=url, target_price=target_price))
        print(f"➕ Added new product to track: {url}")

    def check_price_and_coupon(self, product: Product) -> bool:
        """Check price and coupon for a single product. Returns True if alert should be sent."""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                print(f"\n🔍 Checking product: {product.url}")
                
                # Add random delay between requests
                time.sleep(random.uniform(2, 5))
                
                # Use session with random headers
                headers = self._get_random_headers()
                response = self.session.get(product.url, headers=headers, timeout=10)
                
                if response.status_code != 200:
                    print(f"❌ Failed to retrieve page. Status code: {response.status_code}")
                    retry_count += 1
                    continue

                soup = BeautifulSoup(response.content, "lxml")

                # Get product title
                title_element = soup.find(id="productTitle")
                if title_element:
                    product.title = title_element.get_text().strip()
                    print(f"📦 Product: {product.title}")

                # Try multiple price selectors
                price_element = (
                    soup.find("span", class_="a-offscreen") or
                    soup.find("span", class_="a-price-whole") or
                    soup.find("span", class_="a-price") or
                    soup.find("span", id="priceblock_ourprice")
                )

                if price_element:
                    price_text = price_element.text
                    # Clean up price text
                    price_text = ''.join(filter(lambda x: x.isdigit() or x == '.', 
                                              price_text.replace(',', '')))
                    try:
                        product.current_price = float(price_text)
                        print(f"💰 Current Price: ₹{product.current_price:,.2f}")
                        print(f"🎯 Target Price: ₹{product.target_price:,.2f}")
                    except ValueError:
                        print(f"❌ Error converting price: {price_text}")
                        retry_count += 1
                        continue
                else:
                    print("❌ Price not found, trying alternate selectors...")
                    retry_count += 1
                    continue

                # Check for coupon
                coupon_element = (
                    soup.find('span', string=lambda t: t and ('coupon' in t.lower())) or
                    soup.find('span', class_=lambda x: x and 'coupon' in x.lower())
                )
                product.coupon = coupon_element.get_text().strip() if coupon_element else None
                print(f"🎫 Coupon: {'Available - ' + product.coupon if product.coupon else 'None'}")

                # Determine if alert should be sent
                should_alert = product.current_price < product.target_price or product.coupon is not None
                
                # Print alert status
                if should_alert:
                    print("🔔 Alert condition met!")
                else:
                    print("✓ Checked - No alert needed")
                
                return should_alert

            except requests.RequestException as e:
                print(f"❌ Network error: {e}")
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = retry_count * 5
                    print(f"⏳ Waiting {wait_time} seconds before retry {retry_count + 1}/{max_retries}")
                    time.sleep(wait_time)
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = retry_count * 5
                    print(f"⏳ Waiting {wait_time} seconds before retry {retry_count + 1}/{max_retries}")
                    time.sleep(wait_time)

        print(f"❌ Failed to check product after {max_retries} attempts")
        return False

    def send_email_alert(self, products_to_alert: List[Product]):
        """Send email alert for multiple products."""
        try:
            print("\n📧 Sending email alert...")
            
            msg = MIMEMultipart()
            msg['From'] = self.email
            msg['To'] = self.email
            msg['Subject'] = "Amazon India Price Alert!"

            body = "The following products have met your alert criteria:\n\n"
            for product in products_to_alert:
                body += f"Product: {product.title}\n"
                body += f"Current Price: ₹{product.current_price:,.2f}\n"
                body += f"Target Price: ₹{product.target_price:,.2f}\n"
                if product.coupon:
                    body += f"Coupon Available: {product.coupon}\n"
                body += f"URL: {product.url}\n\n"

            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP(self.smtp_address, port=587) as connection:
                connection.starttls()
                connection.login(self.email, self.password)
                connection.send_message(msg)
            print("✅ Email alert sent successfully!")
        except Exception as e:
            print(f"❌ Failed to send email: {e}")

    def check_all_products(self):
        """Check all products and send alerts if necessary."""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n⏰ Starting price check at {current_time}")
        print("=" * 50)
        
        products_to_alert = []
        for product in self.products:
            if self.check_price_and_coupon(product):
                products_to_alert.append(product)
        
        if products_to_alert:
            self.send_email_alert(products_to_alert)
        
        print("=" * 50)
        print(f"✅ Completed checking {len(self.products)} products")

def main():
    # Initialize the tracker
    tracker = AmazonPriceTracker(
        email="mhashimkp@gmail.com",
        password="upofcmqzrvfxlooi"
    )

    # Add products to track
    tracker.add_product("https://amzn.in/d/ilw23qE", 28000)
    tracker.add_product("https://amzn.in/d/hSFfDhy", 28000)
    tracker.add_product("https://amzn.in/d/4nQrGkk", 26000)

    # Schedule checks with random interval between 2-3 minutes
    schedule.every(10).to(15).minutes.do(tracker.check_all_products)
    print("\n🚀 Price tracker started")
    print("⏱️ Checking every 10 minutes...")
    print("Press Ctrl+C to stop the tracker")

    # Run first check immediately
    tracker.check_all_products()

    # Keep the script running
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()