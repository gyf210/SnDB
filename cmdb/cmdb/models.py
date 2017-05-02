# coding=utf-8

import datetime
from collections import defaultdict
from funcy import flatten
from flask import current_app
from flask_login import UserMixin, AnonymousUserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from . import db, login_manager
from .utils.changeip import validate_ip
from .utils.createuuid import createuuid


class Permission(object):
    OPERATOR = 0x01     # 普通权限
    ADMINISTER = 0x80   # 管理权限


class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)
    default = db.Column(db.Boolean, default=False, nullable=False)
    permissions = db.Column(db.Integer, nullable=False)
    users = db.relationship('User', backref='role', lazy='dynamic')

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'roles'

    @staticmethod
    def insert_roles():
        roles = {
            'Operator': (Permission.OPERATOR, True),
            'Administrator': (0xff, False)
        }
        for r in roles:
            role = Role.query.filter_by(name=r).first()
            if role is None:
                role = Role(name=r)
            role.permissions = roles[r][0]
            role.default = roles[r][1]
            db.session.add(role)
        db.session.commit()

    def to_json(self):
        return dict(id=self.id, name=self.name, default=self.default, permissions=self.permissions)

    def __repr__(self):
        return '<Role %r>' % self.name


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(32), unique=True, nullable=False)
    phone = db.Column(db.String(11), nullable=False)
    member_since = db.Column(db.DateTime(), default=datetime.datetime.now)
    last_seen = db.Column(db.DateTime(), default=datetime.datetime.now)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    avatar_hash = db.Column(db.String(32), default='9b81ee590d27c91277ce8f36280285e3', nullable=False)
    confirmed = db.Column(db.Boolean, default=False, nullable=False)
    status = db.Column(db.Boolean, default=True, nullable=False)

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'users'

    def __repr__(self):
        return '<User %r>' % self.name

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if self.role is None:
            if self.email in current_app.config['CMDB_ADMIN']:
                self.role = Role.query.filter_by(permissions=0xff).first()
            if self.role is None:
                self.role = Role.query.filter_by(default=True).first()

    def can(self, permissions):
        return self.role is not None and (self.role.permissions & permissions) == permissions

    def is_administrator(self):
        return self.can(Permission.ADMINISTER)

    def to_json(self):
        member_since = self.member_since.strftime('%Y-%m-%d %H:%M:%S')
        last_seen = self.last_seen.strftime('%Y-%m-%d %H:%M:%S')
        role_name = self.role.name
        return dict(id=self.id, name=self.name, email=self.email, role_name=role_name, role_id=self.role_id,
                    phone=self.phone, member_since=member_since, last_seen=last_seen, status=self.status)

    def ping(self):
        self.last_seen = datetime.datetime.now()
        db.session.add(self)

    @property
    def password(self):
        raise AttributeError('password is not reading')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_user_token(self, expiration=3600):
        s = Serializer(current_app.config['SECRET_KEY'], expiration)
        return s.dumps({'id': self.id})

    def confirm(self, token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except:
            return False
        if data.get('id') != self.id:
            return False
        self.confirmed = True
        db.session.add(self)
        db.session.commit()
        return True

    def reset_password(self, token, new_password):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except:
            return False
        if data.get('id') != self.id:
            return False
        self.password = new_password
        db.session.add(self)
        db.session.commit()
        return True

    @staticmethod
    def validate_register(form):
        error = []
        if form.get('name', '').strip() == '':
            error.append('用户为空')
        if not form.get('name', '').isalnum():
            error.append('用户必须由数字或字母组成')
        if len(form.get('name', '')) > 128:
            error.append('用户长度超过128位')
        _user = User.query.filter_by(name=form.get('name')).first()
        if _user:
            error.append('用户已使用')
        if form.get('password', '').strip() == '':
            error.append('密码为空')
        if len(form.get('password', '')) < 6:
            error.append('密码长度小于6位')
        if form.get('password2', '').strip() == '':
            error.append('确认密码为空')
        if len(form.get('password2', '')) < 6:
            error.append('确认密码长度小于6位')
        if form.get('password') != form.get('password2'):
            error.append('密码前后不匹配')
        if form.get('email', '').strip() == '':
            error.append('邮箱为空')
        if len(form.get('email', '')) > 64:
            error.append('邮箱长度超过64位')
        _user = User.query.filter_by(email=form.get('email')).first()
        if _user:
            error.append('邮箱已注册')
        if form.get('phone', '').strip() == '':
            error.append('电话为空')
        if len(form.get('phone', '')) > 11:
            error.append('电话长度超过11位')
        if error:
            return False, '\n'.join(error)
        return True, ''

    @staticmethod
    def validate_update_password(form):
        error = []
        if form.get('password_old', '').strip() == '':
            error.append('老密码为空')
        if not current_user.verify_password(form.get('password_old', '')):
            error.append('老密码错误')
        if form.get('password_new', '').strip() == '':
            error.append('新密码为空')
        if len(form.get('password_new', '')) < 6:
            error.append('新密码长度小于6位')
        if form.get('password_old') == form.get('password_new'):
            error.append('新老密码不匹配')
        if form.get('password_repeat_new', '').strip() == '':
            error.append('确认密码为空')
        if form.get('password_new') != form.get('password_repeat_new'):
            error.append('新密码前后输入不匹配')
        if error:
            return False, '\n'.join(error)
        return True, ''

    @staticmethod
    def validate_reset_password(form):
        error = []
        if form.get('email', '').strip() == '':
            error.append('邮箱为空')
        _user = User.query.filter_by(email=form.get('email')).first()
        if not _user:
            error.append('邮箱不存在')
        if form.get('password', '').strip() == '':
            error.append('密码为空')
        if len(form.get('password', '')) < 6:
            error.append('密码长度小于6位')
        if form.get('password2', '').strip() == '':
            error.append('确认密码为空')
        if form.get('password') != form.get('password2'):
            error.append('密码前后输入不匹配')
        if error:
            return False, '\n'.join(error)
        return True, ''

    @staticmethod
    def validate_modify(form):
        error = []
        if form.get('id', '').strip() == '':
            error.append('用户ID为空')
        _user = User.query.filter_by(id=form.get('id', type=int)).first()
        if not _user:
            error.append('用户ID不存在')
        if len(form.get('phone', '')) > 11:
            error.append('电话长度超过11位')
        if error:
            return False, '\n'.join(error)
        return True, ''

    @staticmethod
    def validate_create(form):
        error = []
        if form.get('name', '').strip() == '':
            error.append('用户为空')
        _user = User.query.filter_by(name=form.get('name')).first()
        if _user:
            error.append('用户已存在')
        if form.get('password', '').strip() == '':
            error.append('密码为空')
        if len(form.get('password')) < 6:
            error.append('密码长度小于6位')
        if form.get('email', '').strip() == '':
            error.append('邮箱为空')
        _user = User.query.filter_by(email=form.get('email')).first()
        if _user:
            error.append('邮箱已注册')
        if len(form.get('phone', '')) > 11:
            error.append('电话长度超过11位')
        if error:
            return False, '\n'.join(error)
        return True, ''


class AnonymousUser(AnonymousUserMixin):

    def can(self, permissions):
        return False

    def is_administrator(self):
        return False

login_manager.anonymous_user = AnonymousUser


class Idc(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    operator = db.Column(db.Integer, default=False, nullable=False)
    comment = db.Column(db.Text, default='', nullable=False)
    create_time = db.Column(db.DateTime(), default=datetime.datetime.now)
    change_time = db.Column(db.DateTime(), default=datetime.datetime.now, onupdate=datetime.datetime.now, index=True)
    hosts = db.relationship('Host', backref='idc', lazy='dynamic')

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'idcs'

    def __repr__(self):
        return '<Idc %r>' % self.name

    def to_json(self):
        return dict(id=self.id, name=self.name, operator=self.operator, comment=self.comment)

    @staticmethod
    def validate_idc(form, modify_flag=True):
        error = []
        if modify_flag:
            if form.get('id', '').strip() == '':
                error.append('机房ID为空')
            else:
                if not Idc.query.get(form.get('id', type=int)):
                    error.append('机房ID不存在')
        if form.get('name', '').strip() == '':
            error.append('机房名称为空')
        else:
            _idc = Idc.query.filter_by(name=form.get('name')).first()
            if _idc:
                if modify_flag:
                    if _idc.id != form.get('id', type=int):
                        error.append('机房名称已使用')
                else:
                    error.append('机房名称已使用')
        if form.get('operator', '').strip() == '':
            error.append('运营商为空')
        if error:
            return False, '\n'.join(error)
        return True, ''


class PrivateIp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(15), unique=True, nullable=False)
    host_id = db.Column(db.Integer, db.ForeignKey('hosts.id'))

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'private_ips'

    def __repr__(self):
        return '<PrivateIp %r>' % self.ip


class PublishIp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(15), unique=True, nullable=False)
    host_id = db.Column(db.Integer, db.ForeignKey('hosts.id'))

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'publish_ips'

    def __repr__(self):
        return '<PublishIp %r>' % self.ip


