from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from app.db_connect import get_db
from passlib.context import CryptContext

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin', methods=['GET'])
def admin_dashboard():
    user_id = session.get('user_id')
    if not user_id:
        flash("You must be logged in to access this page.", "danger")
        return redirect(url_for('users.login'))

    connection = get_db()

    # Verify if the user is an admin
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM admins WHERE user_id = %s", (user_id,))
        is_admin = cursor.fetchone()

        if not is_admin:
            flash("You are not authorized to access this page.", "danger")
            return redirect(url_for('index'))

        # Handle search query
        query = request.args.get('query', '').strip() if 'query' in request.args else ''
        page = int(request.args.get('page', 1))  # Current page number
        users_per_page = 10  # Users per page
        offset = (page - 1) * users_per_page

        if query:
            search_query = f"%{query}%"
            cursor.execute("""
                SELECT * FROM users WHERE username LIKE %s LIMIT %s OFFSET %s
            """, (search_query, users_per_page, offset))
        else:
            cursor.execute("""
                SELECT * FROM users LIMIT %s OFFSET %s
            """, (users_per_page, offset))

        users = cursor.fetchall()

        # Get total user count for pagination
        if query:
            cursor.execute("SELECT COUNT(*) as total FROM users WHERE username LIKE %s", (search_query,))
        else:
            cursor.execute("SELECT COUNT(*) as total FROM users")
        total_users = cursor.fetchone()['total']

    total_pages = (total_users + users_per_page - 1) // users_per_page

    return render_template('admin/admin.html', users=users, query=query, page=page, total_pages=total_pages)

pwd_context = CryptContext(
    schemes=["scrypt"],
    default="scrypt",
    deprecated="auto",
    scrypt__rounds=15,  # This corresponds to 2^15 = 32768 for "n"
    scrypt__block_size=8,  # Equivalent to Scrypt's "r"
    scrypt__parallelism=1  # Equivalent to Scrypt's "p"
)

@admin_bp.route('/admin/edit/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    user_id_admin = session.get('user_id')
    if not user_id_admin:
        flash("You must be logged in to access this page.", "danger")
        return redirect(url_for('users.login'))

    # Verify if the logged-in user is an admin
    connection = get_db()
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM admins WHERE user_id = %s", (user_id_admin,))
        is_admin = cursor.fetchone()

    if not is_admin:
        flash("You are not authorized to access this page.", "danger")
        return redirect(url_for('index'))

    # Handle form submission
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        new_password = request.form['new_password']

        # Update user information
        with connection.cursor() as cursor:
            if new_password:
                # Hash the new password using scrypt
                hashed_password = pwd_context.hash(new_password)
                cursor.execute("""
                    UPDATE users SET username = %s, email = %s, password = %s WHERE id = %s
                """, (username, email, hashed_password, user_id))
            else:
                cursor.execute("""
                    UPDATE users SET username = %s, email = %s WHERE id = %s
                """, (username, email, user_id))
            connection.commit()
            flash("User information updated successfully!", "success")
            return redirect(url_for('admin.admin_dashboard'))

    # Fetch user details
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for('admin.admin_dashboard'))

    return render_template('admin/edit_user.html', user=user)
