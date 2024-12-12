import os
import json  # Make sure to import json for handling JSON data
from functools import wraps
from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash
from PIL import Image
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from gunicorn.app.base import BaseApplication
import mysql.connector
import MySQLdb
from mysql.connector import Error
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

# Load environment variables from .env file
load_dotenv()

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for session management

# After your Flask app creation
app.config['PORT'] = int(os.environ.get('PORT', 10000))

# Set the upload folders for item grid and detail images
GRID_UPLOAD_FOLDER = 'static/uploads/grid_images'
DETAIL_UPLOAD_FOLDER = 'static/uploads/detail_images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
UPLOAD_FOLDER = 'static/uploads'


app.config['GRID_UPLOAD_FOLDER'] = GRID_UPLOAD_FOLDER
app.config['DETAIL_UPLOAD_FOLDER'] = DETAIL_UPLOAD_FOLDER
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure that the upload directories exist
os.makedirs(GRID_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DETAIL_UPLOAD_FOLDER, exist_ok=True)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Allowed file check
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database connection
def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'mysql-1eef0d0e-marketplace-e1a9.f.aivencloud.com'),
            port=int(os.getenv('DB_PORT', '28562')),
            user=os.getenv('DB_USER', 'avnadmin'),
            password=os.getenv('DB_PASSWORD', 'AVNS_1z1MpJQf9fVC_t-eNwP'),
            database=os.getenv('DB_NAME', 'defaultdb'),
            ssl_disabled=True  # Changed this line
        )
        print("Successfully connected to database")
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        raise e

