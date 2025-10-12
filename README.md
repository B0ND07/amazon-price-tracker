# 📦 Amazon India Price Tracker

Track Amazon product prices and receive alerts when:
- Price drops below your target 🎯
- (Optional) Coupon discounts are available 🎫

**Note: This tracker now supports Amazon only. Flipkart support has been disabled.**

---

## 🚀 Features
- ✅ Track multiple Amazon products easily
- ✅ Email and Telegram alerts when price drops or coupons are available
- ✅ Auto retries on network failures
- ✅ Configurable through `config.env` file
- ✅ Random headers and delays to avoid getting blocked
- ✅ Coupon checking can be turned ON/OFF
- ✅ Lightweight Docker setup (no Chrome/Selenium needed)

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
pip install requests beautifulsoup4 lxml schedule python-dotenv python-telegram-bot psutil
```

### 3. Create a `.env` File

Create a `config.env` file in the root folder:

```env
# Email Configuration
SMTP_EMAIL=your_email@example.com
SMTP_PASSWORD=your_email_app_password
COUPON_ALERT=True
GLOBAL_EMAIL_ALERTS=True

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
ADMIN_USER_ID=your_telegram_user_id
```

**Note: Products are now managed through the Telegram bot interface. No need to configure URLs in the config file.**

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

## Docker

### Using Docker Compose (Recommended)
```bash
docker-compose up -d
```

### Using Docker directly
```bash
docker build -t amazon-price-tracker .
docker run -d --name amazon-tracker \
  -v ./data-persistent:/data \
  -v ./config.env:/usr/src/app/config.env:ro \
  amazon-price-tracker
```

**Note: The Docker setup is now optimized for Amazon-only tracking (no Chrome/Selenium dependencies).**

## 🧹 Project Structure

```
.
├── main.py                 # Main application entry point
├── telegram_bot.py         # Telegram bot interface
├── product_manager.py      # Product data management
├── tracker_manager.py      # Price tracking coordination
├── trackers/
│   ├── amazon_tracker.py   # Amazon-specific price tracking
│   └── base.py            # Base tracker class
├── config.env             # Configuration file
├── docker-compose.yml     # Docker Compose configuration
├── Dockerfile            # Docker image definition
├── requirements.txt      # Python dependencies
└── README.md            # This file
```

---

## 🛡️ Disclaimer

- This project is for **personal use only**.
- **Not affiliated with Amazon** in any way.
- Use responsibly to avoid being blocked by Amazon.

---

## 🧠 Future Improvements

- [x] Add Telegram alerts ✅
- [ ] Save price history to a local database
- [ ] Create a simple web dashboard for monitoring
- [ ] Add support for other e-commerce platforms

---

## ✨ Author

Made with ❤️ by B0ND07
