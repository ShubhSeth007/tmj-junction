from flask import Flask, render_template, request, redirect, url_for, flash, session,jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
import json
from werkzeug.utils import secure_filename
from sqlalchemy import text
from datetime import datetime

import os
import math

# Load configuration
params = {}
try:
    with open('config.json', 'r') as c:
        params = json.load(c)["params"]
except (FileNotFoundError, KeyError) as e:
    print(f"Error loading config: {str(e)}")
    params = {}  # Ensure params exists even if config fails

# Boolean check for local server
local_server = False

app = Flask(__name__)
app.secret_key = params.get('secret_key', 'super-secret-key')  # Get from config if available
app.config['UPLOAD_FOLDER'] = params.get("folder_location", "uploads")

# Initialize Mail if configured
mail = Mail(app)
if params.get('gmail-user') and params.get('gmail-password'):
    app.config.update(
        MAIL_SERVER='smtp.gmail.com',
        MAIL_PORT=465,
        MAIL_USE_SSL=True,
        MAIL_USERNAME=params['gmail-user'],
        MAIL_PASSWORD=params['gmail-password']
    )
    mail.init_app(app)

# Database Configuration
app.config["SQLALCHEMY_DATABASE_URI"] = params.get('local_uri' if local_server else 'prod_uri', 'sqlite:///default.db')
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class Contacts(db.Model):
    __tablename__ = 'shubhjamp'
    sno = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False)
    phone_num = db.Column(db.String(12), nullable=False)
    message = db.Column(db.String(100), nullable=False)
    date = db.Column(db.String(12), nullable=True)
    subject = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(30), nullable=False)


class bookin(db.Model):
    __tablename__ = 'jampdetail'
    sno = db.Column(db.Integer, primary_key=True)
    jampad_name = db.Column(db.String(30), nullable=False)
    band_name = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    no_of_people = db.Column(db.String(5), nullable=False)
    microphones = db.Column(db.String(5), nullable=False)
    booking_date = db.Column(db.String(10), nullable=False)  # Stored as string
    time_slots = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(12), nullable=True)


# Create tables
with app.app_context():
    db.create_all()


@app.route("/")
def index():
    return render_template('index.html', params=params)