# Create the items table
def create_items_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(''' 
        CREATE TABLE IF NOT EXISTS items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            price DECIMAL(10, 2) NOT NULL,
            description TEXT NOT NULL,
            quality ENUM('new', 'used_like_new', 'used_good', 'used_fair') NOT NULL,
            category VARCHAR(100) NOT NULL,
            meetup_place VARCHAR(255) NOT NULL,
            seller_phone VARCHAR(15) NOT NULL,
            grid_image VARCHAR(255),
            detail_images TEXT,
            seller_id INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

# Example in-memory database (replace with a real database for production)
proofs_data = []

# Route for user information
@app.route('/user_info', methods=['GET', 'POST'])
@login_required
def user_info():
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        # Handle form submission for user info updates
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        username = request.form['username']
        email = request.form['email']

        # Update user information
        cursor.execute(
            "UPDATE users SET first_name = %s, last_name = %s, username = %s, email = %s WHERE id = %s",
            (first_name, last_name, username, email, user_id)
        )
        conn.commit()

    # Fetch current user information
    cursor.execute(
        "SELECT first_name, last_name, username, email, profile_picture FROM users WHERE id = %s", 
        (user_id,)
    )
    user_data = cursor.fetchone()
    
    # Debug: Print user data to console
    print("User Data:", user_data)  # This will help debug if the profile_picture URL is being retrieved

    # Fetch posted items
    posted_items = get_user_items(user_id)

    cursor.close()
    conn.close()

    return render_template('user_info.html', user=user_data, posted_items=posted_items)



    @staticmethod
    def get(user_id):
        conn = connect_to_database()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user_data = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user_data:
                return User(
                    id=user_data['id'],
                    username=user_data['username'],
                    email=user_data['email']
                )
        return None

# Index route to display homepage
@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)  # Use dictionary cursor for named access
    cursor.execute("SELECT * FROM items")  # Fetch all items from the database
    items = cursor.fetchall()  # Get all items as a list of dictionaries
    cursor.close()
    conn.close()
    return render_template('homepage.html', items=items)

# Homepage route
@app.route('/homepage')
def homepage():

    # Check if 'user_id' exists in the session
    if session.get('user_id'):  # Safely access 'user_id' using get()
        return redirect(url_for('main_index'))  # Redirect to main_index if user is logged in
    else:
        return render_template('homepage.html')  # Render the login page if not logged in

# Route for searching and filtering items
@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query', '').lower()  # Get the search query
    min_price = request.args.get('min_price', type=int)  # Get min price filter
    max_price = request.args.get('max_price', type=int)  # Get max price filter
    quality = request.args.get('quality')  # Get quality filter
    category = request.args.get('category')  # Get category filter

    # Start building the SQL query
    sql = "SELECT * FROM items WHERE LOWER(name) LIKE %s OR LOWER(description) LIKE %s"
    params = ['%' + query + '%', '%' + query + '%']

    # Add price filters if provided
    if min_price is not None:
        sql += " AND price >= %s"
        params.append(min_price)
    
    if max_price is not None:
        sql += " AND price <= %s"
        params.append(max_price)

    # Add quality filter if provided and not "all"
    if quality and quality != 'all':
        sql += " AND quality = %s"
        params.append(quality)

    # Add category filter if provided and not "all"
    if category and category != 'all':
        sql += " AND category = %s"
        params.append(category)

    # Execute the query
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql, tuple(params))
    results = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('search_results.html', query=query, results=results, category=category, quality=quality, min_price=min_price, max_price=max_price)


# Route to update an item
@app.route('/update_item/<int:item_id>', methods=['GET', 'POST'])
@login_required
def update_item(item_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch item details if GET request
    if request.method == 'GET':
        cursor.execute("SELECT * FROM items WHERE id = %s AND user_id = %s", (item_id, session['user_id']))
        item = cursor.fetchone()
        cursor.close()
        conn.close()
        if item:
            return render_template('update_item.html', item=item)
        else:
            return redirect(url_for('user_info'))

    # Handle item update if POST request
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        grid_image = request.form.get('grid_image')  # Update image if needed
        cursor.execute(
            "UPDATE items SET name = %s, price = %s, grid_image = %s WHERE id = %s AND user_id = %s",
            (name, price, grid_image, item_id, session['user_id'])
        )
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('user_info'))

# Route to delete an item
@app.route('/delete_item/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM items WHERE id = %s AND user_id = %s", (item_id, session['user_id']))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('user_info'))


# Function to get user items
def get_user_items(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM items WHERE user_id = %s", (user_id,))
    items = cursor.fetchall()
    cursor.close()
    conn.close()
    return items

# Function to get all items
def get_all_items():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM items")
    items = cursor.fetchall()
    cursor.close()
    conn.close()
    return items

# Route for main index
@app.route('/main_index')
@login_required  # Ensure the user is logged in
def main_index():
    user_id = session['user_id']  # Assuming user_id is stored in the session
    user_items = get_user_items(user_id)  # Fetch user items from the database
    all_items = get_all_items()  # Fetch all items for display
    return render_template('main_index.html', user_items=user_items, all_items=all_items)


@app.route('/filter/<category>', methods=['GET'])
@login_required
def filter_by_category(category):
    user_id = session['user_id']
    user_items = get_user_items(user_id)
    
    if category == 'all':
        all_items = get_all_items()
    else:
        all_items = get_items_by_category(category)  # Fetch items filtered by category
    
    return render_template('main_index.html', user_items=user_items, all_items=all_items)

def get_items_by_category(category):
    connection = None  # Initialize connection variable here to avoid reference errors
    try:
        # Set up the database connection
        connection = mysql.connector.connect(
            host='localhost',
            user='root',
            password='123123123',  # No password
            database='marketplace'
        )

        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)  # Use dictionary for easier column-to-field mapping
            query = "SELECT * FROM items WHERE category = %s"
            cursor.execute(query, (category,))
            items = cursor.fetchall()  # Fetch all items that match the category
            cursor.close()
            return items
        else:
            print("Unable to connect to the database")
            return []

    except Error as e:
        print(f"Error: {e}")
        return []

    finally:
        # Make sure the connection is only closed if it was initialized
        if connection is not None and connection.is_connected():
            connection.close()


@app.route('/item/<int:item_id>')
def item_detail(item_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Join the items table with users table to get seller information including profile picture
    cursor.execute("""
        SELECT i.*, u.username, u.profile_picture 
        FROM items i 
        LEFT JOIN users u ON i.user_id = u.id 
        WHERE i.id = %s
    """, (item_id,))
    
    item = cursor.fetchone()
    
    if item:
        # Convert the quality value to a more readable format
        item_quality = item['quality'].replace('_', ' ').title()
        cursor.close()
        conn.close()
        return render_template('item_detail.html', item=item, item_quality=item_quality)
    else:
        cursor.close()
        conn.close()
        return "Item not found", 404



@app.route('/item/<int:item_id>', methods=['GET'])
def item_details(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Query to get item details and username of the seller
    cursor.execute("""
        SELECT items.*, users.username
        FROM items
        JOIN users ON items.user_id = users.id
        WHERE items.id = %s
    """, (item_id,))
    item = cursor.fetchone()

    conn.close()

    if item:
        return render_template('item_details.html', item=item)
    else:
        flash('Item not found', 'danger')
        return redirect(url_for('main_index'))


@app.route('/save_item/<int:item_id>', methods=['POST'])
def save_item(item_id):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))  # Redirect if user not logged in

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if the item is already saved
    cursor.execute("""
        SELECT 1 FROM saved_items WHERE user_id = %s AND item_id = %s
    """, (user_id, item_id))
    existing_item = cursor.fetchone()

    if existing_item:
        # Item is already saved, return an error message
        cursor.close()
        conn.close()
        return jsonify({'status': 'error', 'message': 'This item is already saved.'})

    # Insert the item into saved_items if not already saved
    cursor.execute("""
        INSERT INTO saved_items (user_id, item_id)
        VALUES (%s, %s)
    """, (user_id, item_id))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'status': 'success', 'message': 'Item saved successfully.'})



@app.route('/saved_items')
def saved_items():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))  # Redirect if user not logged in

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT items.* FROM items
        JOIN saved_items ON items.id = saved_items.item_id
        WHERE saved_items.user_id = %s
    """, (user_id,))
    saved_items = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('saved_items.html', saved_items=saved_items)


@app.route('/remove_saved_item/<int:item_id>', methods=['POST'])
def remove_saved_item(item_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'You must be logged in to remove items.'})

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if the item exists
        cursor.execute("SELECT 1 FROM saved_items WHERE user_id = %s AND item_id = %s", (user_id, item_id))
        item_exists = cursor.fetchone()

        if not item_exists:
            return jsonify({'status': 'error', 'message': 'The item does not exist in your saved list.'})

        # Remove the item
        cursor.execute("DELETE FROM saved_items WHERE user_id = %s AND item_id = %s", (user_id, item_id))
        conn.commit()

        # Explicitly return success
        return jsonify({'status': 'success', 'message': 'Item removed from your saved list.'})
    except Exception as e:
        print(f"Error occurred: {e}")  # Debugging
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred while removing the item.'})
    finally:
        cursor.close()
        conn.close()






@app.route('/adminresponse', methods=['GET'])
def admin_response():
    """Renders the admin page with the list of proofs."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM handle_request")
        columns = [column[0] for column in cursor.description]  # Get column names
        requests = [dict(zip(columns, row)) for row in cursor.fetchall()]  # Map rows to dictionaries
        
        print("Fetched data:", requests)  # Debugging line to check what data is returned
        
        return render_template('adminresponse.html', requests=requests)
    except Exception as e:
        flash(f"Error retrieving data: {e}", "danger")
        return redirect(url_for('admin_response'))
    finally:
        cursor.close()
        conn.close()





@app.route('/confirm_request/<string:reference_type>', methods=['POST'])
def confirm_request(reference_type):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Update the status to 'Confirmed' in the handle_request table
        cursor.execute("UPDATE handle_request SET status = %s WHERE reference_type = %s", ('Confirmed', reference_type))
        # Log the status change in the status_history table
        cursor.execute(
            "INSERT INTO status_history (reference_type, status) VALUES (%s, %s)",
            (reference_type, 'Confirmed')
        )
        conn.commit()
        flash(f"Request with reference type {reference_type} has been confirmed.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error updating status: {e}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('admin_response'))


@app.route('/reject_request/<string:reference_type>', methods=['POST'])
def reject_request(reference_type):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Update the status to 'Rejected' in the handle_request table
        cursor.execute("UPDATE handle_request SET status = %s WHERE reference_type = %s", ('Rejected', reference_type))
        # Log the status change in the status_history table
        cursor.execute(
            "INSERT INTO status_history (reference_type, status) VALUES (%s, %s)",
            (reference_type, 'Rejected')
        )
        conn.commit()
        flash(f"Request with reference type {reference_type} has been rejected.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error updating status: {e}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('admin_response'))








@app.route('/submit_proof', methods=['POST'])
def submit_proof():
    sender_name = request.form.get('sender_name')
    sender_number = request.form.get('sender_number')
    reference_type = request.form.get('reference_type')
    screenshot_file = request.files.get('screenshot')
    item_name = request.form.get('item_name')
    item_id = request.form.get('item_id')

    # Validate screenshot and item_name
    if not item_name:
        flash("Item name is required.", "danger")
        return redirect(url_for('item_detail', item_id=item_id))

    if not screenshot_file or screenshot_file.filename == '':
        flash("Screenshot is required. Please upload a screenshot of the payment.", "danger")
        return redirect(url_for('item_detail', item_id=item_id))

    # Process the screenshot and save it
    file_path = f"static/uploads/{screenshot_file.filename}"
    screenshot_file.save(file_path)

    # Insert proof of payment
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = """
        INSERT INTO handle_request (sender_name, sender_number, reference_type, screenshot, status, item_name)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (sender_name, sender_number, reference_type, file_path, 'Pending', item_name))
        conn.commit()
        flash("Proof of payment has been successfully submitted. Your request is now pending approval.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error while submitting proof of payment: {e}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('item_detail', item_id=item_id))




@app.route('/check_status')
def check_status():
    reference_type = request.args.get('referenceType')

    if not reference_type:
        return jsonify({"error": "Reference type is required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Query the database for the reference type
    cursor.execute("""
        SELECT status FROM handle_request WHERE reference_type = %s
    """, (reference_type,))
    
    record = cursor.fetchone()
    cursor.close()
    conn.close()

    if record:
        return jsonify({"status": record['status']})
    return jsonify({"error": "Reference type not found."}), 404





@app.route('/proceed_purchase/<int:item_id>', methods=['POST'])
def proceed_purchase(item_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT items.*, users.username
        FROM items
        JOIN users ON items.user_id = users.id
        WHERE items.id = %s
    """, (item_id,))
    
    item = cursor.fetchone()
    cursor.close()
    conn.close()

    if item:
        buyer_name = "John Doe"  # Replace with session/user data if available
        contact_info = "johndoe@example.com"  # Replace with session/user data if available
        
        return render_template(
            'purchasesuccess.html', 
            buyer_name=buyer_name,
            contact_info=contact_info,
            item=item
        )
    else:
        return "Item not found", 404


# Route for login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')  # Fetch email instead of username
        password = request.form.get('password')

        if not email or not password:  # Check for missing email or password
            return "Missing email or password", 400  # Return an informative error

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            # Query to check for the user's email
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            user_data = cursor.fetchone()

            # Validate user and password
            if user_data and check_password_hash(user_data['password'], password):  # Use hashed password check
                user = User(user_data['id'], user_data['username'], user_data['email'])  # Create User object
                login_user(user)  # Log in the user with Flask-Login
                session['user_id'] = user.id  # Store user ID in session
                return redirect(url_for('main_index'))  # Redirect to main_index on successful login

            return "Invalid email or password", 401  # Handle invalid login
        except Exception as e:
            return f"An error occurred: {e}", 500  # Handle unexpected errors
        finally:
            cursor.close()
            conn.close()  # Ensure the database connection is closed

    # Render the login form for GET requests
    return render_template('homepage.html')



# Route for registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            # Collect data from the form
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')

            # Basic validation
            if not all([first_name, last_name, username, email, password, confirm_password]):
                flash('All fields are required')
                return redirect(url_for('homepage'))  # Changed from register to homepage

            if password != confirm_password:
                flash('Passwords do not match')
                return redirect(url_for('register'))

            # Connect to the database
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # Check if username or email already exists
            cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
            existing_user = cursor.fetchone()
            
            if existing_user:
                flash('Username or email already exists')
                return redirect(url_for('register'))

            # Hash password and insert new user
            hashed_password = generate_password_hash(password)
            cursor.execute("""
                INSERT INTO users (first_name, last_name, username, email, password)
                VALUES (%s, %s, %s, %s, %s)
            """, (first_name, last_name, username, email, hashed_password))
            
            conn.commit()
            
            # Get the new user's ID
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            user_data = cursor.fetchone()
            
            cursor.close()
            conn.close()

            if user_data:
                # Log the user in
                user = User()
                user.id = user_data['id']
                user.username = username
                login_user(user)
                
                # Store user_id in session
                session['user_id'] = user_data['id']
                
                flash('Registration successful!')
                return redirect(url_for('main_index'))
            
        except Exception as e:
            print(f"Registration error: {str(e)}")
            flash('An error occurred during registration')
            return redirect(url_for('homepage'))

    # For GET requests, redirect to homepage
    return redirect(url_for('homepage'))



# Route for logout
@app.route('/logout')
@login_required  # Ensure the user is logged in
def logout():
    logout_user()  # Log the user out
    session.pop('user_id', None)  # Remove user ID from session
    return redirect(url_for('homepage'))  # Redirect to the homepage

# User loader function for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# Ensure to create the items table when the application starts
create_items_table()

@app.route('/post_item', methods=['GET', 'POST'])
@login_required
def post_item():
    if request.method == 'POST':
        item_name = request.form['item_name']
        item_price = request.form['item_price']
        item_desc = request.form['item_desc']
        item_quality = request.form['item_quality']
        item_category = request.form['item_category']
        meetup_place = request.form['meetup_place']
        seller_phone = request.form['seller_phone']

        # Handle Grid Image upload
        grid_image = request.files['grid_image']
        grid_image_url = None
        if grid_image and allowed_file(grid_image.filename):
            upload_result = cloudinary.uploader.upload(grid_image)
            grid_image_url = upload_result['secure_url']

        # Handle Detail Image uploads (multiple images)
        detail_images = request.files.getlist('detail_images')
        detail_image_urls = []

        for detail_image in detail_images:
            if detail_image and allowed_file(detail_image.filename):
                upload_result = cloudinary.uploader.upload(detail_image)
                detail_image_urls.append(upload_result['secure_url'])

        # Save item to the database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(''' 
            INSERT INTO items (name, price, description, quality, category, meetup_place, seller_phone, grid_image, detail_images, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (item_name, item_price, item_desc, item_quality, item_category, meetup_place, seller_phone, 
              grid_image_url, ','.join(detail_image_urls), session.get('user_id')))
        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('main_index'))

    return render_template('post_item.html')

