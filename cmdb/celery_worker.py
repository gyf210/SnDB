# coding=utf-8

from cmdb import create_app, celery
from cmdb.config import BaseConfig

app = create_app(BaseConfig.CMDB_CONFIG or 'default')
app.app_context().push()
