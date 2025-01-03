from flask import g
from .app_factory import create_app
from .db_connect import close_db, get_db

app = create_app()
app.secret_key = 'your-secret'  # Replace with an environment variable

from app.blueprints.users import users
from app.blueprints.recipes import recipes
from app.blueprints.favorites import favorites
from app.blueprints.admin import admin_bp

app.register_blueprint(admin_bp)
app.register_blueprint(users)
app.register_blueprint(recipes)
app.register_blueprint(favorites)

from . import routes

@app.before_request
def before_request():
    g.db = get_db()

# Setup database connection teardown
@app.teardown_appcontext
def teardown_db(exception=None):
    close_db(exception)