# Add this new route to handle profile picture updates
@app.route('/update_profile_picture', methods=['POST'])
@login_required
def update_profile_picture():
    if 'profile_picture' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'})
    
    file = request.files['profile_picture']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})

    if file and allowed_file(file.filename):
        try:
            # Upload to Cloudinary with specific options
            upload_result = cloudinary.uploader.upload(
                file,
                folder="profile_pictures",  # Store in a specific folder
                transformation=[
                    {'width': 300, 'height': 300, 'crop': 'fill'},  # Resize and crop to square
                    {'quality': 'auto:good'}  # Optimize quality
                ]
            )
            
            # Update database with the new profile picture URL
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE users SET profile_picture = %s WHERE id = %s",
                (upload_result['secure_url'], session['user_id'])
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            # Return the new profile picture URL
            return jsonify({
                'success': True,
                'profile_picture_url': upload_result['secure_url']
            })
            
        except Exception as e:
            print(f"Error uploading profile picture: {str(e)}")  # Debug log
            return jsonify({'success': False, 'error': str(e)})
    
    return jsonify({'success': False, 'error': 'Invalid file type'})

# Add this function to create/update the users table
def update_users_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Add profile_picture column if it doesn't exist
        cursor.execute("""
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS profile_picture VARCHAR(255)
        """)
        conn.commit()
    except Exception as e:
        print(f"Error updating users table: {e}")
    finally:
        cursor.close()
        conn.close()

