# 📦 Amazon India Price Tracker

Track Amazon product prices and receive email alerts when:
- Price drops below your target 🎯
- (Optional) Coupon discounts are available 🎫

---

## 🚀 Features
- ✅ Track multiple products easily
- ✅ Email alerts when price drops or coupons are available
- ✅ Auto retries on network failures
- ✅ Configurable through `.env` file
- ✅ Random headers and delays to avoid getting blocked
- ✅ Coupon checking can be turned ON/OFF

---

## 🛠️ Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/b0nd07/amazon-price-tracker.git
cd amazon-price-tracker
```

### 2. Install Required Packages

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install requests beautifulsoup4 lxml schedule python-dotenv
```

### 3. Create a `.env` File

Create a `config.env` file in the root folder:

```env
# Email Credentials
SMTP_EMAIL=your_email@example.com
SMTP_PASSWORD=your_email_app_password

# Products to Track
PRODUCT_1_URL=https://amzn.in/d/ilw23qE
PRODUCT_1_TARGET_PRICE=28000

PRODUCT_2_URL=https://amzn.in/d/hSFfDhy
PRODUCT_2_TARGET_PRICE=28000

PRODUCT_3_URL=https://amzn.in/d/4nQrGkk
PRODUCT_3_TARGET_PRICE=26000

# Enable or Disable Coupon Checking
COUPON_ALERT=True
```

✅ *Tip: Use an **App Password** for Gmail accounts.*

---

## ⚙️ How to Run

```bash
python main.py
```

- First price check will happen immediately
- Then every 10–15 minutes randomly
- Stop the tracker anytime with `Ctrl + C`

---

## 🧹 Project Structure

```
.
├── amazon_price_tracker.py
├── config.env
├── README.md
└── requirements.txt
```

---

## 🛡️ Disclaimer

- This project is for **personal use only**.
- **Not affiliated with Amazon** in any way.
- Use responsibly to avoid being blocked by Amazon.

---

## 🧠 Future Improvements

- [ ] Add Telegram or WhatsApp alerts
- [ ] Save price history to a local database
- [ ] Create a simple web dashboard for monitoring

---

## ✨ Author

Made with ❤️ by B0ND07
