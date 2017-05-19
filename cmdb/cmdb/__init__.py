# coding=utf-8

from flask import Flask
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_uploads import UploadSet, configure_uploads, DOCUMENTS, IMAGES
from celery import Celery
from .config import BaseConfig, config

mail = Mail()
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.session_protection = 'strong'
login_manager.login_view = 'auth.login'
datas = UploadSet('datas', DOCUMENTS)
avatars = UploadSet('avatars', IMAGES)
celery = Celery(__name__, broker=BaseConfig.CELERY_BROKER_URL)


@login_manager.user_loader
def load_user(user_id):
    from .models import User
    return User.query.get(int(user_id))


def create_app(config_name):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    mail.init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    configure_uploads(app, datas)
    configure_uploads(app, avatars)

    from .views.home import home as home_blueprint
    app.register_blueprint(home_blueprint)

    from .views.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from .views.account import account as account_blueprint
    app.register_blueprint(account_blueprint, url_prefix='/account')

    from .views.asset import asset as asset_blueprint
    app.register_blueprint(asset_blueprint, url_prefix='/asset')

    from .views.api import api_bp as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api/v1')

    from .views.info import info as info_blueprint
    app.register_blueprint(info_blueprint, url_prefix='/info')

    celery.conf.update(app.config)

    return app
