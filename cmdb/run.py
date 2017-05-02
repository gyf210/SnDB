# coding=utf-8

from flask_login import current_user
from flask_migrate import Migrate, MigrateCommand
from flask_script import Manager, Shell
from flask_script.commands import Clean, ShowUrls
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from cmdb import create_app, db
from cmdb.models import Role, User, Idc,  Host, Business, Service, Env, System, HostType, Domain, \
                        Priority, ServiceUser, Depend, ApiUser, PublishIp, PrivateIp, VipIp, ServiceAgent
from cmdb.config import BaseConfig

app = create_app(BaseConfig.CMDB_CONFIG or 'default')
manager = Manager(app)
migrate = Migrate(app, db)
admin = Admin(app)


class CmdbModelView(ModelView):
    can_delete = False
    can_create = False
    can_edit = False
    can_view_details = True
    page_size = 50

    def is_accessible(self):
        return current_user.is_authenticated


for name in [Role, User, Idc,  Host, Business, Service, Env, System, HostType,
             Domain, Priority, ServiceUser, Depend, ApiUser]:
    admin.add_view(CmdbModelView(name, db.session))


@manager.command
def init_env():
    """
        Init Environment Function
    """
    Role.insert_roles()
    HostType.insert_host_types()
    System.insert_systems()
    Env.insert_envs()
    Domain.insert_domains()
    Priority.insert_priorities()
    ServiceUser.insert_service_users()
    Depend.insert_depends()
    Business.insert_businesses()
    ApiUser.insert_api_users()


def make_shell_context():
    return dict(app=app, db=db, Role=Role, User=User, Idc=Idc, Host=Host, Business=Business,
                Service=Service, Env=Env, System=System, HostType=HostType, Domain=Domain, Priority=Priority,
                ServiceUser=ServiceUser, Depend=Depend, ApiUser=ApiUser,
                PublishIp=PublishIp, PrivateIp=PrivateIp, VipIp=VipIp, ServiceAgent=ServiceAgent)

manager.add_command("shell", Shell(make_context=make_shell_context))
manager.add_command('db', MigrateCommand)
manager.add_command('clean', Clean())
manager.add_command('showurls', ShowUrls())


if __name__ == '__main__':
    manager.run()

