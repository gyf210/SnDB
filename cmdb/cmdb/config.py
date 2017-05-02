# coding=utf-8

import os
from datetime import timedelta

BaseDir = os.path.dirname(os.path.abspath(__file__))


class BaseConfig(object):
    # SERVER_NAME = '192.168.3.50:9000'
    SECRET_KEY = 'E_\t\xe12z\xbd\xa69\xf2x\x9b\xf3\xb9\xa4\xdcH\xd8\x8d}\x9eZ\x1cB'
    REMEMBER_COOKIE_DURATION = timedelta(hours=6)
    SSL_DISABLE = False
    DATABASE_URL = 'mysql+pymysql://root:123456@127.0.0.1/cmdb_new3?charset=utf8'
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True
    SQLALCHEMY_RECORD_QUERIES = True
    FLASKY_SLOW_DB_QUERY_TIME = 0.1
    SQLALCHEMY_TRACK_MODIFICATIONS = True

    MAIL_SERVER = 'smtp.163.com'
    MAIL_PORT = 25
    MAIL_USE_TLS = False
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', '')
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')

    CMDB_CONFIG = 'prod'
    CMDB_ADMIN = ['admin@le.com', ]
    CMDB_OPS = []

    CELERY_BROKER_URL = 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
    CELERY_TASK_SERIALIZER = 'json'

    UPLOADED_AVATARS_DEST = os.path.join(BaseDir, 'static/uploads/avatar/')
    UPLOADED_DATAS_DEST = os.path.join(BaseDir, 'static/uploads/data/')

    DEBUG = True

    @staticmethod
    def init_app(app):
        pass


class ProdConfig(BaseConfig):
    SQLALCHEMY_DATABASE_URI = BaseConfig.DATABASE_URL

    @staticmethod
    def init_app(app):
        BaseConfig.init_app(app)


class DevelopmentConfig(BaseConfig):
    pass


class TestConfig(BaseConfig):
    pass


config = {
    'prod': ProdConfig,
    'development': DevelopmentConfig,
    'test': TestConfig,
    'default': ProdConfig
}
