# from app import db, TrackedProduct, PriceHistory, send_mail
# from datetime import datetime
# from bs4 import BeautifulSoup
# import requests
# from sqlalchemy import func
# import os

# def clean_price(price_str):
#     import re
#     price_str = re.sub(r'[^\d.]', '', price_str)
#     if price_str.count('.') > 1:
#         parts = price_str.split('.')
#         price_str = parts[0] + '.' + ''.join(parts[1:])
#     return float(price_str)

# def fetch_current_price(product_url):
#     SCRAPERAPI_KEY = 'd147aa3553b782e49185ddea6c5f41ee'
#     headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
#     api_url = f'http://api.scraperapi.com/?api_key={SCRAPERAPI_KEY}&url={product_url}'
#     response = requests.get(api_url, headers=headers, timeout=30)
#     soup1 = BeautifulSoup(response.content, "html.parser")
#     soup2 = BeautifulSoup(soup1.prettify(), "html.parser")

#     # Identify platform
#     if "flipkart.com" in product_url:
#         try:
#             current_price = soup2.find('div', class_='Nx9bqj CxhGGd').get_text(strip=True).strip()[1:]
#             return float(current_price)
#         except:
#             return None
#     elif "amazon." in product_url:
#         try:
#             whole = soup2.find('span', class_='a-price-whole').get_text(strip=True)
#             fraction = soup2.find('span', class_='a-price-fraction').get_text(strip=True)
#             return clean_price(f"{whole}.{fraction}")
#         except:
#             return None
#     elif "nykaa.com" in product_url:
#         try:
#             current_price = soup2.find('span', class_='css-1jczs19').get_text(strip=True).strip()[1:]
#             return float(current_price)
#         except:
#             return None
#     elif "boat-lifestyle" in product_url:
#         try:
#             current_price = soup2.find('span', class_='mobile_atc_price').get_text(strip=True).strip()[1:]
#             return float(current_price)
#         except:
#             return None
#     else:
#         return None

# def update_prices_and_notify():
#     with db.session.begin():
#         products = TrackedProduct.query.all()
#         for product in products:
#             current_price = fetch_current_price(product.url)

#             if current_price is None:
#                 print(f"❌ Could not fetch price for {product.url}")
#                 continue

#             # Update current price in DB
#             product.current_price = current_price

#             # Add to Price History if today's entry doesn't exist
#             today = datetime.utcnow().date()
#             existing_entry = PriceHistory.query.filter(
#                 PriceHistory.product_id == product.id,
#                 func.date(PriceHistory.date) == today
#             ).first()

#             if not existing_entry:
#                 new_entry = PriceHistory(product_id=product.id, price=current_price)
#                 db.session.add(new_entry)

#             # Maintain only last 7 entries
#             history = PriceHistory.query.filter_by(product_id=product.id).order_by(PriceHistory.date).all()
#             while len(history) > 7:
#                 db.session.delete(history[0])
#                 history.pop(0)

#             # Send email if price drops
#             if product.target_price is not None and current_price <= product.target_price:
#                 send_mail(product.user.email, product.product_title, product.url, product.target_price)
#                 print(f"📧 Sent email to {product.user.email} for {product.product_title}")

#     db.session.commit()
#     print("✅ Price check completed.")

# if __name__ == "__main__":
#     update_prices_and_notify()


from app import app, db, TrackedProduct, PriceHistory, send_mail
from datetime import datetime
from bs4 import BeautifulSoup
import requests
from sqlalchemy import func
import os

def clean_price(price_str):
    import re
    price_str = re.sub(r'[^\d.]', '', price_str)
    if price_str.count('.') > 1:
        parts = price_str.split('.')
        price_str = parts[0] + '.' + ''.join(parts[1:])
    return float(price_str)

def fetch_current_price(product_url):
    SCRAPERAPI_KEY = 'd147aa3553b782e49185ddea6c5f41ee'
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    api_url = f'http://api.scraperapi.com/?api_key={SCRAPERAPI_KEY}&url={product_url}'
    response = requests.get(api_url, headers=headers, timeout=30)
    soup1 = BeautifulSoup(response.content, "html.parser")
    soup2 = BeautifulSoup(soup1.prettify(), "html.parser")

    # Identify platform
    if "flipkart.com" in product_url:
        try:
            current_price = soup2.find('div', class_='Nx9bqj CxhGGd').get_text(strip=True).strip()[1:]
            return float(current_price)
        except:
            return None
    elif "amazon." in product_url:
        try:
            whole = soup2.find('span', class_='a-price-whole').get_text(strip=True)
            fraction = soup2.find('span', class_='a-price-fraction').get_text(strip=True)
            return clean_price(f"{whole}.{fraction}")
        except:
            return None
    elif "nykaa.com" in product_url:
        try:
            current_price = soup2.find('span', class_='css-1jczs19').get_text(strip=True).strip()[1:]
            return float(current_price)
        except:
            return None
    elif "boat-lifestyle" in product_url:
        try:
            current_price = soup2.find('span', class_='mobile_atc_price').get_text(strip=True).strip()[1:]
            return float(current_price)
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

        # Update current price in DB
        product.current_price = current_price

        # Add to Price History if today's entry doesn't exist
        today = datetime.utcnow().date()
        existing_entry = PriceHistory.query.filter(
            PriceHistory.product_id == product.id,
            func.date(PriceHistory.date) == today
        ).first()

        if not existing_entry:
            new_entry = PriceHistory(product_id=product.id, price=current_price)
            db.session.add(new_entry)

        # Maintain only last 7 entries
        history = PriceHistory.query.filter_by(product_id=product.id).order_by(PriceHistory.date).all()
        while len(history) > 7:
            db.session.delete(history[0])
            history.pop(0)

        # Send email if price drops
        if product.target_price is not None and current_price <= product.target_price:
            send_mail(product.user.email, product.product_title, product.url, product.target_price)
            print(f"📧 Sent email to {product.user.email} for {product.product_title}")

    db.session.commit()
    print("✅ Price check completed.")

if __name__ == "__main__":
    with app.app_context():  # <-- WRAP IT HERE
        update_prices_and_notify()
