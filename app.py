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

app = Flask(__name__)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'signIn'  # Redirects to this page if @login_required is used


app.secret_key = 'your_secret_key'
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
        sender_email = '27demonstration@gmail.com'
        sender_password = 'laqs gmba zzyw ktyt'  # ⚠️ Use environment variable in production

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
def signUp():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Server-side checks
        if not name or not email or not password or not confirm_password:
            flash('All fields are required.')
            return redirect(url_for('signUp'))

        if password != confirm_password:
            flash('Passwords do not match.')
            return redirect(url_for('signUp'))

        if len(password) < 6:
            flash('Password must be at least 6 characters.')
            return redirect(url_for('signUp'))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered.')
            return redirect(url_for('signIn'))

        hashed_password = generate_password_hash(password)
        new_user = User(name=name, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please log in.')
        return redirect(url_for('signIn'))

    return render_template('signUp.html')

@app.route('/home', methods=['GET', 'POST'])
@login_required
def home():
    if request.method == 'POST':
        product_url = request.form['product_url'].strip()

        if not product_url:
            flash("Please enter a product URL.")
            return redirect(url_for('home'))
        
        # 🔍 Check if the same product already exists for this user
        existing_product = TrackedProduct.query.filter_by(url=product_url, user_id=current_user.id).first()

        if existing_product:
            flash("Product already exists. Redirecting to track page.")
            return redirect(url_for('track_product', product_id=existing_product.id))

        # ✅ If not found, create a new product entry
        # Create a new product entry with just URL for now
        new_product = TrackedProduct(
            url=product_url,
            user_id=current_user.id
        )
        db.session.add(new_product)
        db.session.commit()
        flash("Product URL saved successfully.")
        return redirect(url_for('track_product', product_id=new_product.id))

    return render_template('home.html')


@app.route('/track/<int:product_id>', methods=['GET', 'POST'])
@login_required
def track_product(product_id):
    product = TrackedProduct.query.get_or_404(product_id)

    # Ensure product belongs to the current user
    if product.user_id != current_user.id:
        flash("Unauthorized access.")
        return redirect(url_for('home'))
    
    URL = product.url
    headers =  {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 OPR/113.0.0.0"}
   
    SCRAPERAPI_KEY = 'd147aa3553b782e49185ddea6c5f41ee'  # 🔑 Replace with your actual key
    api_url = f'http://api.scraperapi.com/?api_key={SCRAPERAPI_KEY}&url={URL}'
    response = requests.get(api_url, headers=headers, timeout=30)
    soup1 = BeautifulSoup(response.content, "html.parser")
    soup2 = BeautifulSoup(soup1.prettify(), "html.parser")

    # Step 1: Identify website
    if "flipkart.com" in URL:
        platform = "flipkart"
    elif "amazon." in URL:
        platform = "amazon"
    elif "nykaa.com" in URL:
        platform = "nykaa"
    elif "boat-lifestyle" in URL:
        platform = "boat"
    else:
        platform = "unknown"

    try:
        if platform == "boat":
    #BOAT
            product_title = soup2.find('h1', class_='product-meta__title heading h3').get_text(strip=True)
            current_price = soup2.find('span', class_='mobile_atc_price').get_text(strip=True) 
            current_price = current_price.strip()[1:]
        
            image_wrapper = soup2.find('div', class_='product__media-image-wrapper aspect-ratio aspect-ratio--natural')
            if image_wrapper:
                image_tag = image_wrapper.find('img', alt=lambda val: val and 'boAt' in val)
            else:
                image_tag = None
            if image_tag:
                raw_src = image_tag['src']
                product_image = "https:" + raw_src if raw_src.startswith("//") else raw_src
            else:
                product_image = "https://upload.wikimedia.org/wikipedia/commons/a/a3/Image-not-found.png"

        elif platform == "nykaa":
        # NYKAA
            product_title = soup2.find('h1', class_='css-1gc4x7i').get_text(strip=True)
            current_price = soup2.find('span', class_='css-1jczs19').get_text(strip=True) 
            current_price = current_price.strip()[1:]

            image_wrapper = soup2.find('div', class_='productSelectedImage css-eyk94w')
            if image_wrapper:
                image_tag = image_wrapper.find('img', alt=lambda val: val and 'product' in val)
            else:
                image_tag = None
            if image_tag:
                raw_src = image_tag['src']
                product_image = "https:" + raw_src if raw_src.startswith("//") else raw_src
            else:
                product_image = "https://upload.wikimedia.org/wikipedia/commons/a/a3/Image-not-found.png"

        elif platform == "amazon":
        # AMAZON
            product_title = soup2.find('h1', class_='a-size-large a-spacing-none').get_text(strip=True)
            whole = soup2.find('span', class_='a-price-whole').get_text(strip=True)
            fraction = soup2.find('span', class_='a-price-fraction').get_text(strip=True)
            current_price = clean_price(f"{whole}.{fraction}")

            image_wrapper = soup2.find('div', class_='imgTagWrapper')
            if image_wrapper:
                image_tag = image_wrapper.find('img', class_=lambda x: x and 'a-dynamic-image' in x and 'a-stretch-vertical' in x)
            else:
                image_tag = None
            if image_tag:
                raw_src = image_tag['src']
                product_image = "https:" + raw_src if raw_src.startswith("//") else raw_src
            else:
                product_image = "https://upload.wikimedia.org/wikipedia/commons/a/a3/Image-not-found.png"

        elif platform == "flipkart":
        # FLIPKART
            product_title = soup2.select_one('h1._6EBuvT span').get_text(strip=True)
            current_price = soup2.find('div', class_='Nx9bqj CxhGGd').get_text(strip=True)
            current_price = current_price.strip()[1:]

            image_wrapper = soup2.find('div', class_='_4WELSP _6lpKCl')
            if image_wrapper:
                image_tag = image_wrapper.find('img', class_=lambda x: x and 'DByuf4' in x and ' IZexXJ' in x and 'jLEJ7H' in x)
            else:
                image_tag = None
            if image_tag:
                raw_src = image_tag['src']
                product_image = "https:" + raw_src if raw_src.startswith("//") else raw_src
            else:
                product_image = "https://upload.wikimedia.org/wikipedia/commons/a/a3/Image-not-found.png"

        else:
            product_title = "We don't support this Website yet"
            current_price = "N/A"
            product_image  = "https://upload.wikimedia.org/wikipedia/commons/a/a3/Image-not-found.png"

    except AttributeError:
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
        flash('Target price updated successfully!')
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
    user_products = TrackedProduct.query.filter_by(user_id=current_user.id).all()

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

@app.route('/myProfile', methods=['GET', 'POST'])
@login_required
def myProfile():
    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if not check_password_hash(current_user.password, old_password):
            flash("Incorrect current password.")
            return redirect(url_for('myProfile'))

        if new_password != confirm_password:
            flash("New passwords do not match.")
            return redirect(url_for('myProfile'))

        if len(new_password) < 6:
            flash("Password must be at least 6 characters.")
            return redirect(url_for('myProfile'))

        current_user.password = generate_password_hash(new_password)
        db.session.commit()
        flash("Password updated successfully.")
        return redirect(url_for('myProfile'))

    return render_template("myProfile.html")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    app.run(host='0.0.0.0', port=5000)
   