class VipIp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(15), unique=True, nullable=False)

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'vip_ips'

    def __repr__(self):
        return '<VipIp %r>' % self.ip


host_vip_ip = db.Table('host_vip_ip',
                       db.Column('host_id', db.Integer, db.ForeignKey('hosts.id'), primary_key=True),
                       db.Column('vip_ip_id', db.Integer, db.ForeignKey('vip_ips.id'), primary_key=True))


class Host(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    cpu = db.Column(db.String(128), default='4C', nullable=False)
    memory = db.Column(db.String(128), default='8G', nullable=False)
    disk = db.Column(db.String(128), default='200G', nullable=False)
    host_ip = db.Column(db.String(15), default='', nullable=False)
    idc_id = db.Column(db.Integer, db.ForeignKey('idcs.id'))
    host_type_id = db.Column(db.Integer, db.ForeignKey('host_types.id'))
    system_id = db.Column(db.Integer, db.ForeignKey('systems.id'))
    env_id = db.Column(db.Integer, db.ForeignKey('envs.id'))
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'))
    status = db.Column(db.Integer, default=False, nullable=False)
    comment = db.Column(db.Text, default='', nullable=False)
    owner = db.Column(db.String(128), default='', nullable=False)
    create_time = db.Column(db.DateTime(), default=datetime.datetime.now)
    change_time = db.Column(db.DateTime(), default=datetime.datetime.now, onupdate=datetime.datetime.now, index=True)
    private_ips = db.relationship('PrivateIp', backref='host', lazy='dynamic', cascade='all,delete-orphan')
    publish_ips = db.relationship('PublishIp', backref='host', lazy='dynamic', cascade='all,delete-orphan')
    vip_ips = db.relationship('VipIp', secondary=host_vip_ip,
                              backref=db.backref('hosts', lazy='dynamic'), lazy='dynamic')

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'hosts'

    def __repr__(self):
        return '<Host %r>' % self.name

    def to_json(self):
        private_ip = list(flatten(self.private_ips.values(PrivateIp.ip)))
        publish_ip = list(flatten(self.publish_ips.values(PublishIp.ip)))
        vip_ip = list(flatten(self.vip_ips.values(VipIp.ip)))
        if self.idc_id:
            idc, idc_id = self.idc.name, self.idc_id
        else:
            idc, idc_id = '', ''
        if self.host_type_id:
            host_type, host_type_id = self.host_type.name, self.host_type_id
        else:
            host_type, host_type_id = '', ''
        if self.system_id:
            system, system_id = self.system.name, self.system_id
        else:
            system, system_id = '', ''
        if self.env_id:
            env, env_id = self.env.name, self.env_id
        else:
            env, env_id = '', ''
        if self.business_id:
            business, business_id = self.business.name, self.business_id
        else:
            business, business_id = '', ''
        return dict(id=self.id, name=self.name, cpu=self.cpu, memory=self.memory, disk=self.disk,
                    host_ip=self.host_ip, idc=idc, idc_id=idc_id, host_type=host_type, host_type_id=host_type_id, 
                    system=system, system_id=system_id, env=env, env_id=env_id, owner=self.owner,
                    status=self.status, comment=self.comment, publish_ip=publish_ip, private_ip=private_ip, 
                    vip_ip=vip_ip, business_id=business_id, business=business)

    @staticmethod
    def validate_auto_check_ip(ips):
        _ok_list, _error_list, _error_repeat_list = [], [], []
        for ip in ips:
            _ret, _number = validate_ip(ip)
            if _ret:
                if _number == 1:
                    if PrivateIp.query.filter_by(ip=ip).first():
                        _error_repeat_list.append(ip)
                        continue
                else:
                    if PublishIp.query.filter_by(ip=ip).first():
                        _error_repeat_list.append(ip)
                        continue
                if VipIp.query.filter_by(ip=ip).first():
                    _error_repeat_list.append(ip)
                    continue
                if Host.query.filter_by(host_ip=ip).first():
                    _error_repeat_list.append(ip)
                    continue
                _ok_list.append(ip)
            else:
                _error_list.append(ip)
        return _ok_list, _error_list, _error_repeat_list

    @staticmethod
    def validate_check_ip(form, modify_flag=True):
        _errors, _error_list, _error_repeat_list = [], [], []
        _tmp_dict = defaultdict(int)
        private_ip = set(form.get('private_ip', '').split())
        publish_ip = set(form.get('publish_ip', '').split())
        vip_ip = set(form.get('vip_ip', '').split())
        host_ip = set(form.get('host_ip', '').split())
        if private_ip:
            for _ip in private_ip:
                _ret, _number = validate_ip(_ip)
                if _ret and _number == 1:
                    _tmp_dict[_ip] += 1
                else:
                    _error_list.append(_ip)
        else:
            _errors.append('内网IP为空')
        if publish_ip:
            for _ip in publish_ip:
                _ret, _number = validate_ip(_ip)
                if _ret and _number == 2:
                    _tmp_dict[_ip] += 1
                else:
                    _error_list.append(_ip)
        if vip_ip:
            for _ip in vip_ip:
                _ret, _number = validate_ip(_ip)
                if _ret:
                    _tmp_dict[_ip] += 1
                else:
                    _error_list.append(_ip)
        if host_ip:
            for _ip in host_ip:
                _ret, _number = validate_ip(_ip)
                if _ret:
                    _tmp_dict[_ip] += 1
                else:
                    _error_list.append(_ip)
        for key, value in _tmp_dict.items():
            if value > 1:
                _error_repeat_list.append(key)
            else:
                _publish_ip = PublishIp.query.filter_by(ip=key).first()
                _private_ip = PrivateIp.query.filter_by(ip=key).first()
                _vip_ip = VipIp.query.filter_by(ip=key).first()
                _host_ip = Host.query.filter_by(host_ip=key).first()
                if _publish_ip:
                    if modify_flag:
                        if _publish_ip.host_id == form.get('id', type=int):
                            continue
                    _error_repeat_list.append(key)
                elif _private_ip:
                    if modify_flag:
                        if _private_ip.host_id == form.get('id', type=int):
                            continue
                    _error_repeat_list.append(key)
                elif _vip_ip:
                    if key in vip_ip:
                        continue
                    _error_repeat_list.append(key)
                elif _host_ip:
                    if key in host_ip:
                        continue
                    _error_repeat_list.append(key)

        if _error_list:
            _errors.append('错误IP:{}'.format(', '.join(set(_error_list))))
        if _error_repeat_list:
            _errors.append('重复IP:{}'.format(', '.join(set(_error_repeat_list))))
        if _errors:
            return False, '\n'.join(_errors)
        return True, ''
    
    @staticmethod
    def manual_batch_create_host(publish_ip_list, private_ip_list, business_id):
        result_host_list, result_publish_ip_list, result_private_ip_list = [], [], []
        items = dict(host_type_id=HostType.query.filter_by(name='虚拟机').first().id,
                     env_id=Env.query.filter_by(name='生产环境').first().id, business_id=business_id)
        if publish_ip_list:
            for _ip in publish_ip_list:
                _publish_ip = PublishIp.query.filter_by(ip=_ip).first()
                if not _publish_ip:
                    _publish_ip = PublishIp(ip=_ip)
                    db.session.add(_publish_ip)
                    items['name'] = createuuid()
                    _host = Host(**items)
                    _host.publish_ips.append(_publish_ip)
                    db.session.add(_host)
                    result_host_list.append(_host)
                else:
                    result_host_list.append(_publish_ip.host)
                result_publish_ip_list.append(_publish_ip)
        if private_ip_list:
            for _ip in private_ip_list:
                _private_ip = PrivateIp.query.filter_by(ip=_ip).first()
                if not _private_ip:
                    _private_ip = PrivateIp(ip=_ip)
                    db.session.add(_private_ip)
                    items['name'] = createuuid()
                    _host = Host(**items)
                    _host.private_ips.append(_private_ip)
                    db.session.add(_host)
                    result_host_list.append(_host)
                else:
                    result_host_list.append(_private_ip.host)
                result_private_ip_list.append(_private_ip)
        db.session.commit()
        return result_host_list, result_publish_ip_list, result_private_ip_list 

    @staticmethod
    def batch_create_host(data_list):
        result_list = []
        for data in data_list:
            """主机SN"""
            name = data.get('sn', '').strip()
            if not name:
                continue
            """主机cpu, memory, disk"""
            cpu, memory, disk = '未知', '未知', '未知'
            try:
                for value in data.get('hardware', '').get('delivered', ''):
                    if value:
                        _type = value.get('type', '')
                        _value = value.get('optionvalue', '未知').strip()
                        if _type.lower() == 'cpu':
                            cpu = _value
                        elif _type == '内存':
                            memory = _value
                        elif _type == '硬盘':
                            disk = _value
            except:
                pass
            """主机内网IP, 公网IP, 虚IP"""
            private_ip_list, publish_ip_list, vip_ip_list = [], [], []
            for value in data.get('machineip', ''):
                if value:
                    _iptype = value.get('iptype', '')
                    _ipvalue = value.get('ip', [])
                    if _iptype == 'inip':
                        private_ip_list.append(_ipvalue)
                    elif _iptype == 'outip':
                        publish_ip_list.append(_ipvalue)
                    elif _iptype == 'vip':
                        vip_ip_list.append(_ipvalue)
            """主机类型"""
            host_ip = ''
            host_type_id = HostType.query.filter_by(name='未知').first().id
            try:
                if data.get('assettype', '').get('name', '') == '公司实体资产':
                    host_type_id = HostType.query.filter_by(name='物理机').first().id
                else:
                    host_ip = data.get('storeIp', '').strip()
                    host_type_id = HostType.query.filter_by(name='虚拟机').first().id
            except:
                pass
            """主机所属IDC"""
            idcroomadd = data.get('idcroomadd', '')
            idcroom = data.get('idcroom', '')
            if idcroomadd and idcroomadd.get('name', ''):
                _idc_name = data['idcroomadd']['name'] 
            else:
                if idcroom and idcroom.get('name', ''):
                    _idc_name = data['idcroom']['name']
            _idc = Idc.query.filter_by(name=_idc_name.strip()).first()
            if not _idc:
                if '电信' in _idc_name:
                    _operator = 0
                elif '联通' in _idc_name:
                    _operator = 1
                else:
                    _operator = 2
                _idc = Idc(name=_idc_name.strip(), operator=_operator)
                db.session.add(_idc)
                db.session.commit()
            idc_id = _idc.id
            """主机操作系统"""
            _system_name = '未知'
            try:
                _system_name = data.get('virtualmachine', '')[0]['name'].strip()
            except:
                pass
            finally:
                _system = System.query.filter_by(name=_system_name).first()
                if not _system:
                    _system = System(name=_system_name)
                    db.session.add(_system)
                    db.session.commit()
                system_id = _system.id
            """主机所属环境"""
            env_id = Env.query.filter_by(name='生产环境').first().id
            """主机状态"""
            status = 1
            try:
                if data.get('state', '').get('name', '') == '使用中':
                    status = 0
            except:
                status = 2
            """主机备注"""
            comment = ''
            try:
                if data.get('bussiness', '')[0]['name'].strip():
                    comment = data['bussiness'][0]['name'].strip()
            except:
                pass
            """主机属主"""
            owner_list = []
            for _owner in data.get('owner', ''):
                if _owner:
                    _name = _owner.get('name', '')
                    owner_list.append(_name)
            message_dict = dict(name=name, cpu=cpu, memory=memory, disk=disk,
                                publish_ip=publish_ip_list, private_ip=private_ip_list, vip_ip=vip_ip_list,
                                host_ip=host_ip, host_type_id=host_type_id, idc_id=idc_id, system_id=system_id,
                                env_id=env_id, status=status, comment=comment, owner=','.join(owner_list))
            result_list.append(message_dict)
        return result_list

    @staticmethod
    def validate_host(form, modify_flag=True):
        error = []
        if modify_flag:
            if form.get('id', '').strip() == '':
                error.append('主机ID为空')
            else:
                _host = Host.query.get(form.get('id', type=int))
                if not _host:
                    error.append('主机ID不存在')
        if form.get('idc_id', '').strip() == '':
            error.append('所属机房为空')
        if form.get('host_type_id', '').strip() == '':
            error.append('主机类型为空')
        if form.get('system_id', '').strip() == '':
            error.append('操作系统为空')
        if form.get('cpu', '').strip() == '':
            error.append('CPU为空')
        if form.get('memory', '').strip() == '':
            error.append('内存为空')
        if form.get('disk', '').strip() == '':
            error.append('DISK为空')
        _ret, _error = Host.validate_check_ip(form, modify_flag)
        if _error:
            error.append(_error)
        if form.get('business_id', '').strip() == '':
            error.append('所属产品为空')
        if form.get('env_id', '').strip() == '':
            error.append('所属环境为空')
        if form.get('status', '').strip() == '':
            error.append('主机状态为空')
        if error:
            return False, '\n'.join(error)
        return True, ''


class Business(db.Model):
    id = db.Column(db.Integer, index=True, primary_key=True)
    pid = db.Column(db.Integer, index=True)
    name = db.Column(db.String(128), default='', nullable=False)
    type = db.Column(db.Integer)
    product = db.Column(db.String(128), default='', nullable=False)
    contact = db.Column(db.Text, default='', nullable=False)
    comment = db.Column(db.Text, default='', nullable=False)
    create_time = db.Column(db.DateTime(), default=datetime.datetime.now)
    change_time = db.Column(db.DateTime(), default=datetime.datetime.now, onupdate=datetime.datetime.now, index=True)
    services = db.relationship('Service', backref='business', lazy='dynamic')
    hosts = db.relationship('Host', backref='business', lazy='dynamic')

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'businesses'

    def __repr__(self):
        return '<Business %r>' % self.name

    def to_json(self):
        if self.product:
            product = Business.query.get(int(self.product.split(',')[1])).name
        else:
            product = ''
        return dict(id=self.id, pid=self.pid, name=self.name, contact=self.contact,
                    comment=self.comment, product=product)

    @staticmethod
    def insert_businesses():
        businesses = [
            {'id': 1, 'name': 'ROOT', 'pid': 0, 'type': 0, 'product': '0'},
            {'name': '乐视云', 'pid': 1, 'type': 1, 'product': '1'},
            {'name': '乐视网', 'pid': 1, 'type': 1, 'product': '1'},
        ]
        for r in businesses:
            result = Business.query.filter_by(name=r['name']).first()
            if result is None:
                result = Business(**r)
                db.session.add(result)
                db.session.commit()

    def create_product_type(self, pid):
        _parent_business = Business.query.get(int(pid))
        if _parent_business.name == 'ROOT':
            return pid, _parent_business.type + 1
        else:
            return '{},{}'.format(_parent_business.product, pid), _parent_business.type + 1

    @staticmethod
    def choice_business_list(start_type_id, end_type_id):
        _result = []
        for _business in Business.query.filter(Business.type > start_type_id, Business.type < end_type_id):
            _tmp_list = _business.product.split(',')
            _tmp_list.pop(0)
            _tmp_list.append(str(_business.id))
            _result.append({'id': _business.id, 'name': '__'.join(
                [Business.query.get(int(_id)).name for _id in _tmp_list])})
        return _result

    @staticmethod
    def validate_business(form, modify_flag=True):
        error = []
        if modify_flag:
            if form.get('id', '').strip() == '':
                error.append('产品ID为空')
            else:
                _business = Business.query.get(int(form.get('id', -1)))
                if not _business:
                    error.append('产品ID不存在')
        if form.get('pid', '').strip() == '':
            error.append('所属产品线为空')
        if form.get('name', '').strip() == '':
            error.append('产品名称为空')
        else:
            _business = Business.query.filter_by(name=form.get('name', ''),
                                                 pid=form.get('pid', -1)).first()
            if _business:
                if modify_flag:
                    if _business.id != int(form.get('id', -1)):
                        error.append('产品已存在')
                else:
                    error.append('产品已存在')
        if error:
            return False, '\n'.join(error)
        return True, ''

    @staticmethod
    def validate_tree_business(form, pid):
        error = []
        if form.get('id', '').strip() == '':
            error.append('产品ID为空')
        else:
            _business = Business.query.get(int(form.get('id', -1)))
            if not _business:
                error.append('产品ID不存在')
        if form.get('name', '').strip() == '':
            error.append('产品名称为空')
        else:
            _business = Business.query.filter_by(name=form.get('name'),pid=pid).first()
            if _business:
                if _business.id != int(form.get('id')):
                    error.append('产品已存在')
        if error:
            return False, '\n'.join(error)
        return True, ''
        

class HostType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    comment = db.Column(db.Text, default='', nullable=False)
    hosts = db.relationship('Host', backref='host_type', lazy='dynamic')

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'host_types'

    def __repr__(self):
        return '<HostType %r>' % self.name

    def to_json(self):
        return dict(id=self.id, name=self.name, comment=self.comment)

    @staticmethod
    def insert_host_types():
        host_types = [
            {'name': '物理机', 'comment': ''},
            {'name': '虚拟机', 'comment': ''},
            {'name': '未知', 'comment': ''},
        ]
        for r in host_types:
            result = HostType.query.filter_by(name=r['name']).first()
            if result is None:
                result = HostType(name=r['name'])
            result.comment = r['comment']
            db.session.add(result)
        db.session.commit()


class System(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    comment = db.Column(db.Text, default='', nullable=False)
    hosts = db.relationship('Host', backref='system', lazy='dynamic')

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'systems'

    def __repr__(self):
        return '<System %r>' % self.name

    def to_json(self):
        return dict(id=self.id, name=self.name, comment=self.comment)

    @staticmethod
    def insert_systems():
        systems = [
            {'name': 'CentOS 6.0', 'comment':  ''},
            {'name': 'CentOS 6.3', 'comment':  ''},
            {'name': 'CentOS 6.5', 'comment':  ''},
            {'name': 'CentOS 6.6', 'comment':  ''},
            {'name': 'CentOS 6.7', 'comment':  ''},
            {'name': 'LetvOS 6.6', 'comment':  ''},
            {'name': '未知', 'comment':  ''},
        ]
        for r in systems:
            result = System.query.filter_by(name=r['name']).first()
            if result is None:
                result = System(name=r['name'])
            result.comment = r['comment']
            db.session.add(result)
        db.session.commit()


class Env(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    comment = db.Column(db.Text, default='', nullable=False)
    hosts = db.relationship('Host', backref='env', lazy='dynamic')

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'envs'

    def __repr__(self):
        return '<Env %r>' % self.name

    def to_json(self):
        return dict(id=self.id, name=self.name, comment=self.comment)

    @staticmethod
    def insert_envs():
        envs = [
            {'name': '生产环境', 'comment': ''},
            {'name': '测试环境', 'comment': ''},
            {'name': '预发环境', 'comment': ''},
        ]
        for r in envs:
            result = Env.query.filter_by(name=r['name']).first()
            if result is None:
                result = Env(name=r['name'])
            result.comment = r['comment']
            db.session.add(result)
        db.session.commit()


class Domain(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    comment = db.Column(db.Text, default='', nullable=False)

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'domains'

    def __repr__(self):
        return '<Domain %r>' % self.name

    def to_json(self):
        return dict(id=self.id, name=self.name, comment=self.comment)

    @staticmethod
    def insert_domains():
        domains = [
            {'name': 'play.api.live.lecloud.com', 'comment': ''},
        ]
        for r in domains:
            result = Domain.query.filter_by(name=r['name']).first()
            if result is None:
                result = Domain(name=r['name'])
            result.comment = r['comment']
            db.session.add(result)
        db.session.commit()


class Priority(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    comment = db.Column(db.Text, default='', nullable=False)
    services = db.relationship('Service', backref='priority', lazy='dynamic')

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'priorities'

    def __repr__(self):
        return '<Priority %r>' % self.name

    def to_json(self):
        return dict(id=self.id, name=self.name, comment=self.comment)

    @staticmethod
    def insert_priorities():
        priorities = [
            {'name': '高', 'comment': ''},
            {'name': '中', 'comment': ''},
            {'name': '低', 'comment': ''},
        ]
        for r in priorities:
            result = Priority.query.filter_by(name=r['name']).first()
            if result is None:
                result = Priority(name=r['name'])
            result.comment = r['comment']
            db.session.add(result)
        db.session.commit()


class ServiceUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    comment = db.Column(db.Text, default='', nullable=False)
    services = db.relationship('Service', backref='user', lazy='dynamic')

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'serviceusers'

    def __repr__(self):
        return '<ServiceUser %r>' % self.name

    def to_json(self):
        return dict(id=self.id, name=self.name, comment=self.comment)

    @staticmethod
    def insert_service_users():
        users = [
            {'name': 'root', 'comment': ''},
            {'name': 'leworker', 'comment': ''},
            {'name': '未知', 'comment': ''},
        ]
        for r in users:
            result = ServiceUser.query.filter_by(name=r['name']).first()
            if result is None:
                result = ServiceUser(name=r['name'])
            result.comment = r['comment']
            db.session.add(result)
        db.session.commit()


class Depend(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    comment = db.Column(db.Text, default='', nullable=False)

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'depends'

    def __repr__(self):
        return '<Depend %r>' % self.name

    def to_json(self):
        return dict(id=self.id, name=self.name, comment=self.comment)

    @staticmethod
    def insert_depends():
        depends = [
            {'name': 'gbalancer', 'comment': ''},
            {'name': 'gluster', 'comment': ''},
            {'name': 'cbase', 'comment': ''},
            {'name': 'jdk6', 'comment': ''},
            {'name': 'jdk7', 'comment': ''},
            {'name': 'jdk8', 'comment': ''},
            {'name': 'tomcat6', 'comment': ''},
            {'name': 'tomcat7', 'comment': ''},
            {'name': 'tomcat8', 'comment': ''},
            {'name': 'resin', 'comment': ''},
            {'name': 'redis', 'comment': ''},
            {'name': 'memcached', 'comment': ''},
        ]
        for r in depends:
            result = Depend.query.filter_by(name=r['name']).first()
            if result is None:
                result = Depend(name=r['name'])
            result.comment = r['comment']
            db.session.add(result)
        db.session.commit()


class ApiUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    status = db.Column(db.Boolean, default=False, nullable=False)
    comment = db.Column(db.Text, default='', nullable=False)

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'apiusers'

    def __repr__(self):
        return '<ApiUser %r>' % self.name

    @staticmethod
    def insert_api_users():
        apiusers = [
            {'name': 'leworker'},
        ]
        for r in apiusers:
            result = ApiUser.query.filter_by(name=r['name']).first()
            if result is None:
                result = ApiUser(name=r['name'])
                result.password = '123456'
                db.session.add(result)
                db.session.commit()

    @property
    def password(self):
        raise AttributeError('password is not reading')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_api_token(self, expiration=315360000):
        s = Serializer(current_app.config['SECRET_KEY'], expiration)
        return s.dumps({'id': self.id})

    @staticmethod
    def verify_api_token(token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
            _user = ApiUser.query.get(data['id'])
            if _user.status == 0:
                return True
        except:
            return False
        return False


service_host = db.Table('service_host',
                        db.Column('host_id', db.Integer, db.ForeignKey('hosts.id'), primary_key=True),
                        db.Column('service_id', db.Integer, db.ForeignKey('services.id'), primary_key=True)
                        )


service_private_ip = db.Table('service_private_ip',
                              db.Column('private_ip_id', db.Integer, db.ForeignKey('private_ips.id'), primary_key=True),
                              db.Column('service_id', db.Integer, db.ForeignKey('services.id'), primary_key=True)
                              )


service_publish_ip = db.Table('service_publish_ip',
                              db.Column('publish_ip_id', db.Integer, db.ForeignKey('publish_ips.id'), primary_key=True),
                              db.Column('service_id', db.Integer, db.ForeignKey('services.id'), primary_key=True)
                              )


service_domain = db.Table('service_domain',
                          db.Column('domain_id', db.Integer, db.ForeignKey('domains.id'), primary_key=True),
                          db.Column('service_id', db.Integer, db.ForeignKey('services.id'), primary_key=True)
                          )


service_depend = db.Table('service_depend',
                          db.Column('depend_id', db.Integer, db.ForeignKey('depends.id'), primary_key=True),
                          db.Column('service_id', db.Integer, db.ForeignKey('services.id'), primary_key=True)
                          )


class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), default='', nullable=False)
    name_alias = db.Column(db.String(128), default='', nullable=False)
    port = db.Column(db.String(5), default='',  nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'))
    priority_id = db.Column(db.Integer, db.ForeignKey('priorities.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('serviceusers.id'))
    contact = db.Column(db.Text, default='', nullable=False)
    contact_email = db.Column(db.Text, default='', nullable=False) 
    status = db.Column(db.Integer, default=False, nullable=False)
    comment = db.Column(db.Text, default='', nullable=False)
    db_instance = db.Column(db.String(128), default='', nullable=False)
    create_time = db.Column(db.DateTime(), default=datetime.datetime.now)
    change_time = db.Column(db.DateTime(), default=datetime.datetime.now, onupdate=datetime.datetime.now, index=True)
    hosts = db.relationship('Host', secondary=service_host,
                            backref=db.backref('services', lazy='dynamic'), lazy='dynamic')
    private_ips = db.relationship('PrivateIp', secondary=service_private_ip,
                                  backref=db.backref('services', lazy='dynamic'), lazy='dynamic')
    publish_ips = db.relationship('PublishIp', secondary=service_publish_ip,
                                  backref=db.backref('services', lazy='dynamic'), lazy='dynamic')
    domains = db.relationship('Domain', secondary=service_domain,
                              backref=db.backref('services', lazy='dynamic'), lazy='dynamic')
    depends = db.relationship('Depend', secondary=service_depend,
                              backref=db.backref('services', lazy='dynamic'), lazy='dynamic')

    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'services'

    def __repr__(self):
        return '<Service %r>' % self.name

    def to_json(self):
        private_ip = list(flatten(self.private_ips.values(PrivateIp.ip)))
        publish_ip = list(flatten(self.publish_ips.values(PublishIp.ip)))
        domain = list(flatten(self.domains.values(Domain.name)))
        depend = list(flatten(self.depends.values(Depend.name)))
        return dict(id=self.id, name=self.name, name_alias=self.name_alias, port=self.port,
                    business_id=self.business_id, business=self.business.name,
                    priority=self.priority.name, priority_id=self.priority_id,
                    user=self.user.name, user_id=self.user_id,
                    db_instance=self.db_instance.split(), contact=self.contact.split(),
                    contact_email=self.contact_email.split(), status=self.status, comment=self.comment,
                    private_ip=private_ip, publish_ip=publish_ip, depend=depend, domain=domain)

    def to_modify_json(self):
        private_ip = list(self.private_ips.values(PrivateIp.id, PrivateIp.ip))
        publish_ip = list(self.publish_ips.values(PublishIp.id, PublishIp.ip))
        depend = list(self.depends.values(Depend.id, Depend.name))
        domain = list(self.domains.values(Domain.id, Domain.name))
        publish_ip_excluded, private_ip_excluded, depend_excluded, domain_excluded = self.excluded_service()
        return dict(id=self.id, name=self.name, name_alias=self.name_alias, port=self.port,
                    business_id=self.business_id, business=self.business.name,
                    priority=self.priority.name, priority_id=self.priority_id,
                    user=self.user.name, user_id=self.user_id, 
                    contact=self.contact.split(), db_instance=self.db_instance.split(),
                    contact_email=self.contact_email.split(), status=self.status, comment=self.comment,
                    private_ip=private_ip, publish_ip=publish_ip, depend=depend, domain=domain,
                    publish_ip_excluded=publish_ip_excluded, private_ip_excluded=private_ip_excluded,
                    depend_excluded=depend_excluded, domain_excluded=domain_excluded)

    def excluded_service(self):
        publish_ip_total_set = set(PublishIp.query.values(PublishIp.id, PublishIp.ip))
        private_ip_total_set = set(PrivateIp.query.values(PrivateIp.id, PrivateIp.ip))
        depend_total_set = set(Depend.query.values(Depend.id, Depend.name))
        domain_total_set = set(Domain.query.values(Domain.id, Domain.name))
        publish_ip_set = set(self.publish_ips.values(PublishIp.id, PublishIp.ip))
        private_ip_set = set(self.private_ips.values(PrivateIp.id, PrivateIp.ip))
        depend_set = set(self.depends.values(Depend.id, Depend.name))
        domain_set = set(self.domains.values(Domain.id, Domain.name))
        publish_ip_excluded = list(publish_ip_total_set.difference(publish_ip_set))
        private_ip_excluded = list(private_ip_total_set.difference(private_ip_set))
        depend_excluded = list(depend_total_set.difference(depend_set))
        domain_excluded = list(domain_total_set.difference(domain_set))
        return publish_ip_excluded, private_ip_excluded, depend_excluded, domain_excluded

    @staticmethod
    def validate_service(form, modify_flag=True):
        error = []
        if modify_flag:
            if form.get('id', '').strip() == '':
                error.append('应用ID为空')
            else:
                _service = Service.query.get(int(form.get('id')))
                if not _service:
                    error.append('应用ID不存在')
        if form.get('name', '').strip() == '':
            error.append('应用名为空')
        else:
            _service = Service.query.filter_by(name=form.get('name'), business_id=form.get('business_id')).first()
            if _service:
                if modify_flag:
                    if _service.id != int(form.get('id')):
                        error.append('应用已存在')
                else:
                    error.append('应用已存在')
        if form.get('business_id', '').strip() == '':
            error.append('所属产品为空')
        if form.get('user_id', '').strip() == '':
            error.append('运行账户为空')
        if form.get('priority_id', '').strip() == '':
            error.append('应用优先级为空')
        if form.get('status', '').strip() == '':
            error.append('应用状态为空')
        if error:
            return False, '\n'.join(error)
        return True, ''


class ServiceAgent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, default=0, nullable=False)
    name = db.Column(db.String(128), default='', nullable=False)
    name_alias = db.Column(db.String(128), default='', nullable=False)
    port = db.Column(db.String(5), default='',  nullable=False)
    business = db.Column(db.String(128), default='', nullable=False)
    business_id = db.Column(db.Integer, default=0, nullable=False)
    user = db.Column(db.String(128), default='', nullable=False)
    user_id = db.Column(db.Integer, default=0, nullable=False)
    priority = db.Column(db.String(128), default='', nullable=False)
    priority_id = db.Column(db.Integer, default=0, nullable=False)
    domain = db.Column(db.Text, default='', nullable=False)
    depend = db.Column(db.Text, default='', nullable=False)
    publish_ip = db.Column(db.Text, default='', nullable=False)
    private_ip = db.Column(db.Text, default='', nullable=False)
    contact = db.Column(db.Text, default='', nullable=False)
    contact_email = db.Column(db.Text, default='', nullable=False)
    db_instance = db.Column(db.String(128), default='', nullable=False)
    comment = db.Column(db.Text, default='', nullable=False)
    state = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.Integer, default=-1, nullable=False)
    check_user = db.Column(db.String(128), default='', nullable=False)
    create_time = db.Column(db.DateTime(), default=datetime.datetime.now)
    change_time = db.Column(db.DateTime(), default=datetime.datetime.now, onupdate=datetime.datetime.now, index=True)
    
    __table_args__ = {'mysql_engine': 'Innodb', 'mysql_charset': 'utf8'}
    __tablename__ = 'service_agents'

    def __repr__(self):
        return '<ServiceAgent %r>' % self.name

    def to_json(self):
        _business = Business.query.get(self.business_id)
        if _business:
            business = _business.name
        else:
            business = ''
        _user = ServiceUser.query.get(self.user_id)
        if _user:
            user = _user.name
        else:
            user = ''
        _service = Service.query.get(self.service_id)
        if _service:
            old_port = _service.port
            old_depend = _service.to_json()['depend']
        else:
            old_port = '空'
            old_depend = ['空',]
        port = self.port if self.port else '空'
        depend = self.depend.split(',') if self.depend else ['空',]
        state_dict = {0: '未处理', 1: '已处理', 2: '删除'}
        return dict(id=self.id, service_id=self.service_id, name=self.name, 
                    name_alias=self.name_alias, port=port, contact=self.contact, 
                    business=business, user=user, db_instance=self.db_instance.split(','), 
                    depend=depend, domain=self.domain.split(','), state_name=state_dict[self.state],
                    publish_ip=self.publish_ip.split(','), private_ip=self.private_ip.split(','), 
                    state_id=self.state, create_time=self.create_time.strftime('%Y-%m-%d %H:%M:%S'),
                    change_time=self.change_time.strftime('%Y-%m-%d %H:%M:%S'), old_port=old_port, old_depend=old_depend)

