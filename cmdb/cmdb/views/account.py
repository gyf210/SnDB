# coding=utf-8

from flask import Blueprint, g, render_template, jsonify, request
from flask_login import login_required, current_user
from ..models import Role, User
from .. import db
from ..utils.decorators import admin_required

account = Blueprint('account', __name__)


@account.before_request
def before_request():
    role_list = []
    _roles = Role.query.all()
    for _role in _roles:
        role_list.append(_role.to_json())
    g.role_list = role_list


@account.route('/user_list/')
@login_required
@admin_required
def index():
    return render_template('account/user.html', roles=g.role_list)


@account.route('/user_list_data/')
@login_required
@admin_required
def user_list_data():
    data = []
    _users = User.query.filter_by(status=1, confirmed=1).all()
    for _user in _users:
        data.append(_user.to_json())
    return jsonify({'data': data})


@account.route('/user_enable_data/')
@login_required
@admin_required
def user_enable_data():
    _id = request.args.get('id', '')
    _user = User.query.filter_by(id=_id).first()
    _user.status = 1
    db.session.add(_user)
    db.session.commit()
    return ''


@account.route('/user_disable_data/')
@login_required
@admin_required
def user_disable_data():
    _id = request.args.get('id', '')
    _user = User.query.filter_by(id=_id).first()
    if not _user:
        error = '用户不存在'
    elif _user == current_user:
        error = '当前用户无法禁用'
    else:
        error = ''
        _user.status = 0
        db.session.add(_user)
        db.session.commit()
    return jsonify({'error': error})


@account.route('/user_delete_data/')
@login_required
@admin_required
def user_delete_data():
    _id = request.args.get('id', '')
    _user = User.query.filter_by(id=_id).first()
    if not _user:
        error = '用户不存在'
    elif current_user == _user:
        error = '当前用户无法删除'
    else:
        error = ''
        db.session.delete(_user)
        db.session.commit()
    return jsonify({'error': error})


@account.route('/user_activate_data/')
@login_required
@admin_required
def user_activate_data():
    _id = request.args.get('id', '')
    _user = User.query.filter_by(id=_id).first()
    _user.confirmed = 1
    db.session.add(_user)
    db.session.commit()
    return ''


@account.route('/user_disable/')
@login_required
@admin_required
def user_disable():
    return render_template('account/user_disable.html')


@account.route('/user_list_data_disable/')
@login_required
@admin_required
def user_list_data_disable():
    data = []
    _users = User.query.filter_by(status=0).filter_by(confirmed=1).all()
    for _user in _users:
        data.append(_user.to_json())
    return jsonify({'data': data})


@account.route('/user_unactivate/')
@login_required
@admin_required
def user_unactivate():
    return render_template('account/user_unactivate.html')


@account.route('/user_list_data_unactivate/')
@login_required
@admin_required
def user_list_data_unactivate():
    data = []
    _users = User.query.filter_by(confirmed=0).all()
    for _user in _users:
        data.append(_user.to_json())
    return jsonify({'data': data})


@account.route('/user_modify_list/')
@login_required
@admin_required
def user_modify_list():
    _id = request.args.get('id', '')
    _user = User.query.filter_by(id=_id).first().to_json()
    _user['roles'] = g.role_list
    return jsonify(_user)


@account.route('/user_modify/', methods=['POST'])
@login_required
@admin_required
def user_modify():
    if request.method == 'POST':
        _form = request.form
        ret, error = User.validate_modify(_form)
        if ret:
            _user = User.query.filter_by(id=_form.get('id', type=int)).first()
            _user.phone = _form.get('phone')
            _user.role_id = _form.get('role_id')
            db.session.add(_user)
            db.session.commit()
        return jsonify({'error': error})


@account.route('/user_create/', methods=['POST'])
@login_required
@admin_required
def user_create():
    if request.method == 'POST':
        _form = request.form
        ret, error = User.validate_create(_form)
        if ret:
            _user = User()
            _user.name = _form.get('name').strip()
            _user.password = _form.get('password').strip()
            _user.email = _form.get('email').strip()
            _user.phone = _form.get('phone').strip()
            _user.confirmed = True
            db.session.add(_user)
            db.session.commit()
            _user = User.query.filter_by(name=_form.get('name')).first()
            _user.role_id = _form.get('role_id')
            db.session.add(_user)
            db.session.commit()
        return jsonify({'error': error}) 
