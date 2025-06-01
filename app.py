import os
import datetime # Added import for datetime
import re # For nl2br filter
from markupsafe import Markup, escape # For nl2br filter
from flask import Flask, render_template # render_template for custom error pages
from flask_login import LoginManager
from flask_migrate import Migrate # For database migrations, if you choose to use Flask-Migrate

# from flask_wtf.csrf import CSRFProtect # Import CSRFProtect # CSRF REMOVED

# Import configurations and models
from config import get_config, Config # Use get_config to load appropriate config
from models import db, User, PDFDocument, ChatMessage, Contract, Dilekce, Ifade # Import db instance and User, PDFDocument, ChatMessage, Contract, Dilekce, Ifade models

# Import Blueprints
from main_routes import main_bp
from auth_routes import auth_bp
from dashboard_routes import dashboard_bp
from chat_routes import chat_bp
from contract_routes import contract_bp # Import the new contract blueprint
from dilekce_routes import dilekce_bp # Import the new dilekce blueprint
from ifade_routes import ifade_bp # Import the new ifade blueprint

# Initialize extensions (outside of create_app for global access if needed, or inside)
login_manager = LoginManager()
migrate = Migrate() # Initialize Migrate
# csrf = CSRFProtect() # Initialize CSRFProtect # CSRF REMOVED

def create_app(config_name=None):
    """Flask application factory."""
    # Use instance_relative_config=True so app.instance_path points to project_root/instance
    app = Flask(__name__, instance_relative_config=True)

    # Load configuration
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'default')
    app.config.from_object(get_config()) # Use selected config object

    # Ensure the instance folder exists (Flask standard way)
    # This is where app.db will be created by SQLAlchemy if it's configured to be there.
    # Your SQLALCHEMY_DATABASE_URI in config.py already points to an absolute path
    # project_root/instance/app.db, which is consistent with app.instance_path.
    try:
        if not os.path.exists(app.instance_path):
            os.makedirs(app.instance_path)
            print(f"Created instance folder at: {app.instance_path}")
        else:
            # This print is for confirmation, can be removed in production
            print(f"Instance folder already exists at: {app.instance_path}")
    except OSError as e:
        # Log this error properly in a real application
        print(f"Error creating instance folder {app.instance_path}: {e}")
        # Depending on the app's needs, you might raise the error or handle it.

    # Ensure SQLALCHEMY_DATABASE_URI is an absolute path if it's SQLite
    # This handles cases where DATABASE_URL in .env might be a relative SQLite path.
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI')
    if db_uri and db_uri.startswith('sqlite:///'):
        path_part = db_uri[len('sqlite:///'):]

        # A path is relative if it's not ':memory:' and doesn't start with '/' (for Unix-like/macOS)
        # For Windows, an absolute path would typically start with a drive letter e.g. C:/
        # os.path.isabs() is not directly usable here as path_part is not a pure OS path yet.
        is_relative_to_cwd = path_part != ':memory:' and not path_part.startswith('/')
        if os.name == 'nt': # More specific check for Windows absolute paths
            if len(path_part) > 1 and path_part[1] == ':' and path_part[0].isalpha():
                 is_relative_to_cwd = False # It's like C:/... or C:\...

        if is_relative_to_cwd:
            # Resolve relative path against app.root_path
            # e.g., 'instance/site.db' becomes '/abs/path/to/project/instance/site.db'
            absolute_db_path = os.path.join(app.root_path, path_part)
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + absolute_db_path # Note: 4 slashes for absolute
            print(f"App: Converted relative SQLite URI from .env to absolute: {app.config['SQLALCHEMY_DATABASE_URI']}")
        elif path_part == ':memory:':
            print(f"App: Using SQLite in-memory database: {db_uri}")
        else:
            # Path was already absolute (e.g. sqlite:////path/to/db)
            print(f"App: Using already absolute SQLite URI: {db_uri}")
    elif db_uri:
        # For other database types like PostgreSQL, MySQL, etc.
        print(f"App: Using non-SQLite DATABASE_URL: {db_uri}")


    # Initialize Flask extensions
    db.init_app(app)
    migrate.init_app(app, db) # Initialize Flask-Migrate
    login_manager.init_app(app)
    # csrf.init_app(app) # Initialize CSRFProtect with the app # CSRF REMOVED

    # Configure LoginManager
    login_manager.login_view = 'auth.login' # Blueprint_name.route_function_name
    login_manager.login_message = 'Bu sayfayı görüntülemek için lütfen giriş yapın.'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register Blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth') # Optional: prefix for all auth routes
    app.register_blueprint(dashboard_bp) # Prefix is already in dashboard_bp
    app.register_blueprint(chat_bp)      # Prefix is already in chat_bp
    app.register_blueprint(contract_bp)  # Register the contract blueprint (prefix is in the blueprint)
    app.register_blueprint(dilekce_bp)   # Register the dilekce blueprint (prefix is in the blueprint)
    app.register_blueprint(ifade_bp)     # Register the ifade blueprint (prefix is in the blueprint)

    # Context processors (can also be defined in blueprints if specific)
    @app.context_processor
    def inject_global_vars():
        return dict(
            site_name="EmsalKarar GPT", 
            current_year=datetime.datetime.utcnow().year
        )

    # Custom error handlers (optional)
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html', title="Sayfa Bulunamadı"), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        # Log the error e
        return render_template('errors/500.html', title="Sunucu Hatası"), 500
        
    # Create database tables if they don't exist
    # This is usually handled by migrations in a production app (Flask-Migrate)
    # For simplicity in development, we can create them here.
    with app.app_context():
        # The instance folder should now reliably exist due to the code above
        # and the code in config.py.
        db.create_all() 
        print(f"Database checked/created at: {app.config['SQLALCHEMY_DATABASE_URI']}")
        # You might want to create a default admin user here for first run
        # from auth_routes import create_admin_user # If you have such a helper
        # create_admin_user(app)


    # Shell context for Flask CLI (flask shell)
    @app.shell_context_processor
    def make_shell_context():
        return {'db': db, 'User': User, 'PDFDocument': PDFDocument, 'ChatMessage': ChatMessage, 'Contract': Contract, 'Dilekce': Dilekce, 'Ifade': Ifade}

    # Custom Jinja2 filter for nl2br
    @app.template_filter('nl2br')
    def nl2br_filter(s):
        if s is None:
            return ''
        # Ensure the input is a string and escape it before replacing newlines
        s = str(escape(s))
        return Markup(re.sub(r'\r\n|\r|\n', '<br>\n', s))

    return app

# Create the Flask app instance using the factory
# The FLASK_APP environment variable should point to this file (e.g., app.py)
# The FLASK_ENV environment variable can be 'dev', 'prod', 'test'
flask_app = create_app() # Use default config based on FLASK_ENV or 'default'

if __name__ == '__main__':
    # Run the app
    # The host and port can be configured here or through environment variables
    # Debug mode should be enabled via FLASK_DEBUG=True in .env for DevelopmentConfig
    flask_app.run(host='localhost', port=int(os.environ.get('PORT', 5005)))
