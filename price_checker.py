from app import app, db, TrackedProduct, PriceHistory, send_mail
from datetime import datetime
from bs4 import BeautifulSoup
import requests
from sqlalchemy import func
import os
import re
import json
from dotenv import load_dotenv

load_dotenv()

def clean_price(price_str):
    price_str = re.sub(r'[^\d.]', '', price_str)
    if price_str.count('.') > 1:
        parts = price_str.split('.')
        price_str = parts[0] + '.' + ''.join(parts[1:])
    return float(price_str)

def fetch_current_price(product_url):
    GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

    # Myntra: returns full HTML with JSON-LD to Chrome UA — no proxy needed
    if "myntra.com" in product_url:
        try:
            myntra_headers = {
                "User-Agent": CHROME_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/",
            }
            resp = requests.get(product_url, headers=myntra_headers, timeout=20, allow_redirects=True)
            if resp.status_code != 200:
                print(f"[Myntra] HTTP {resp.status_code}")
                return None
            soup2 = BeautifulSoup(resp.content, "html.parser")
        except Exception as e:
            print(f"[Myntra] Request failed: {e}")
            return None
    elif "flipkart.com" in product_url:
        try:
            bot_resp = requests.get(product_url, headers={"User-Agent": GOOGLEBOT_UA}, timeout=30, allow_redirects=True)
            soup2 = BeautifulSoup(bot_resp.content, "html.parser")
        except Exception as e:
            print(f"[Flipkart] Request failed: {e}")
            return None
    else:
        try:
            headers = {"User-Agent": CHROME_UA}
            fallback_resp = requests.get(product_url, headers=headers, timeout=30, allow_redirects=True)
            soup2 = BeautifulSoup(fallback_resp.content, "html.parser")
        except Exception as e:
            print(f"[Fallback] Request failed: {e}")
            return None

    if "flipkart.com" in product_url:
        try:
            prices = []
            for el in soup2.find_all(string=re.compile(r'\u20B9')):
                text = el.strip().replace('\u20B9', '').strip()
                if text and len(text) < 12:
                    try:
                        prices.append(clean_price(text))
                    except Exception:
                        pass
            return float(prices[0]) if prices else None
        except:
            return None
    elif "amazon." in product_url or "amzn." in product_url:
        try:
            price_whole = soup2.find('span', class_='a-price-whole')
            if price_whole:
                whole = price_whole.get_text(strip=True).replace('.', '')
                fraction_tag = soup2.find('span', class_='a-price-fraction')
                fraction = fraction_tag.get_text(strip=True) if fraction_tag else "00"
                return clean_price(f"{whole}.{fraction}")
            return None
        except:
            return None
    elif "myntra.com" in product_url:
        try:
            # Strategy 1: JSON-LD Product schema
            for ld_tag in soup2.find_all('script', type='application/ld+json'):
                try:
                    ld = json.loads(ld_tag.string or '')
                    items = ld if isinstance(ld, list) else [ld]
                    for item in items:
                        if item.get('@type') == 'Product':
                            offers = item.get('offers', {})
                            if isinstance(offers, list):
                                offers = offers[0]
                            price_val = offers.get('price', '') if offers else ''
                            if price_val:
                                return clean_price(str(price_val))
                except Exception:
                    pass
            return None
        except:
            return None
    elif "boat-lifestyle" in product_url:
        try:
            price_tag = soup2.find('span', class_='mobile_atc_price')
            current_price = price_tag.get_text(strip=True).strip()[1:] if price_tag else None
            return float(current_price) if current_price else None
        except:
            return None
    else:
        return None

def update_prices_and_notify():
    products = TrackedProduct.query.all()
    for product in products:
        current_price = fetch_current_price(product.url)

        if current_price is None:
            print(f"❌ Could not fetch price for {product.url}")
            continue

        product.current_price = current_price

        today = datetime.utcnow().date()
        existing_entry = PriceHistory.query.filter(
            PriceHistory.product_id == product.id,
            func.date(PriceHistory.date) == today
        ).first()

        if not existing_entry:
            new_entry = PriceHistory(product_id=product.id, price=current_price)
            db.session.add(new_entry)

        history = PriceHistory.query.filter_by(product_id=product.id).order_by(PriceHistory.date).all()
        while len(history) > 7:
            db.session.delete(history[0])
            history.pop(0)

        if product.target_price is not None and current_price <= product.target_price:
            send_mail(product.user.email, product.product_title, product.url, product.target_price)
            print(f"📧 Sent email to {product.user.email} for {product.product_title}")

    db.session.commit()
    print("✅ Price check completed.")

if __name__ == "__main__":
    with app.app_context():
        update_prices_and_notify()
