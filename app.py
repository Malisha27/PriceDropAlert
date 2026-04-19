from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from threading import Thread
from bs4 import BeautifulSoup
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
import os
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_apscheduler import APScheduler

load_dotenv()

app = Flask(__name__)
app.config['SCHEDULER_API_ENABLED'] = True

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

csrf = CSRFProtect(app)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'signIn'  # Redirects to this page if @login_required is used


app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_for_dev_ONLY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(app)

def clean_price(price_str):
    # Removes everything except digits and single decimal point
    price_str = re.sub(r'[^\d.]', '', price_str)
    # Fix accidental double dots
    if price_str.count('.') > 1:
        parts = price_str.split('.')
        price_str = parts[0] + '.' + ''.join(parts[1:])
    return float(price_str)



class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    # Relationship to tracked products
    products = db.relationship('TrackedProduct', backref='user', lazy=True)

class TrackedProduct(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    product_title = db.Column(db.String(500), nullable=True)
    target_price = db.Column(db.Float, nullable=True)
    current_price = db.Column(db.Float, nullable=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    price_history = db.relationship('PriceHistory', backref='product', lazy=True)

class PriceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('tracked_product.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def send_mail(to_email, product_title, product_url, target_price):
    try:
        sender_email = 'pricedropppp@gmail.com'
        sender_password = os.environ.get('EMAIL_PASSWORD')  # ⚠️ Uses environment variable

        # Set up the MIME
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = to_email
        message["Subject"] = f"{product_title} is now below ₹{target_price}!"

        body = f"Don't miss it! Link here: {product_url}"
        message.attach(MIMEText(body, "plain", "utf-8"))  # 👈 Ensures utf-8 encoding

        # Connect and send
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, message.as_string())
        server.quit()

        print("✅ Email sent successfully!")

    except Exception as e:
        print(f"❌ Error sending email: {e}")


@app.route('/')
def design():
    return render_template('design.html')

@app.route('/signIn', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def signIn():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password.', 'error')
            return redirect(url_for('signIn'))

    return render_template('signIn.html')

@app.route('/signUp', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def signUp():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Server-side checks
        if not name or not email or not password or not confirm_password:
            flash('All fields are required.', 'error')
            return redirect(url_for('signUp'))

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('signUp'))

        if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$', password):
            flash('Password must be at least 8 characters long and contain at least one uppercase letter, one lowercase letter, one digit, and one special character.', 'error')
            return redirect(url_for('signUp'))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered.', 'error')
            return redirect(url_for('signIn'))

        hashed_password = generate_password_hash(password)
        new_user = User(name=name, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Email has been registered, please try to login.', 'success')
        return redirect(url_for('signIn'))

    return render_template('signUp.html')

@app.route('/home', methods=['GET', 'POST'])
@login_required
def home():
    if request.method == 'POST':
        product_url = request.form['product_url'].strip()

        if not product_url:
            flash("Please enter a product URL.", "error")
            return redirect(url_for('home'))
        
        allowed_domains = ['amazon.', 'amzn.', 'flipkart.com', 'myntra.com', 'boat-lifestyle']
        if not any(domain in product_url for domain in allowed_domains):
            flash("Unsupported URL. Please enter a valid product URL from supported domains.", "error")
            return redirect(url_for('home'))
        
        # 🔍 Check if the same product already exists for this user
        existing_product = TrackedProduct.query.filter_by(url=product_url, user_id=current_user.id).first()

        if existing_product:
            flash("Product already exists. Redirecting to your watchlist.", "success")
            return redirect(url_for('watchlist', highlight=existing_product.id))

        # ✅ If not found, create a new product entry
        # Create a new product entry with just URL for now
        new_product = TrackedProduct(
            url=product_url,
            user_id=current_user.id
        )
        db.session.add(new_product)
        db.session.commit()
        flash("Product URL saved successfully.", "success")
        return redirect(url_for('track_product', product_id=new_product.id))

    return render_template('home.html')


@app.route('/track/<int:product_id>', methods=['GET', 'POST'])
@login_required
def track_product(product_id):
    product = TrackedProduct.query.get_or_404(product_id)

    # Ensure product belongs to the current user
    if product.user_id != current_user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for('home'))
    
    URL = product.url
    import urllib.parse
    safe_url = urllib.parse.quote(URL)
    SCRAPERAPI_KEY = os.environ.get('SCRAPERAPI_KEY')
    CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

    # Myntra: returns full HTML with JSON-LD to a regular Chrome UA — no proxy needed
    # Flipkart: still works with Googlebot UA
    if "myntra.com" in URL:
        try:
            myntra_headers = {
                "User-Agent": CHROME_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/",
            }
            myntra_resp = requests.get(URL, headers=myntra_headers, timeout=20, allow_redirects=True)
            if myntra_resp.status_code != 200:
                raise Exception(f"Myntra returned {myntra_resp.status_code}")
            soup2 = BeautifulSoup(myntra_resp.content, "html.parser")
            final_url = myntra_resp.url
        except Exception as ex:
            print(f"[Myntra] Request failed: {ex}")
            flash("Could not fetch Myntra product details. Please try again later.", "error")
            db.session.delete(product)
            db.session.commit()
            return redirect(url_for('home'))
    elif "flipkart.com" in URL:
        bot_resp = requests.get(URL, headers={"User-Agent": GOOGLEBOT_UA}, timeout=30, allow_redirects=True)
        final_url = bot_resp.url
        print(f"[Bot-bypass] Resolved: {URL} → {final_url}")
        soup2 = BeautifulSoup(bot_resp.content, "html.parser")
    else:
        final_url = URL
        api_url = f'http://api.scraperapi.com/?api_key={SCRAPERAPI_KEY}&url={safe_url}'
        try:
            response = requests.get(api_url, timeout=30)
            if response.status_code == 200:
                soup2 = BeautifulSoup(response.content, "html.parser")
            else:
                raise Exception("ScraperAPI Error")
        except:
            fallback_resp = requests.get(URL, headers={"User-Agent": CHROME_UA}, timeout=30, allow_redirects=True)
            soup2 = BeautifulSoup(fallback_resp.content, "html.parser")

    # Step 1: Identify website using FINAL resolved URL
    if "flipkart.com" in final_url:
        platform = "flipkart"
    elif "amazon." in final_url or "amzn." in final_url:
        platform = "amazon"
    elif "myntra.com" in final_url:
        platform = "myntra"
    elif "boat-lifestyle" in final_url:
        platform = "boat"
    else:
        platform = "unknown"

    try:
        if platform == "boat":
    #BOAT
            product_title_tag = soup2.find('h1', class_='product-meta__title')
            product_title = product_title_tag.get_text(strip=True) if product_title_tag else "boAt Product"
            price_tag = soup2.find('span', class_='mobile_atc_price')
            current_price = price_tag.get_text(strip=True).strip()[1:] if price_tag else "0"
            image_wrapper = soup2.find('div', class_='product__media-image-wrapper')
            image_tag = image_wrapper.find('img') if image_wrapper else None
            if image_tag and 'src' in image_tag.attrs:
                raw_src = image_tag['src']
                product_image = "https:" + raw_src if raw_src.startswith("//") else raw_src
            else:
                product_image = "https://upload.wikimedia.org/wikipedia/commons/a/a3/Image-not-found.png"

        elif platform == "myntra":
        # MYNTRA — serves full SSR HTML with JSON-LD Product schema to Chrome UA
        # Primary: JSON-LD → Fallback: OG title + image
            import json as _json

            product_title = None
            current_price = None
            product_image = None

            # ── Strategy 1: JSON-LD Product schema (most reliable) ────────────
            for ld_tag in soup2.find_all('script', type='application/ld+json'):
                try:
                    ld = _json.loads(ld_tag.string or '')
                    items = ld if isinstance(ld, list) else [ld]
                    for item in items:
                        if item.get('@type') == 'Product':
                            if not product_title:
                                product_title = item.get('name', '').strip()
                            if not product_image:
                                img = item.get('image', '')
                                product_image = img[0] if isinstance(img, list) else (img.get('url', '') if isinstance(img, dict) else img)
                            if not current_price:
                                offers = item.get('offers', {})
                                if isinstance(offers, list):
                                    offers = offers[0]
                                price_val = offers.get('price', '') if offers else ''
                                if price_val:
                                    current_price = str(clean_price(str(price_val)))
                        if product_title and current_price and product_image:
                            break
                except Exception:
                    pass
                if product_title and current_price and product_image:
                    break

            # ── Strategy 2: OG meta tags ──────────────────────────────────────
            if not product_title:
                og_title = soup2.find('meta', property='og:title')
                if og_title and og_title.get('content'):
                    # Strip "Buy X - ... - Apparel for Men | Myntra" suffixes
                    raw = og_title['content']
                    product_title = re.split(r' -  -| \| ', raw)[0].replace('Buy ', '', 1).strip()

            if not product_image:
                og_img = soup2.find('meta', property='og:image')
                if og_img and og_img.get('content'):
                    product_image = og_img['content']

            # Ensure defaults
            product_title = product_title or "Myntra Product"
            current_price = current_price or "0"
            product_image = product_image or "https://upload.wikimedia.org/wikipedia/commons/a/a3/Image-not-found.png"

            print(f"[Myntra] title={product_title!r} price={current_price!r} image={str(product_image)[:60]}")

        elif platform == "amazon":
        # AMAZON
            title_tag = soup2.find(id='productTitle')
            product_title = title_tag.get_text(strip=True) if title_tag else "Amazon Product"
            
            price_whole = soup2.find('span', class_='a-price-whole')
            if price_whole:
                whole = price_whole.get_text(strip=True).replace('.', '')
                fraction_tag = soup2.find('span', class_='a-price-fraction')
                fraction = fraction_tag.get_text(strip=True) if fraction_tag else "00"
                current_price = clean_price(f"{whole}.{fraction}")
            else:
                current_price = "0"

            img_tag = soup2.find('img', id='landingImage')
            if img_tag and 'src' in img_tag.attrs:
                product_image = img_tag['src']
            else:
                product_image = "https://upload.wikimedia.org/wikipedia/commons/a/a3/Image-not-found.png"

        elif platform == "flipkart":
        # FLIPKART — parsed via OG meta tags + regex (Googlebot gets SEO markup, not desktop React)
            import re

            # Title: og:title is long ("Buy XYZ | Flipkart.com"), so trim at first " - "
            title_tag = soup2.find('meta', property='og:title')
            if title_tag and title_tag.get('content'):
                raw_title = title_tag['content']
                # Strip common Flipkart SEO suffixes like " - Buy ... | Flipkart.com"
                product_title = re.split(r' - Buy | \| ', raw_title)[0].strip()
            else:
                product_title = "Flipkart Product"

            # Price: scan all text nodes containing ₹, pick the first valid number
            prices = []
            for el in soup2.find_all(string=re.compile(r'\u20B9')):
                text = el.strip().replace('\u20B9', '').strip()
                if text and len(text) < 12:
                    try:
                        prices.append(clean_price(text))
                    except Exception:
                        pass  # skip non-numeric fragments like "Buy at 330"

            current_price = str(prices[0]) if prices else "0"

            # Image: og:image is the canonical HD product image
            img_tag = soup2.find('meta', property='og:image')
            product_image = img_tag['content'] if img_tag and img_tag.get('content') else "https://upload.wikimedia.org/wikipedia/commons/a/a3/Image-not-found.png"

        else:
            product_title = "We don't support this Website yet"
            current_price = "N/A"
            product_image  = "https://upload.wikimedia.org/wikipedia/commons/a/a3/Image-not-found.png"

    except Exception as e:
        print("Scrape Parsing Error:", e)
        product_title = "Unavailable"
        current_price = "N/A"
        product_image = "https://upload.wikimedia.org/wikipedia/commons/a/a3/Image-not-found.png"



    if request.method == 'POST':
        target_price = float(request.form['target_price'])
        product.target_price = target_price
        product.current_price = current_price
        product.product_title = product_title

        # ✅ Check price and send email if needed
        if float(current_price) <= target_price:
            send_mail(
                to_email=current_user.email,
                product_title=product_title,
                product_url=product.url,
                target_price=target_price
            )


        history = (
            PriceHistory.query
            .filter_by(product_id=product.id)
            .order_by(PriceHistory.date)
            .all()
        )

        while len(history) >= 15:
            db.session.delete(history[0])
            history.pop(0)

        # Add today's price (avoid duplicate on same date)
        from sqlalchemy import func
        today = datetime.utcnow().date()
        existing_today = PriceHistory.query.filter(
            PriceHistory.product_id == product.id,
            func.date(PriceHistory.date) == today
        ).first()

        if not existing_today:
            new_entry = PriceHistory(
                product_id=product.id,
                price=current_price,
                date=datetime.utcnow()
            )
            db.session.add(new_entry)

        db.session.commit()
        flash("Target price updated successfully!", "success")
        return redirect(url_for('watchlist'))
    


    return render_template(
        "track.html",
        product=product,
        product_title=product_title,
        current_price=current_price,
        product_image=product_image
    )
  

  
@app.route('/watchlist')
@login_required
def watchlist():
    # changed so that it sorts by latest product added
    user_products = TrackedProduct.query.filter_by(user_id=current_user.id).order_by(TrackedProduct.date_added.desc()).all()

    for product in user_products:
        history = (
            PriceHistory.query
            .filter_by(product_id=product.id)
            .order_by(PriceHistory.date)
            .all()
        )
        product.history_dates = [h.date.strftime("%d %b") for h in history]
        product.history_prices = [float(h.price) for h in history]

        # ✅ Safely convert to float and compare
        if product.current_price is not None and product.target_price is not None:
            product.price_status = (
                "green" if float(product.current_price) <= float(product.target_price) else "red"
            )
        else:
            product.price_status = "gray"  # fallback color if price missing

    return render_template("watchlist.html", products=user_products)

@app.route('/delete/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    product = TrackedProduct.query.get_or_404(product_id)

    # Make sure the product belongs to the current user
    if product.user_id != current_user.id:
        flash("Unauthorized action.")
        return redirect(url_for('watchlist'))

    # Delete associated price history first (due to FK constraint)
    PriceHistory.query.filter_by(product_id=product.id).delete()

    db.session.delete(product)
    db.session.commit()

    flash("Product deleted from your watchlist.", "success")
    return redirect(url_for('watchlist'))

@app.route('/api/update_target/<int:product_id>', methods=['POST'])
@login_required
def update_target_api(product_id):
    product = TrackedProduct.query.get_or_404(product_id)
    if product.user_id != current_user.id:
        return {"error": "Unauthorized"}, 403

    try:
        data = request.get_json()
        new_target = float(data.get('target_price'))
        if new_target <= 0:
            return {"error": "Invalid price"}, 400
        
        product.target_price = new_target
        db.session.commit()
        
        # Calculate new status
        status = "gray"
        if product.current_price is not None:
             status = "green" if float(product.current_price) <= float(product.target_price) else "red"

        return {"success": True, "new_target": new_target, "status": status}, 200
    except Exception as e:
        return {"error": str(e)}, 400

@app.route('/myProfile', methods=['GET', 'POST'])
@login_required
def myProfile():
    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if not check_password_hash(current_user.password, old_password):
            flash("Incorrect current password.", "error")
            return redirect(url_for('myProfile'))

        if new_password != confirm_password:
            flash("New passwords do not match.", "error")
            return redirect(url_for('myProfile'))

        if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$', new_password):
            flash("Password must be at least 8 characters long and contain at least one uppercase letter, one lowercase letter, one digit, and one special character.", "error")
            return redirect(url_for('myProfile'))

        current_user.password = generate_password_hash(new_password)
        db.session.commit()
        flash("Password updated successfully.", "success")
        return redirect(url_for('myProfile'))

    return render_template("myProfile.html")

@app.route('/api/feedback', methods=['POST'])
@login_required
@limiter.limit("5 per hour")
def feedback():
    try:
        data = request.get_json()
        message_body = (data.get('message') or '').strip()

        if not message_body:
            return {"error": "Feedback message cannot be empty."}, 400

        sender_email = 'pricedropppp@gmail.com'
        sender_password = os.environ.get('EMAIL_PASSWORD')
        recipient_email = '27midnightlabs@gmail.com'
        user_email = current_user.email

        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = 'PDA: Feedback'
        msg['Reply-To'] = user_email

        body = f"Feedback from: {user_email}\n\n{message_body}"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()

        return {"success": True}, 200

    except Exception as e:
        print(f"❌ Feedback email error: {e}")
        return {"error": "Failed to send feedback. Please try again later."}, 500


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('signIn'))

# Schedule price checks every 12 hours
@scheduler.task('interval', id='price_check_job', hours=12)
def scheduled_job():
    with app.app_context():
        from price_checker import update_prices_and_notify
        print("Running scheduled price check...")
        update_prices_and_notify()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    app.run(host='0.0.0.0', port=5000)
   