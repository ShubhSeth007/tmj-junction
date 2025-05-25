from flask import Flask, render_template, request, redirect, url_for, flash, session,jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
import json
from werkzeug.utils import secure_filename
from sqlalchemy import text
from datetime import datetime
import razorpay

import os
import math

# Load configuration
try:
    with open('config.json', 'r') as c:
        params = json.load(c)["params"]
except (FileNotFoundError, KeyError) as e:
    print(f"Error loading config: {str(e)}")
    params = {}  # Ensure params exists even if config fails

# Boolean check for local server
local_server = False  # Set to True for local testing


app = Flask(__name__)
app.secret_key = params.get('secret_key', 'super-secret-key')  # Get from config if available
app.config['UPLOAD_FOLDER'] = params.get("folder_location", "uploads")

app.config.update(
    SESSION_COOKIE_SECURE=True,        # Ensures cookie is sent only over HTTPS
    SESSION_COOKIE_SAMESITE='Lax',     # Helps with cross-site compatibility (e.g., redirects)
    SESSION_COOKIE_HTTPONLY=True,      # Prevents JS access — safe default
)

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

# Initialize Razorpay client with test credentials
razorpay_client = razorpay.Client(auth=(params.get('razorpay_key_id'), params.get('razorpay_key_secret')))


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
    booking_date = db.Column(db.String(10), nullable=False)
    time_slots = db.Column(db.String(200), nullable=False)
    date = db.Column(db.String(12), nullable=True)
    payment_id = db.Column(db.String(100), nullable=True)
    payment_status = db.Column(db.String(20), nullable=False, default='pending')
    is_admin_booking = db.Column(db.Boolean, default=False)


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
            time_slots = request.form.get('timeSlots', '')
            booking_date_str = request.form.get('bookingDate')
            amount = request.form.get('amount')  # Get amount from form

            # Validate required fields
            if not all([jampad_name, band_name, email, phone, no_of_people, microphones, time_slots, booking_date_str,
                        amount]):

                flash('Please fill all required fields', 'error')
                return redirect(url_for('jampad'))

            # Convert date format
            try:
                booking_date_obj = datetime.strptime(booking_date_str, '%d-%m-%Y')
                db_date_str = booking_date_obj.strftime('%Y-%m-%d')
            except ValueError:
                flash('Invalid date format. Use DD-MM-YYYY', 'error')
                return redirect(url_for('jampad'))

            # Check slot availability
            existing = bookin.query.filter_by(
                booking_date=db_date_str,
                jampad_name=jampad_name
            ).all()

            for booking in existing:
                existing_slots = set(booking.time_slots.split(','))
                new_slots = set(time_slots.split(','))
                if existing_slots & new_slots:
                    flash('Time slots already booked!', 'error')
                    return render_template('newjampad (1).html', params=params, existing_booking=booking)

            # Store in session
            session['pending_booking'] = {
                'jampad_name': jampad_name,
                'band_name': band_name,
                'email': email,
                'phone': phone,
                'no_of_people': no_of_people,
                'microphones': microphones,
                'booking_date': db_date_str,
                'time_slots': time_slots,
                'amount': amount
            }
            session.modified = True
            print(f"Session stored: {session.get('pending_booking')}")

            if "user" in session and session['user'] == params.get('admin_user'):
                # Handle admin booking
                return save_admin_booking()
            else:
                try:
                    amount = int(amount)
                except ValueError:
                    flash('Invalid amount value', 'error')
                    return redirect(url_for('jampad'))

                # Redirect to payment with POST method preservation
                return redirect(url_for('initiate_payment', amount=amount))

        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
            return redirect(url_for('jampad'))

    return render_template('newjampad (1).html', params=params)


def save_admin_booking():
    """Save admin booking directly"""
    print("broro")
    booking_data = session['pending_booking']
    booking = bookin(
        jampad_name=booking_data['jampad_name'],
        band_name=booking_data['band_name'],
        email=booking_data['email'],
        phone=booking_data['phone'],
        no_of_people=booking_data['no_of_people'],
        microphones=booking_data['microphones'],
        booking_date=booking_data['booking_date'],
        time_slots=booking_data['time_slots'],
        date=datetime.now().strftime('%Y-%m-%d'),
        payment_status='admin_booking',
        is_admin_booking=True
    )

    db.session.add(booking)
    db.session.commit()

    # Email sending logic
    if 'gmail-user' in params and params['gmail-user']:
        try:
            # Email to user
            mail.send_message(
                'Admin Booking Confirmation',
                sender=params['gmail-user'],
                recipients=[booking_data['email']],
                body=f"""Your JamPad booking has been created by admin.

JamPad: {booking_data['jampad_name']}
Date: {booking_data['booking_date']}
Time Slot: {booking_data['time_slots']}
Band Name: {booking_data['band_name']}
Status: Admin Booking
"""
            )

            # Email to admin
            mail.send_message(
                'New Admin Booking',
                sender=params['gmail-user'],
                recipients=[params['gmail-user']],
                body=f"""A new admin booking has been created.

JamPad: {booking_data['jampad_name']}
Band Name: {booking_data['band_name']}
Date: {booking_data['booking_date']}
Time Slot: {booking_data['time_slots']}
Status: Admin Booking
"""
            )
        except Exception as e:
            print(f"Email sending failed: {str(e)}")

    flash('Admin booking created!', 'success')
    return redirect(url_for('dashjamp'))



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

