from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from passlib.context import CryptContext
from werkzeug.security import generate_password_hash, check_password_hash
from app.db_connect import get_db

pwd_context = CryptContext(
    schemes=["scrypt"],
    default="scrypt",
    deprecated="auto",
    scrypt__rounds=15,  # Corresponds to 2^15 = 32768 for "n"
    scrypt__block_size=8,  # Equivalent to Scrypt's "r"
    scrypt__parallelism=1  # Equivalent to Scrypt's "p"
)

users = Blueprint('users', __name__)

@users.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']  # Capture the email field
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Validate required fields
        if not username or not email or not password:
            flash("Username, email, and password are required.", "danger")
            return redirect(url_for('users.register'))

        # Check if passwords match
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for('users.register'))

        connection = get_db()

        # Check if the email already exists
        query = "SELECT * FROM users WHERE email = %s"
        with connection.cursor() as cursor:
            cursor.execute(query, (email,))
            user = cursor.fetchone()

        if user:
            flash("Email is already registered. Please use a different email.", "danger")
            return redirect(url_for('users.register'))

        # Check if the username already exists
        query = "SELECT * FROM users WHERE username = %s"
        with connection.cursor() as cursor:
            cursor.execute(query, (username,))
            user = cursor.fetchone()

        if user:
            flash("Username is already taken. Please choose a different username.", "danger")
            return redirect(url_for('users.register'))

        # Hash the password using Passlib
        hashed_password = pwd_context.hash(password)

        # Insert the new user into the database
        query = "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)"
        with connection.cursor() as cursor:
            cursor.execute(query, (username, email, hashed_password))
        connection.commit()

        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for('users.login'))

    return render_template("register.html")


@users.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        connection = get_db()
        query = "SELECT * FROM users WHERE username = %s"
        with connection.cursor() as cursor:
            cursor.execute(query, (username,))
            user = cursor.fetchone()

        if user:
            # Check if the password matches the new Passlib Scrypt hash
            if pwd_context.verify(password, user['password']):
                session['user_id'] = user['id']
                session['username'] = user['username']
                flash("Login successful!", "success")
                return redirect(url_for('index'))
            # Check if the password matches the legacy Werkzeug hash
            elif check_password_hash(user['password'], password):
                # Re-hash the password using Passlib
                new_hashed_password = pwd_context.hash(password)
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE users SET password = %s WHERE id = %s",
                        (new_hashed_password, user['id']),
                    )
                    connection.commit()
                session['user_id'] = user['id']
                session['username'] = user['username']
                flash("Login successful! Your password has been updated to a more secure format.", "success")
                return redirect(url_for('index'))
            else:
                flash("Invalid credentials. Please try again.", "danger")
        else:
            flash("Invalid credentials. Please try again.", "danger")

    return render_template("login.html")

@users.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('users.login'))

@users.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        flash("Please log in to view your profile.", "warning")
        return redirect(url_for('users.login'))

    connection = get_db()
    user_id = session['user_id']
    query = "SELECT * FROM users WHERE id = %s"
    with connection.cursor() as cursor:
        # Fetch user information
        cursor.execute(query, (user_id,))
        user = cursor.fetchone()

        if not user:
            flash("User not found!", "error")
            return redirect(url_for('index'))

        # Handle profile update (POST request)
        if request.method == 'POST':
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            email = request.form.get('email')
            bio = request.form.get('bio')

            update_query = """
                UPDATE users 
                SET first_name = %s, last_name = %s, email = %s, bio = %s 
                WHERE id = %s
            """
            cursor.execute(update_query, (first_name, last_name, email, bio, user_id))
            connection.commit()
            flash("Profile updated successfully!", "success")
            return redirect(url_for('users.profile'))

        # Fetch recipes created by the user
        recipe_query = "SELECT * FROM recipes WHERE user_id = %s"
        recipes = []
        cursor.execute(recipe_query, (user_id,))
        recipes = cursor.fetchall()

    # Determine if in edit mode
    editing = request.args.get('edit') == 'True'

    return render_template(
        "view_profile.html",
        user=user,
        recipes=recipes,
        editing=editing,
        is_current_user=True
    )

@users.route('/profile/<username>', methods=['GET', 'POST'])
def view_profile(username):
    db = get_db()
    user_id = session.get('user_id')  # Get logged-in user ID
    editing = request.args.get('edit') == 'True'  # Check if in edit mode

    with db.cursor() as cursor:
        # Fetch the user being viewed
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if not user:
            flash("User not found!", "error")
            return redirect(url_for('index'))

        # Check if current user is viewing their own profile
        is_current_user = user_id == user['id']

        # Handle POST request for editing
        if request.method == 'POST' and is_current_user:
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            email = request.form.get('email')
            bio = request.form.get('bio')

            cursor.execute("""
                UPDATE users SET first_name = %s, last_name = %s, email = %s, bio = %s WHERE id = %s
            """, (first_name, last_name, email, bio, user_id))
            db.commit()
            flash("Profile updated successfully!", "success")
            return redirect(url_for('users.view_profile', username=username))

        # Fetch recipes by the user
        query = request.args.get('query', '').strip() if 'query' in request.args else ''
        if query:
            cursor.execute("""
                SELECT * FROM recipes WHERE user_id = %s AND title LIKE %s
            """, (user['id'], f"%{query}%"))
        else:
            cursor.execute("""
                SELECT * FROM recipes WHERE user_id = %s
            """, (user['id'],))
        recipes = cursor.fetchall()

    return render_template('view_profile.html', user=user, recipes=recipes, query=query, editing=editing, is_current_user=is_current_user)



