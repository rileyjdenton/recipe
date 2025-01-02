from flask import Flask, session
from app.db_connect import get_db

def create_app():
    app = Flask(__name__)

    @app.context_processor
    def inject_admin_status():
        user_id = session.get('user_id')
        if not user_id:
            return {"is_admin": False}

        db = get_db()
        with db.cursor() as cursor:
            cursor.execute("SELECT 1 FROM admins WHERE user_id = %s", (user_id,))
            is_admin = cursor.fetchone() is not None

        return {"is_admin": is_admin}

    return app