@app.route("/initiate-payment")
def initiate_payment():
    if 'pending_booking' not in session:
        flash('Session expired. Please start over.', 'error')
        return redirect(url_for('jampad'))

    booking = session['pending_booking']
    amount = request.args.get('amount')# ₹599 in paise
    amount=int(amount)
    print(f"the amount is {amount}")

    try:
        # Create Razorpay order
        order = razorpay_client.order.create({
            'amount': amount * 100,
            'currency': 'INR',
            'payment_capture': '1',
            'notes': {
                'booking_for': f"{booking['jampad_name']} - {booking['time_slots']}"
            }
        })

        return render_template('payment.html',
                               razorpay_key_id=params['razorpay_key_id'],
                               order_id=order['id'],
                               amount=amount,
                               name=booking['band_name'],
                               email=booking['email'],
                               contact=booking['phone'],
                               booking=booking,

                               params=params
                               )

    except Exception as e:
        flash(f'Payment error: {str(e)}', 'error')
        return redirect(url_for('jampad'))


@app.route("/payment/success")
def payment_success():
    if 'pending_booking' not in session:
        flash('Session expired. Please start over.', 'error')
        return redirect(url_for('jampad'))

    payment_id = request.args.get('payment_id')
    order_id = request.args.get('order_id')


    try:
        # Verify payment with Razorpay
        payment = razorpay_client.payment.fetch(payment_id)

        if payment['status'] == 'captured':
            # Save to database
            booking_data = session['pending_booking']
            booking = bookin(  # Make sure this matches your model name
                jampad_name=booking_data['jampad_name'],
                band_name=booking_data['band_name'],
                email=booking_data['email'],
                phone=booking_data['phone'],
                no_of_people=booking_data['no_of_people'],
                microphones=booking_data['microphones'],
                booking_date=booking_data['booking_date'],
                time_slots=booking_data['time_slots'],
                date=datetime.now().strftime('%Y-%m-%d'),
                payment_id=order_id,
                payment_status='completed'
            )

            db.session.add(booking)
            db.session.commit()

            # Create booking details for template
            booking_details = {
                'jampad_name': booking.jampad_name,
                'booking_date': booking.booking_date,
                'time_slots': booking.time_slots,
                'payment_id': booking.payment_id,
                'band_name': booking.band_name,
                'microphones': booking.microphones,
                'band_name': booking.band_name,
                'no_of_people': booking.no_of_people
            }

            # Send confirmation email
            if 'gmail-user' in params and params['gmail-user']:
                try:
                    # Email to user
                    mail.send_message(
                        'Booking Confirmation',
                        sender=params['gmail-user'],
                        recipients=[booking_data['email']],
                        body=f"""Your booking for {booking_data['jampad_name']} is confirmed!

            Date: {booking_data['booking_date']}
            Time: {booking_data['time_slots']}
            Band Name: {booking_data['band_name']}
            Payment ID: {order_id}
            """
                    )

                    # Email to admin
                    mail.send_message(
                        'New Booking Received',
                        sender=params['gmail-user'],
                        recipients=[params['gmail-user']],
                        body=f"""A new booking has been made.

            JamPad: {booking_data['jampad_name']}
            Band Name: {booking_data['band_name']}
            Date: {booking_data['booking_date']}
            Time: {booking_data['time_slots']}
            Payment ID: {order_id}
            """
                    )
                except Exception as e:
                    print(f"Email sending failed: {str(e)}")

            # Clear session
            session.pop('pending_booking', None)

            # Debug print
            print("Rendering success.html with booking:", booking_details)

            # Render the template directly
            return render_template('success.html',
                                   booking=booking_details)

        else:
            flash('Payment verification failed', 'error')
            return redirect(url_for('jampad'))

    except Exception as e:
        db.session.rollback()
        print(f"Payment processing error: {str(e)}")  # Debug print
        flash(f'Payment processing error: {str(e)}', 'error')
        return redirect(url_for('jampad'))


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




if __name__ == "__main__":
    app.run(debug=True)