# Call this function when your app starts
# Add this near the bottom of your file, before the if __name__ == '__main__': line
update_users_table()

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create users table first
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL
        )
    ''')
    
    # Then create items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(100) NOT NULL,
            description TEXT,
            price DECIMAL(10,2),
            seller_id INT,
            FOREIGN KEY (seller_id) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()


def init_db():
    conn = connect_to_database()
    if conn:
        try:
            cursor = conn.cursor()
            
            # Create users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(255) NOT NULL UNIQUE,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password VARCHAR(255) NOT NULL,
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    profile_picture VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            print("Database initialized successfully")
            
        except Error as e:
            print(f"Error initializing database: {e}")
        finally:
            cursor.close()
            conn.close()

# Initialize the database when the application starts
init_db()
create_items_table()

class StandaloneApplication(BaseApplication):
    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        for key, value in self.options.items():
            if key in self.cfg.settings and value is not None:
                self.cfg.set(key.lower(), value)

    def load(self):
        return self.application

if __name__ == '__main__':
    options = {
        'bind': '0.0.0.0:' + os.environ.get('PORT', '8080'),
        'workers': 4,
        'threads': 4,
        'timeout': 120
    }
    StandaloneApplication(app, options).run()

def connect_to_database():
    try:
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT')),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )
        
        if connection.is_connected():
            print("Successfully connected to database")
            return connection
            
    except Error as e:
        print(f"Error connecting to database: {e}")
        return None

def get_db_connection():
    return connect_to_database()

# Test database connection
def test_connection():
    conn = connect_to_database()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            print("Database query successful")
        except Error as e:
            print(f"Error executing query: {e}")
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
                print("Database connection closed")



