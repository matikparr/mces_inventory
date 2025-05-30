import os
from flask import Flask, render_template,send_from_directory, make_response
from flask_login import LoginManager
from config import DevelopmentConfig, ProductionConfig, Config
from app.services.user_services import UserService
from datetime import datetime
from app.extensions import db, migrate, mail, celery
from dotenv import load_dotenv
from flask_migrate import Migrate
from app.models.user_models import User
from app.models.inventory_models import Inventory
from app.models.category_models import Category
from app.models.borrowing_models import Borrowing
from app.models.logs_models import Logs
from app.models.borrowing_details_model import BorrowingDetails
from app.models.borrowing_status_model import BorrowedItemStatus
from app.models.cart_models import Cart
from app.tasks.apscheduler import start_scheduler

from flask_mail import Mail

def create_app():
    app = Flask(__name__)
    # Load .env file
    load_dotenv()
    
    env = os.getenv('FLASK_ENV', 'development')
    if env == 'production':
        app.config.from_object(ProductionConfig)
    else:
        app.config.from_object(DevelopmentConfig)

    Config.Initialize_database()
    start_scheduler()
    
    # Initialize SQLAlchemy
    db.init_app(app)
    Migrate(app, db)
    mail.init_app(app) 
    
    with app.app_context():
        db.create_all()
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        if 'users' in inspector.get_table_names():
            if UserService.count_admins() == 0:
                UserService.create_default_admin()
                
    # Initialize LoginManager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'  
    login_manager.login_message = "Please log in to access this page."

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
   
    # Register blueprints
    from app.routes import all_blueprints
   
    @app.route('/static/storage/app/<filename>')
    def cached_image(filename):
        """Serve inventory images with caching"""
        upload_folder = Config.UPLOAD_FOLDER 

        if not os.path.exists(os.path.join(upload_folder, filename)):
            return send_from_directory("static/images", "not_available.jpg") 

        response = make_response(send_from_directory(upload_folder, filename))
        response.headers["Cache-Control"] = "public, max-age=31536000" 
        return response
        
    for blueprint in all_blueprints:
        app.register_blueprint(blueprint)
       
  
    # Error handler for 404
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404

    # Error handler for 500 (optional)
    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('500.html'), 500
  
    @app.context_processor
    def inject_now():
        return {'now': datetime.now()}
    return app
