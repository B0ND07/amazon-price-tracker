# Import necessary libraries
import requests
from bs4 import BeautifulSoup
import lxml
import smtplib
import schedule
import time

# The URL of the Amazon India product page you want to monitor
URL = "https://amzn.in/d/crvlYpS"  # Replace with your product URL

# Headers to mimic a browser visit
headers = { 
    'Accept-Language': "en-IN,en;q=0.9",
    'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 Edg/107.0.1418.35"
}

# Set the threshold price for the alert (in INR)
BUY_PRICE = 28000  # Set your desired buy price

# SMTP configuration
YOUR_SMTP_ADDRESS = "smtp.gmail.com"
YOUR_EMAIL = "mhashimkp@gmail.com"
YOUR_PASSWORD = "upofcmqzrvfxlooi"

def check_price_and_coupon():
    print("Checking price and coupon availability...")

    # Send a request to the URL
    response = requests.get(URL, headers=headers)

    # Check if the request was successful
    if response.status_code != 200:
        print(f"Failed to retrieve the page. Status code: {response.status_code}")
        return

    # Parse the HTML content of the page
    soup = BeautifulSoup(response.content, "lxml")

    # Find the element that contains the price
    price_data = soup.find("span", class_="a-offscreen")

    # Check if the price element was found
    if not price_data:
        print("Price not found on the page.")
        return

    # Extract the price text and convert to a floating-point number
    price = price_data.text
    split_price = float(price.replace("₹", "").replace(",", "").strip())

    # Print the extracted price
    print(f"Current price: ₹{split_price}")

    # Find the product title and clean it
    title_element = soup.find(id="productTitle")
    if not title_element:
        print("Product title not found.")
        return

    title = title_element.get_text().strip()
    print(f"Product Title: {title}")

    # Check for coupon availability
    coupon_element = soup.find('span', text=lambda t: t and ('coupon' in t.lower()))
    coupon_available = False
    coupon_text = ""

    if coupon_element:
        coupon_available = True
        coupon_text = coupon_element.get_text().strip()
        print(f"Coupon Available: {coupon_text}")
    else:
        print("No coupon available.")

    # Check if the current price is less than the buy price or if a coupon is available
    if split_price < BUY_PRICE or coupon_available:
        # Create a message with the product title, price, and coupon information
        message = f"{title} is now {split_price}."
        if coupon_available:
            message += f" Coupon available: {coupon_text}"

        # Send an email alert
        try:
            with smtplib.SMTP(YOUR_SMTP_ADDRESS, port=587) as connection:
                connection.starttls()
                connection.login(YOUR_EMAIL, YOUR_PASSWORD)
                connection.sendmail(
                    from_addr=YOUR_EMAIL,
                    to_addrs=YOUR_EMAIL,
                    msg=f"Subject:Amazon India Price Alert!\n\n{message}\n{URL}"
                )
            print("Email sent successfully!")
        except Exception as e:
            print(f"Failed to send email: {e}")
    else:
        print(f"No alert sent. The price is still above ₹{BUY_PRICE} and no coupon is available.")

# Schedule the function to run every 5 minutes
schedule.every(1).minutes.do(check_price_and_coupon)

print("Scheduler started. Checking every 1 minutes...")

# Keep the script running
while True:
    schedule.run_pending()
    time.sleep(60)  # Check every minute for pending tasks