@app.route("/contact", methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            email = request.form.get('email')
            phone = request.form.get('phone')
            message = request.form.get('message')
            sub = request.form.get('subject')

            if not all([name, email, phone, message, sub]):
                flash('Please fill all required fields', 'error')
                return redirect(url_for('contact'))

            entry = Contacts(
                name=name,
                phone_num=phone,
                message=message,
                date=datetime.now().strftime('%Y-%m-%d'),
                email=email,
                subject=sub
            )
            db.session.add(entry)
            db.session.commit()
            if params:
                mail.send_message(
                    'New message from ' + name,
                    sender=email,
                    recipients=[params.get('gmail-user')],
                    body= "message:" + message + "\n" + "phone:" + phone + "\n" + "subject:" + sub + "\n" + "email:" + email
                )
            flash('Your message has been sent!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while sending your message', 'error')
            app.logger.error(f"Contact form error: {str(e)}")

    return render_template("conatctnew.html", params=params)


@app.route("/dashjamp", methods=['GET', 'POST'])
def dashjamp():
    if request.method == "POST":
        username = request.form.get("username")
        userpass = request.form.get("password")

        if username == params.get('admin_user') and userpass == params.get('admin_password'):
            session['user'] = username
            return render_template("view_bookings.html", params=params)
        else:
            flash('Invalid credentials', 'error')

    if "user" in session and session['user'] == params.get('admin_user'):
        return render_template("dashjamp.html", params=params)

    return render_template("admin.html", params=params)


# In your jampad route (most critical fixes):
@app.route("/jampad", methods=['GET', 'POST'])
def jampad():
    if request.method == 'POST':
        try:
            # Get form fields
            jampad_name = request.form.get('jampad')
            band_name = request.form.get('bandName')
            email = request.form.get('email')
            phone = request.form.get('phone')
            no_of_people = request.form.get('people')
            microphones = request.form.get('mics')
            time_slots = request.form.get('timeSlots', '')  # comma-separated string
            booking_date_str = request.form.get('bookingDate')

            # Validate required fields
            if not all([jampad_name, band_name, email, phone, no_of_people, microphones, time_slots, booking_date_str]):
                flash('Please fill all required fields', 'error')
                return redirect(url_for('jampad'))

            # Convert date format from dd-mm-yyyy to yyyy-mm-dd
            try:
                booking_date_obj = datetime.strptime(booking_date_str, '%d-%m-%Y')
                date_str = booking_date_obj.strftime('%Y-%m-%d')
            except ValueError:
                flash('Invalid date format. Use DD-MM-YYYY', 'error')
                return redirect(url_for('jampad'))

            # Check if exact slot already booked
            existing = bookin.query.filter_by(
                booking_date=date_str,
                jampad_name=jampad_name
            ).all()
            for booking in existing:
                existing_slots = set(booking.time_slots.split(','))

                new_slots = set(time_slots.split(','))
                if existing_slots & new_slots:  # if there is any overlap
                    print("Matched Existing:", booking)
                    flash('One or more selected time slots are already booked!', 'error')
                    return render_template('newjampad (1).html', params=params, existing_booking=booking)

            # Create new booking
            new_booking = bookin(
                jampad_name=jampad_name,
                band_name=band_name,
                email=email,
                phone=phone,
                no_of_people=no_of_people,
                microphones=microphones,
                booking_date=date_str,
                time_slots=time_slots,
                date=datetime.now().strftime('%Y-%m-%d')
            )

            db.session.add(new_booking)
            db.session.commit()
            if params:
                mail.send_message(
                    'New message from ' + jampad_name,
                    sender=email,
                    recipients=[params.get('gmail-user')],
                    body= "jampad:" + jampad_name + "\n" + "phone:" + phone + "\n" + "time_slots:" + time_slots + "\n" + "band_name:" + band_name
                )
            if "user" in session and session['user'] == params.get('admin_user'):
                flash('Booking recorded without payment (Admin Mode)', 'info')
                return redirect(url_for('dashjamp'))
            return redirect(url_for('pay', booking_id=new_booking.sno))

        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
            app.logger.error(f"Booking error: {str(e)}")
            return redirect(url_for('jampad'))

    # GET request
    return render_template('newjampad (1).html', params=params)


@app.route('/view_bookings', methods=['GET'])
def view_bookings():
    if "user" not in session or session['user'] != params.get('admin_user'):
        return redirect(url_for('dashjamp'))

    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    query = bookin.query

    if from_date and to_date:
        try:
            from_date_obj = datetime.strptime(from_date, '%Y-%m-%d')
            to_date_obj = datetime.strptime(to_date, '%Y-%m-%d')

            query = query.filter(
                bookin.date >= from_date_obj,
                bookin.date <= to_date_obj
            )
        except ValueError:
            flash('Invalid date format', 'error')

    bookings = query.order_by(bookin.date.desc()).all()
    return render_template('view_bookings.html',
                           bookings=bookings,
                           from_date=from_date,
                           to_date=to_date,
                           params=params)



@app.route('/delete/<int:booking_id>', methods=['POST'])
def delete_booking(booking_id):
    if "user" not in session or session['user'] != params.get('admin_user'):
        return redirect(url_for('dashjamp'))

    booking = bookin.query.get_or_404(booking_id)
    try:
        db.session.delete(booking)
        db.session.commit()
        flash('Booking deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting booking', 'error')
        app.logger.error(f"Delete booking error: {str(e)}")

    return redirect(url_for('view_bookings'))


@app.route('/get_booked_slots', methods=['GET'])
def get_booked_slots():
    jam_pad = request.args.get('jampad')  # Get the jampad name from request
    date_str = request.args.get('date')

    print(f"Received request - jampad: {jam_pad}, date: {date_str}")
    if not date_str:
        return jsonify({"error": "Date parameter missing"}), 400

    try:
        # Convert input date string to match your database format
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        db_date_str = date_obj.strftime('%Y-%m-%d')  # adjust if DB format is different

        # Query bookings for the specified date AND jampad
        query = bookin.query.filter_by(booking_date=db_date_str)
        if jam_pad:
            query = query.filter_by(jampad_name=jam_pad)

        bookings = query.all()
        booked_slots = []

        for booking in bookings:
            if booking.time_slots:
                booked_slots.extend(booking.time_slots.split(','))

        # Print for confirmation
        print(f"Booked slots for {jam_pad} on {date_str}: {booked_slots}")

        return jsonify({
            "date": date_str,
            "jampad": jam_pad,
            "booked_slots": booked_slots
        })

    except Exception as e:
        print(f"Error fetching booked slots: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/refund")
def refund():
    return render_template('refund.html', params=params)


@app.route('/upload', methods=['POST'])
def upload_file():
    if "user" not in session or session['user'] != params.get('admin_user'):
        return redirect(url_for('dashjamp'))

    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(request.url)

    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(request.url)

    if file:
        filename = secure_filename(file.filename)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        flash('File uploaded successfully', 'success')
        return redirect(url_for('dashjamp'))


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('dashjamp'))

