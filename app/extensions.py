from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail
from celery import Celery

db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
celery = Celery()