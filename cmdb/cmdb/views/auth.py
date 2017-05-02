# coding=utf-8

import os
import hashlib
from PIL import Image
from flask import Blueprint, request, render_template, redirect, url_for, current_app
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.utils import secure_filename
from ..models import User
from .. import db, avatars
from ..utils.sendemail import send_async_email

auth = Blueprint('auth', __name__)


@auth.before_app_request
def before_request():
    if current_user.is_authenticated:
        current_user.ping()
        if not current_user.confirmed \
                and request.endpoint[:5] != 'auth.' \
                and request.endpoint != 'static':
            return redirect(url_for('auth.unconfirmed'))


@auth.route('/unconfirmed/')
def unconfirmed():
    if current_user.is_anonymous or current_user.confirmed:
        return redirect(url_for('home.index'))
    return render_template('auth/unconfirmed.html')


@auth.route('/confirm/')
@login_required
def reconfirm():
    token = current_user.generate_user_token()
    send_async_email.delay(sender=current_app.config['MAIL_DEFAULT_SENDER'], to=current_user.email, subject='注册激活邮件',
                           template='auth/email/confirm', token=token.decode())
    return render_template('auth/register_replay.html', email=current_user.email)


@auth.route('/confirm/<token>/')
@login_required
def confirm(token):
    if current_user.confirmed:
        return redirect(url_for('home.index'))
    if current_user.confirm(token):
        return redirect(url_for('home.index'))
    return redirect(url_for('home.index'))


@auth.route('/register/', methods=['GET', 'POST'])
def register():
    form, error = '', ''
    if request.method == 'POST':
        form = request.form
        ret, error = User.validate_register(form)
        if ret:
            _user = User(name=form.get('name'), password=form.get('password2'),
                         email=form.get('email'), phone=form.get('phone'))
            db.session.add(_user)
            db.session.commit()
            token = _user.generate_user_token()
            send_async_email.delay(sender=current_app.config['MAIL_DEFAULT_SENDER'], to=_user.email, subject='注册激活邮件',
                                   template='auth/email/confirm', token=token.decode())
            return render_template('auth/register_replay.html', email=form.get('email'))
    return render_template('auth/register.html', error=error, form=form)


@auth.route('/login/', methods=['GET', 'POST'])
def login():
    _name, error = '', ''
    if request.method == 'POST':
        _name = request.form.get('name', '')
        _password = request.form.get('password', '')
        _user = User.query.filter_by(name=_name).first()
        if not _user:
            error = u'用户名未注册'
        elif not _user.status:
            error = u'该用户禁止登陆, 请联系管理员'
        else:
            if _user.verify_password(_password):
                login_user(_user, remember=True)
                return redirect(url_for('home.index'))
            else:
                error = u'密码错误'
    return render_template('auth/login.html', name=_name, error=error)


@auth.route('/logout/')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth.route('/change_password/', methods=['GET', 'POST'])
@login_required
def change_password():
    error = ''
    if request.method == 'POST':
        _form = request.form
        ret, error = User.validate_update_password(_form)
        if ret:
            current_user.password = _form.get('password_repeat_new')
            db.session.add(current_user)
            db.session.commit()
            return redirect(url_for('home.index'))
    return render_template('auth/person_settings.html', error=error)


@auth.route('/change_image/', methods=['GET', 'POST'])
@login_required
def change_image():
    error = ''
    if request.method == 'POST':
        if 'file' in request.files:
            file_name = request.files['file']
            if file_name.filename == '':
                error = '文件为空'
            elif not os.path.splitext(file_name.filename)[0].isalnum():
                error = '文件名只能包含数字或字母'
            else:
                try:
                    file = avatars.save(request.files['file'])
                    file_path = os.path.join(current_app.config['UPLOADED_AVATARS_DEST'], file)
                    im = Image.open(file_path)
                    im.thumbnail((48, 48))
                    _avatar_name = hashlib.md5(secure_filename(file_name.filename).encode()).hexdigest()
                    _avatar_path = os.path.join(current_app.config['UPLOADED_AVATARS_DEST'], _avatar_name)
                    im.save(_avatar_path, format='JPEG')
                    current_user.avatar_hash = _avatar_name
                    db.session.add(current_user)
                    db.session.commit()
                    return redirect(url_for('home.index'))   
                except: 
                    error = "上传失败"
                else:
                    os.unlink(file_path)
                    im.close()
        else:
            error = '文件错误'
    return render_template('auth/change_image.html', error=error)


@auth.route('/forgot/password/', methods=['GET', 'POST'])
def password_reset_request():
    error = ''
    if not current_user.is_anonymous:
        return redirect(url_for('home.index'))
    if request.method == 'POST':
        _form = request.form
        _user = User.query.filter_by(email=_form.get('email', '')).first()
        if _user:
            token = _user.generate_user_token()
            send_async_email.delay(sender=current_app.config['MAIL_DEFAULT_SENDER'], to=_user.email, subject='重置密码邮件',
                                   template='auth/email/reset_password', token=token.decode())
            return render_template('auth/forgot_password_replay.html', email=_form.get('email'))
        else:
            error = '邮箱未注册'
    return render_template('auth/forgot_password.html', error=error)


@auth.route('/reset/password/<token>/', methods=['GET', 'POST'])
def password_reset(token):
    form, error = '', ''
    if not current_user.is_anonymous:
        return redirect(url_for('home.index'))
    if request.method == 'POST':
        form = request.form
        ret, error = User.validate_reset_password(form)
        if ret:
            _user = User.query.filter_by(email=form.get('email')).first()
            if _user.reset_password(token, form.get('password2')):
                return redirect(url_for('auth.login'))
            else:
                error = '密码更新失败'
    return render_template('auth/reset_password.html', form=form, error=error)