@app.route("/privac")
def privacy():
    return render_template('privacy policy.html', params=params)

@app.route("/terms")
def terms():
    return render_template('terms-no-toggle.html', params=params)
@app.route("/admin")
def admin():
    return render_template('admin.html', params=params)





@app.route('/test_db')
def test_db():
    try:
        db.session.execute(text("SELECT 1"))
        return "Database connection successful!"
    except Exception as e:
        return f"Database connection failed: {str(e)}"




# ---------------- PHONEPE INTEGRATION ----------------
# ---------------- DEFAULT PHONEPE TEST INTEGRATION ----------------


import base64, hmac, hashlib, json, requests
from flask import redirect, url_for, flash

client_id = params.get("client_id")
client_secret = params.get("client_secret")


def get_phonepe_access_token(client_id, client_secret):
    token_url = "https://api-preprod.phonepe.com/apis/hermes/pg/v1/token"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret
    }

    response = requests.post(token_url, headers=headers, data=data)
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        print("Error getting access token:", response.text)
        return None

@app.route("/pay/<int:booking_id>")
def pay(booking_id):
    booking = bookin.query.get_or_404(booking_id)
    amount = 59900  # ₹599 in paise

    access_token = get_phonepe_access_token(client_id, client_secret)
    if not access_token:
        flash("Payment initialization failed (token error)", "error")
        return redirect(url_for("jampad"))

    transaction_id = f"TXN{booking_id}{int(datetime.now().timestamp())}"

    payload = {
        "merchantId": client_id,
        "transactionId": transaction_id,
        "merchantUserId": booking.email,
        "amount": amount,
        "redirectUrl": url_for("payment_success", _external=True),
        "redirectMode": "POST",
        "callbackUrl": url_for("payment_callback", _external=True),
        "mobileNumber": booking.phone,
        "paymentInstrument": {
            "type": "PAY_PAGE"
        }
    }

    url = "https://api-preprod.phonepe.com/apis/pg-sandbox/pg/v1/pay"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

    response = requests.post(url, headers=headers, json=payload)
    res_json = response.json()
    print("PhonePe response:", res_json)

    if res_json.get("success"):
        redirect_url = res_json["data"]["instrumentResponse"]["redirectInfo"]["url"]
        return redirect(redirect_url)
    else:
        flash("Payment failed: " + res_json.get("message", "Unknown error"), "error")
        return redirect(url_for("jampad"))




@app.route("/payment_success", methods=["POST"])
def payment_success():
    return "✅ Payment successful! (Test Key Response)"

@app.route("/payment_callback", methods=["POST"])
def payment_callback():
    data = request.get_json()
    print("PhonePe callback (test):", data)
    return "OK", 200



if __name__ == "__main__":
    app.run(debug=True)