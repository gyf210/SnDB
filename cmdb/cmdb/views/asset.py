# coding=utf-8

import os
import json
from hashlib import md5
import xlrd
import tablib
from funcy import flatten
from flask import Blueprint, render_template, jsonify, request, g, current_app, redirect, url_for, make_response
from flask_login import login_required, current_user
from ..models import Idc, Host, Business, Service, HostType, System, \
                     Env, Domain, Depend, ServiceUser, Priority, PrivateIp, PublishIp, VipIp, ServiceAgent
from .. import db, datas
from ..utils.statshost import stats_api_lingshu
from ..utils.checkurl import checkurl
from ..utils.changeip import validate_ip
from ..utils.decorators import admin_required
from ..utils.createuuid import createuuid
from .raw_sql import BUSINESS_HOST_IDC_DATA, HOST_IDC_SERVICE_BUSINESS_DATA

asset = Blueprint('asset', __name__)


def query_db_function(name, filters=None):
    result_list = []
    if filters:
        results = name.query.filter_by(filters).all()
    else:
        results = name.query.all()
    for result in results:
        result_list.append(result.to_json())
    return result_list


@asset.before_request
@admin_required
def before_request():
    g.users = query_db_function(ServiceUser)
    g.priorities = query_db_function(Priority)


@asset.route('/idc_list/')
@login_required
@admin_required
def idc_list():
    return render_template('asset/idc_list.html')


@asset.route('/idc_list_data/')
@login_required
@admin_required
def idc_list_data():
    data = [_idc.to_json() for _idc in Idc.query.order_by(Idc.change_time.desc()).all()]
    return jsonify({'data': data})


@asset.route('/idc_create/', methods=['POST'])
@login_required
@admin_required
def idc_create():
    _form = request.form
    ret, error = Idc.validate_idc(_form, False)
    if ret:
        _idc = Idc(**_form)
        db.session.add(_idc)
        db.session.commit()
    return jsonify({'error': error})


@asset.route('/idc_modify_list/', methods=['POST'])
@login_required
@admin_required
def idc_modify_list():
    _id = request.form.get('id', default=-1, type=int)
    _idc = Idc.query.get(_id)
    return jsonify(_idc.to_json())


@asset.route('/idc_modify/', methods=['POST'])
@login_required
@admin_required
def idc_modify():
    _form = request.form
    ret, error = Idc.validate_idc(_form)
    if ret:
        _id = _form.get('id', type=int)
        Idc.query.filter_by(id=_id).update(_form)
        db.session.commit()
    return jsonify({'error': error})


@asset.route('/idc_delete_data/', methods=['POST'])
@login_required
@admin_required
def idc_delete_data():
    error = '' 
    _id = request.form.get('id', default=-1, type=int)
    _idc = Idc.query.get(_id)
    if not _idc:
        error = '所选机房ID为空'
    elif _idc.hosts.count():
        error = '{} 关联主机无法删除'.format(_idc.name)
    else:
        db.session.delete(_idc)
        db.session.commit()
    return jsonify({'error': error})


@asset.route('/idc_batch_delete_data/', methods=['POST'])
@login_required
@admin_required
def idc_batch_delete_data():
    error = ''
    _id_set = set(request.form.get('ids', '').split(','))
    if not _id_set:
        error = '所选机房ID为空'
    else:
        _errors = []
        for _id in _id_set:
            if _id.isdigit():
                _id = int(_id)
                _idc = Idc.query.get(_id)
                if _idc:
                    if _idc.hosts.count():
                        _errors.append(_idc.name)
                    else:
                        db.session.delete(_idc)
        db.session.commit()
        if _errors:
            error = '{} 关联主机无法删除'.format(', '.join(set(_errors)))
    return jsonify({'error': error})


@asset.route('/host_list/', methods=['GET', 'POST'])
@login_required
@admin_required
def host_list():
    fields = [{'id': 1, 'name': '所属机房'}, {'id': 2, 'name': '公网IP'}, {'id': 3, 'name': '内网IP'},
              {'id': 4, 'name': '所属产品'}, {'id': 5, 'name': '负责人'}, {'id': 6, 'name': '主机状态'}]
    if request.method == 'POST':
        field_id = request.form.get('field_id', default=-1, type=int)
        search_data = request.form.get('search_data', default='').strip()
        if field_id not in list(range(1, 7)) or not search_data:
            return jsonify({'hosts': ''})
        elif field_id == 1:
            idc = Idc.query.filter_by(name=search_data).first()
            if idc and idc.hosts.count():
                return jsonify({'hosts': [_host.to_json() for _host in idc.hosts]})
        elif field_id == 2:
            status, ret = validate_ip(search_data)
            if status and ret == 2:
                publish_ip = PublishIp.query.filter_by(ip=search_data).first()
                if publish_ip and publish_ip.host:
                    return jsonify({'hosts': [publish_ip.host.to_json()]})
                vip_ip = VipIp.query.filter_by(ip=search_data).first()
                if vip_ip:
                    return jsonify({'hosts': [_host.to_json() for _host in vip_ip.hosts]})
                hosts = Host.query.filter_by(host_ip=search_data).all()
                if hosts:
                    return jsonify({'hosts': [_host.to_json() for _host in hosts]})
        elif field_id == 3:
            status, ret = validate_ip(search_data)
            if status and ret == 1:
                private_ip = PrivateIp.query.filter_by(ip=search_data).first()
                if private_ip and private_ip.host:
                    return jsonify({'hosts': [private_ip.host.to_json()]})
                vip_ip = VipIp.query.filter_by(ip=search_data).first()
                if vip_ip:
                    return jsonify({'hosts': [_host.to_json() for _host in vip_ip.hosts]})
                hosts = Host.query.filter_by(host_ip=search_data).all()
                if hosts:
                    return jsonify({'hosts': [_host.to_json() for _host in hosts]})
        elif field_id == 4:
            hosts = []
            businesses = Business.query.filter(Business.name.ilike('%{}%'.format(search_data)))
            if businesses.count():
                for business in businesses:
                    if business.hosts.count():
                        hosts.extend([_host.to_json() for _host in business.hosts])
                return jsonify({'hosts': hosts})
        elif field_id == 5:
            hosts = Host.query.filter(Host.owner.ilike('%{}%'.format(search_data)))
            if hosts.count():
                return jsonify({'hosts': [_host.to_json() for _host in hosts]})
        elif field_id == 6:
            status_dict = {'使用': 0, '维护': 1, '空闲': 2}
            status_id = status_dict.get(search_data, -1)
            hosts = Host.query.filter_by(status=status_id).all()
            if hosts:
                return jsonify({'hosts': [_host.to_json() for _host in hosts]})
        return jsonify({'hosts': ''})
    page_id = request.args.get('id', default=1, type=int)
    hosts = Host.query.order_by(Host.change_time.desc()).paginate(page_id, 10, False)
    page_per_echo = 8
    page_range_list = []
    if hosts.pages - page_id >= page_per_echo // 2:
        start_index = max(page_id - page_per_echo // 2, 1)
    else:
        start_index = hosts.pages - page_per_echo + 1
    end_index = max(page_id + page_per_echo // 2, page_per_echo + 1)
    for number in range(start_index, end_index):
        if 0 < number <= hosts.pages:
            page_range_list.append(number)
    idcs = query_db_function(Idc)
    host_types = query_db_function(HostType)
    systems = query_db_function(System)
    envs = query_db_function(Env)
    businesses = Business.choice_business_list(0, 3)
    if hosts.items:
        start = (hosts.page - 1) * 10 + 1
        end = hosts.page * 10 if page_id != hosts.pages else hosts.total
    else:
        start = 0
        end = 0
    return render_template('asset/host_list.html', idcs=idcs, host_types=host_types,
                           start=start, end=end, systems=systems, envs=envs, businesses=businesses,
                           hosts=hosts, page_range_list=page_range_list, fields=fields)


@asset.route('/host_auto_create/', methods=['POST'])
@login_required
@admin_required
def host_auto_create():
    error_list = []
    _ip_set = set(request.form.get('auto_ip', '').split())
    business_id = request.form.get('business_id', type=int)
    status = request.form.get('status', default=-1, type=int)
    if not _ip_set:
        error_list.append('主机IP为空')
    if not Business.query.get(business_id):
        error_list.append('所属产品为空')
    if status == -1:
        error_list.append('主机状态为空')
    if error_list:
        return jsonify({'error': '\n'.join(error_list), 'ret': 0})
    else:
        _ok_list, _error_list, _error_repeat_list = Host.validate_auto_check_ip(_ip_set)
        _ip_error_set, _data_api_set = set(), set()
        if _ok_list:
            for _ip in _ok_list:
                try:    
                    _data_list = stats_api_lingshu([_ip, ])
                    if not _data_list:
                        _ip_error_set.add(_ip)
                    else:
                        _data_api_set.add(json.dumps(_data_list))
                except:
                    _ip_error_set.add(_ip)
            if _data_api_set:
                for _data in _data_api_set:
                    _data = json.loads(_data)
                    _items = {}
                    _items_api_list = Host.batch_create_host(_data)
                    for key, value in _items_api_list[0].items():
                        if not (key == 'publish_ip' or key == 'private_ip' or key == 'vip_ip'):
                            _items[key] = value if isinstance(value, int) else value.strip()
                    _host = Host(**_items)
                    _host.business_id = business_id
                    _host.status = status
                    if _items_api_list[0]['publish_ip']:
                        _host.publish_ips.extend([PublishIp(ip=_ip) for _ip in _items_api_list[0]['publish_ip']])
                    _host.private_ips.extend([PrivateIp(ip=_ip) for _ip in _items_api_list[0]['private_ip']])
                    if _items_api_list[0]['vip_ip']:
                        for _ip in _items_api_list[0]['vip_ip']:
                            _vip_ip = VipIp.query.filter_by(ip=_ip).first()
                            if not _vip_ip:
                                _vip_ip = VipIp(ip=_ip)
                            _host.vip_ips.append(_vip_ip)
                    db.session.add(_host)
                db.session.commit()
        error = []
        if _error_list:
            error.append('错误IP:{}'.format(','.join(_error_list)))
        if _error_repeat_list:
            error.append('已添加IP:{}'.format(','.join(_error_repeat_list)))
        if _ip_error_set:
            error.append('需手动添加IP:{}'.format(','.join(_ip_error_set)))
        if not error:
            return jsonify({'error': '', 'ret': 1})
        else:
            return jsonify({'error': '\n'.join(error), 'ret': 1})
    

@asset.route('/host_create/', methods=['POST'])
@login_required
@admin_required
def host_create():
    _form = request.form
    ret, error = Host.validate_host(_form, False)
    if ret:
        _items = {}
        for key, value in _form.items():
            if not (key == 'publish_ip' or key == 'private_ip' or key == 'vip_ip'):
                _items[key] = value.strip()
        _items['name'] = createuuid()
        _host = Host(**_items)
        publish_ip_set = set(_form.get('publish_ip', '').split())
        private_ip_set = set(_form.get('private_ip', '').split())
        vip_ip_set = set(_form.get('vip_ip', '').split())
        if publish_ip_set:
            _host.publish_ips.extend([PublishIp(ip=_ip) for _ip in publish_ip_set])
        _host.private_ips.extend([PrivateIp(ip=_ip) for _ip in private_ip_set])
        if vip_ip_set:
            for _ip in vip_ip_set:
                _vip_ip = VipIp.query.filter_by(ip=_ip).first()
                if not _vip_ip:
                    _vip_ip = VipIp(ip=_ip)
                _host.vip_ips.append(_vip_ip)
        db.session.add(_host)
        db.session.commit()
        error = ''
    return jsonify({'error': error})


@asset.route('/host_modify_list/', methods=['POST'])
@login_required
@admin_required
def host_modify_list():
    _id = request.form.get('id', default=-1, type=int)
    _host = Host.query.get(_id)
    return jsonify(_host.to_json())


@asset.route('/host_modify/', methods=['POST'])
@login_required
@admin_required
def host_modify():
    _form = request.form
    ret, error = Host.validate_host(_form)
    if ret:
        _items, _error, _error_publish_ip, _error_private_ip = {}, [], [], []
        _id = _form.get('id', type=int)
        for key, value in _form.items():
            if not (key == 'publish_ip' or key == 'private_ip' or key == 'vip_ip'):
                _items[key] = value.strip()
        Host.query.filter_by(id=_id).update(_items)
        _host = Host.query.get(_id)

        publish_ip = set([publish_ip.ip for publish_ip in _host.publish_ips])
        publish_ip_modify = set(_form.get('publish_ip').split())
        if publish_ip != publish_ip_modify:
            src_set = publish_ip.difference(publish_ip_modify)
            dest_set = publish_ip_modify.difference(publish_ip)
            if not src_set and dest_set:
                _host.publish_ips.extend([PublishIp(ip=_ip) for _ip in dest_set])
            elif src_set:
                for _ip in src_set:
                    if PublishIp.query.filter_by(ip=_ip).first().services.count():
                        _error_publish_ip.append(_ip)
                if not _error_publish_ip:
                    for _ip in src_set:
                        _host.publish_ips.remove(PublishIp.query.filter_by(ip=_ip).first())
                    if dest_set:
                        _host.publish_ips.extend([PublishIp(ip=_ip) for _ip in dest_set])

        private_ip = set([private_ip.ip for private_ip in _host.private_ips])
        private_ip_modify = set(_form.get('private_ip').split())
        if private_ip != private_ip_modify:
            src_set = private_ip.difference(private_ip_modify)
            dest_set = private_ip_modify.difference(private_ip)
            if not src_set and dest_set:
                _host.private_ips.extend([PrivateIp(ip=_ip) for _ip in dest_set])
            elif src_set:
                for _ip in src_set:
                    if PrivateIp.query.filter_by(ip=_ip).first().services.count():
                        _error_private_ip.append(_ip)
                if not _error_private_ip:
                    for _ip in src_set:
                        _host.private_ips.remove(PrivateIp.query.filter_by(ip=_ip).first())
                    if dest_set:
                        _host.private_ips.extend([PrivateIp(ip=_ip) for _ip in dest_set])

        vip_ip = set([vip_ip.ip for vip_ip in _host.vip_ips])
        vip_ip_modify = set(_form.get('vip_ip').split())
        if vip_ip != vip_ip_modify:
            if vip_ip:
                for _ip in vip_ip:
                    _host.vip_ips.remove(VipIp.query.filter_by(ip=_ip).first())
            if vip_ip_modify:
                for _ip in vip_ip_modify:
                    _vip_ip = VipIp.query.filter_by(ip=_ip).first()
                    if not _vip_ip:
                        _vip_ip = VipIp(ip=_ip)
                    _host.vip_ips.append(_vip_ip)

        if _error_publish_ip:
            _error.append('公网IP{}关联应用无法修改'.format(','.join(_error_publish_ip)))
        if _error_private_ip:
            _error.append('内网IP{}关联应用无法修该'.format(','.join(_error_private_ip)))
        if _error:
            error = '\n'.join(_error)
        else:
            db.session.commit()
    return jsonify({'error': error})


@asset.route('/host_delete_data/', methods=['POST'])
@login_required
@admin_required
def host_delete_data():
    _host = Host.query.get(request.form.get('id', default=-1, type=int))
    if not _host:
        error = '主机ID为空'
    else:
        _error = []
        for private_ip in _host.private_ips:
            if private_ip.services.count():
                _error.append(private_ip.ip)
        if _host.publish_ips.count():
            for publish_ip in _host.publish_ips:
                if publish_ip.services.count():
                    _error.append(publish_ip.ip)
        if not _error:
            db.session.delete(_host)
            db.session.commit()
            error = ''
        else:
            error = '主机{} 关联应用无法删除'.format(', '.join(_error))
    return jsonify({'error': error})


@asset.route('/host_batch_delete_data/', methods=['POST'])
@login_required
@admin_required
def host_batch_delete_data():
    _error = ''
    _id_set = set(request.form.get('ids', '').split(','))
    if not _id_set:
        _error = '所选主机ID为空'
    else:
        _errors = []
        for _id in _id_set:
            if _id.isdigit():
                _id = int(_id)
                _host = Host.query.get(_id)
                if _host:
                    if _host.services.count():
                        _errors.append(_host.private_ips.all()[0].ip)
                    else:
                        db.session.delete(_host)
        db.session.commit()
        if _errors:
            _error = '主机{} 关联应用无法删除'.format(', '.join(set(_errors)))
    return jsonify({'error': _error})


@asset.route('/host_batch_output_data/')
@login_required
@admin_required
def host_batch_output_data():
    headers = ['SN', 'CPU', 'MEMORY', 'DISK', '内网IP', '公网IP', '虚拟IP', '宿主IP', '所属机房','主机类型', '操作系统', '所属环境', '所属业务', '所属服务', '负责人', '备注']
    _results = db.session.execute(HOST_IDC_SERVICE_BUSINESS_DATA).fetchall()
    data = tablib.Dataset(*_results, headers=headers)
    ret = make_response(data.xlsx)
    filename = '{}.xlsx'.format('HOST_SERVICE_DATA')
    ret.headers["Content-Disposition"] = "attachment; filename={}".format(filename)
    return ret 
    

@asset.route('/business_list/')
@login_required
@admin_required
def business_list():
    businesses = Business.choice_business_list(0, 2)
    return render_template('asset/business_list.html', businesses=businesses)


@asset.route('/business_list_data/')
@login_required
@admin_required
def business_list_data():
    data = [_business.to_json() for _business in
            Business.query.filter(Business.type > 1).order_by(Business.change_time.desc())]
    return jsonify({'data': data})


@asset.route('/business_create/', methods=['POST'])
@login_required
@admin_required
def business_create():
    _form = request.form
    ret, error = Business.validate_business(_form, False)
    if ret:
        _business = Business(**_form)
        pid = _form.get('pid', '')
        _business.product, _business.type = _business.create_product_type(pid)
        db.session.add(_business)
        db.session.commit()
    return jsonify({'error': error})


@asset.route('/business_modify_list/', methods=['POST'])
@login_required
@admin_required
def business_modify_list():
    _id = request.form.get('id', default=-1, type=int)
    _business = Business.query.get(_id)
    return jsonify(_business.to_json())


@asset.route('/business_modify/', methods=['POST'])
@login_required
@admin_required
def business_modify():
    _form = request.form
    ret, error = Business.validate_business(_form)
    if ret:
        _id = _form.get('id', default=-1, type=int)
        _mess_dict = {}
        for key, value in _form.items():
            _mess_dict[key] = value
        _mess_dict['type'] = Business.query.get(_mess_dict['pid']).type + 1
        _mess_dict['product'] = '{},{}'.format(
            Business.query.get(_mess_dict['pid']).product, str(_mess_dict['pid']))
        Business.query.filter_by(id=_id).update(_mess_dict)
        db.session.commit()
    return jsonify({'error': error})


@asset.route('/business_delete_data/', methods=['POST'])
@login_required
@admin_required
def business_delete_data():
    _id = request.form.get('id', default=-1, type=int)
    _business = Business.query.get(_id)
    if not _business:
        error = '产品ID为空'
    elif _business.services.count():
        error = '关联应用{}无法删除'.format(','.join([_service.name for _service in _business.services]))
    elif _business.hosts.count():
        error = '关联主机{}无法删除'.format(','.join([_host.name for _host in _business.hosts]))
    else:
        db.session.delete(_business)
        db.session.commit()
        error = ''
    return jsonify({'error': error})


@asset.route('/business_batch_delete_data/', methods=['POST'])
@login_required
@admin_required
def business_batch_delete_data():
    _ids = request.form.get('ids', '')
    if not _ids:
        error = '产品ID为空'
    else:
        _errors = []
        _id_list = _ids.split(',')
        for _id in _id_list:
            if _id:
                _business = Business.query.get(int(_id))
                if not _business.services.count() and not _business.hosts.count():
                    db.session.delete(_business)
                else:
                    _errors.append(_business.name)
        if _errors:
            error = '{} 存在关联无法删除'.format(', '.join(_errors))
        else:
            error = ''
        db.session.commit()
    return jsonify({'error': error}) 


@asset.route('/business_tree/')
@login_required
@admin_required
def business_tree():
    return render_template('asset/business_tree.html')


@asset.route('/business_tree_data_list/', methods=['POST'])
@login_required
@admin_required
def business_tree_data_list():
    businesses = Business.query.all()
    data = [{'id': _business.id, 'pid': _business.pid, 'name': _business.name} for _business in businesses]
    return jsonify(data)


@asset.route('/business_tree_info/', methods=['POST'])
@login_required
@admin_required
def business_tree_info():
    id = request.form.get('id', default=-1, type=int)
    _business = Business.query.get(id)
    if _business:
        data = {}
        data['status'] = 0
        data['business_name'] = _business.name
        data['business_owner'] = _business.contact
        _column = ["idc_name", "private_ip"]
        _sql = BUSINESS_HOST_IDC_DATA.format(str(_business.id))
        _results = db.session.execute(_sql).fetchall()
        _messages = [dict(zip(_column, _result)) for _result in _results if _result[1]]
        data['business_host'] = _messages
        try:
            data['business_service'] = list(flatten(_business.services.values(Service.name))) 
        except:
            data['business_service'] = ''
        return jsonify(data)
    else:
        data = {'status': 1}
        return jsonify(data)


@asset.route('/business_tree_create/', methods=['POST'])
@login_required
@admin_required
def business_tree_create():
    data = json.loads(request.form.get('data'))
    _form = {}
    for _item in data.get('params'):
        _form[_item['name']] = _item['value']
    _form['pid'] = str(data['pid'])
    ret, error = Business.validate_business(_form, False)
    if ret:
        _business = Business(**_form)
        pid = _form.get('pid')
        _business.product, _business.type = _business.create_product_type(pid)
        db.session.add(_business)
        db.session.commit()
        return jsonify({'error': error, 'id': _business.id, 'name': _business.name})
    return jsonify({'error': error})


@asset.route('/business_tree_modify/', methods=['POST'])
@login_required
@admin_required
def business_tree_modify():
    data = json.loads(request.form.get('data'))
    _form = {}
    for _item in data.get('params'):
        _form[_item['name']] = _item['value'].strip()
    pid = data.get('pid', -1)
    ret, error = Business.validate_tree_business(_form, pid)
    if ret:
        _id = _form.get('id')
        Business.query.filter_by(id=_id).update(_form)
        db.session.commit()
        return jsonify({'error': error, 'name': _form.get('name')})
    return jsonify({'error': error})


@asset.route('/business_tree_delete/', methods=['POST'])
@login_required
@admin_required
def business_tree_delete():
    _id = request.form.get('id', default=-1, type=int)
    _business = Business.query.get(_id)
    _product = set((flatten([bu[0].split(',') for bu in Business.query.values(Business.product)])))
    if not _business:
        error = '产品为空'
    elif _business.services.count():
        error = '关联服务无法删除'
    elif _business.hosts.count():
        error = '关联主机无法删除'
    elif str(_id) in _product:
        error = '关联产品无法删除'
    else: 
        error = ''
        db.session.delete(_business)
        db.session.commit()
    return jsonify({'error': error})
        

@asset.route('/app_list/', methods=['GET', 'POST'])
@login_required
@admin_required
def app_list():
    fields = [{'id': 1, 'name': '应用名'}, {'id': 2, 'name': '内网IP'},
              {'id': 3, 'name': '外网IP'}, {'id': 4, 'name': '所属产品'},
              {'id': 5, 'name': '所属域名'}, {'id': 6, 'name': '负责人'}]
    if request.method == 'POST':
        field_id = request.form.get('field_id', default=-1, type=int)
        search_result = request.form.get('search_result', default='').strip()
        if field_id not in list(range(1, 7)) or not search_result:
            return jsonify({'services': ''})
        if field_id == 1:
            services = Service.query.filter(Service.name.contains(search_result)).all()
            if services:
                return jsonify({'services': [service.to_json() for service in services]})
        if field_id == 2:
            private_ips = PrivateIp.query.filter_by(ip=search_result).all()
            if private_ips:
                _service_private_ip_list = []
                for _private_ip in private_ips:
                    _service_private_ip_list.extend([service.to_json() for service in _private_ip.services])
                return jsonify({'services': _service_private_ip_list})
        if field_id == 3:
            publish_ips = PublishIp.query.filter_by(ip=search_result).all()
            if publish_ips:
                _service_publish_ip_list = []
                for _publish_ip in publish_ips:
                    _service_publish_ip_list.extend([service.to_json() for service in _publish_ip.services])
                return jsonify({'services': _service_publish_ip_list})
        if field_id == 4:
            businesses = Business.query.filter(Business.name.contains(search_result)).all()
            if businesses:
                _service_business_list = []
                for business in businesses:
                    _service_business_list.extend([service.to_json() for service in business.services])
                return jsonify({'services': _service_business_list})
        if field_id == 5:
            domains = Domain.query.filter(Domain.name.contains(search_result)).all()
            if domains:
                _service_domain_list = []
                for domain in domains:
                    _service_domain_list.extend([service.to_json() for service in domain.services])
                return jsonify({'services': _service_domain_list})
        if field_id == 6:
            services = Service.query.filter_by(contact=search_result).all()
            if services:
                return jsonify({'services': [service.to_json() for service in services]})
        return jsonify({'services': ''})
    page_id = request.args.get('id', default=1, type=int)
    services = Service.query.order_by(Service.change_time.desc()).paginate(page_id, 10, False)
    page_per_echo = 8
    page_range_list = []
    if services.pages - page_id >= page_per_echo // 2:
        start_index = max(page_id - page_per_echo // 2, 1)
    else:
        start_index = services.pages - page_per_echo + 1
    end_index = max(page_id + page_per_echo // 2, page_per_echo + 1)
    for number in range(start_index, end_index):
        if 0 < number <= services.pages:
            page_range_list.append(number)
    if services.items:
        start = (services.page - 1) * 10 + 1
        end = services.page * 10 if page_id != services.pages else services.total
    else:
        start = 0
        end = 0
    hosts_private = list(PrivateIp.query.values(PrivateIp.id, PrivateIp.ip))
    hosts_publish = list(PublishIp.query.values(PublishIp.id, PublishIp.ip))
    depends = list(Depend.query.values(Depend.id, Depend.name))
    domains = list(Domain.query.values(Domain.id, Domain.name))
    businesses = Business.choice_business_list(0, 3)
    return render_template('asset/app_list.html', hosts_private=hosts_private, hosts_publish=hosts_publish,
                           depends=depends, domains=domains, businesses=businesses, start=start,
                           end=end, services=services, page_range_list=page_range_list, fields=fields)


@asset.route('/app_create/', methods=['POST'])
@login_required
@admin_required
def app_create():
    data = json.loads(request.form.get('data'))
    _form = {}
    for _item in data['params']:
        if not (_item['name'].startswith('private_ip') or _item['name'].startswith('depend') or
                _item['name'].startswith('domain') or _item['name'].startswith('publish_ip')):
            _form[_item['name']] = _item['value']
    ret, error = Service.validate_service(_form, False)
    if ret:
        _hosts = set()
        _service = Service(**_form)
        if data['publish_ip']:
            for _id in data['publish_ip']:
                _publish_ip = PublishIp.query.get(int(_id))
                _service.publish_ips.append(_publish_ip)
                _hosts.add(_publish_ip.host)
        if data['private_ip']:
            for _id in data['private_ip']:
                _private_ip = PrivateIp.query.get(int(_id))
                _service.private_ips.append(_private_ip)
                _hosts.add(_private_ip.host)
        _service.domains.extend([Domain.query.get(int(_id)) for _id in data['domain']])
        _service.depends.extend([Depend.query.get(int(_id)) for _id in data['depend']])
        _service.hosts.extend(_hosts)
        db.session.add(_service)
        db.session.commit()
    return jsonify({'error': error})


@asset.route('/app_modify_list/', methods=['POST'])
@login_required
@admin_required
def app_modify_list():
    _id = request.form.get('id', type=int)
    _service = Service.query.get(_id)
    return jsonify(_service.to_modify_json())


@asset.route('/app_modify/', methods=['POST'])
@login_required
@admin_required
def app_modify():
    data = json.loads(request.form.get('data'))
    _form = {}
    for _item in data['params']:
        if not (_item['name'].startswith('private_ip') or _item['name'].startswith('depend') or
                _item['name'].startswith('domain') or _item['name'].startswith('publish_ip')):
            _form[_item['name']] = _item['value']
    ret, error = Service.validate_service(_form)
    if ret:
        _hosts = set()
        Service.query.filter_by(id=int(_form['id'])).update(_form)
        _service = Service.query.get(int(_form['id']))
        if _service.private_ips.count():
            for _ip in _service.private_ips.all():
                _ip.services.remove(_service)
        if _service.publish_ips.count():
            for _ip in _service.publish_ips.all():
                _ip.services.remove(_service)
        if _service.domains.count():
            for _domain in _service.domains.all():
                _domain.services.remove(_service)
        if _service.depends.count():
            for _depend in _service.depends.all():
                _depend.services.remove(_service)
        if _service.hosts.count():
            for _host in _service.hosts.all():
                _host.services.remove(_service)
        for _id in data['publish_ip']:
            _publish_ip = PublishIp.query.get(int(_id))
            _service.publish_ips.append(_publish_ip)
            _hosts.add(_publish_ip.host)
        for _id in data['private_ip']:
            _private_ip = PrivateIp.query.get(int(_id))
            _service.private_ips.append(_private_ip)
            _hosts.add(_private_ip.host)
        _service.domains.extend([Domain.query.get(int(_id)) for _id in data['domain']])
        _service.depends.extend([Depend.query.get(int(_id)) for _id in data['depend']])
        _service.hosts.extend(_hosts)
        db.session.commit()
        error = ''
    return jsonify({'error': error})


@asset.route('/app_delete_data/', methods=['POST'])
@login_required
@admin_required
def app_delete_data():
    _error = ''
    _id = request.form.get('id', type=int)
    _service = Service.query.get(_id)
    if not _service:
        _error = '应用不存在'
    else:
        db.session.delete(_service)
        db.session.commit()
    return jsonify({'error': _error})


@asset.route('/app_batch_delete_data/', methods=['POST'])
@login_required
@admin_required
def app_batch_delete_data():
    _error = ''
    _id_set = set(request.form.get('ids', '').split(','))
    if not _id_set:
        _error = '应用不存在'
    else:
        for _id in _id_set:
            if _id.isdigit():
                _id = int(_id)
                _service = Service.query.get(_id)
                if _service:
                    db.session.delete(_service)
        db.session.commit()
    return jsonify({'error': _error})


@asset.route('/app_batch_create/', methods=['GET', 'POST'])
@login_required
@admin_required
def app_batch_create():
    _error = ''
    if request.method == 'POST':
        if 'file' in request.files:
            _file = request.files['file']
            if _file.filename == '':
                _error = '上传文件为空'
            else:
                _name, _ext = os.path.splitext(_file.filename)
                _file.filename = md5(_name.encode()).hexdigest() + _ext
                file = datas.save(_file)
                file_path = os.path.join(current_app.config['UPLOADED_DATAS_DEST'], file)
                column = ['name', 'name_alias', 'port', 'private_ip', 'publish_ip', 'jdk', 'tomcat', 'resin',
                          'gbalancer', 'gluster', 'memcached', 'redis', 'cbase', 'business', 'domain',
                          'user', 'contact', 'contact_email', 'comment', 'company', 'db_instance']
                data_sheet_list, data_service_list = [], []
                error_total_list = []
                with xlrd.open_workbook(file_path) as f:
                    table = f.sheets()[0]
                    value_private_set = set(flatten([_ip.split() for _ip in table.col_values(3)[1:] if _ip]))
                    value_publish_set = set(flatten([_ip.split() for _ip in table.col_values(4)[1:] if _ip]))
                    value_table_list = [table.row_values(i) for i in range(1, table.nrows)]
                    for value in value_table_list:
                        if len(value) != len(column):
                            continue
                        data_sheet_list.append(dict(zip(column, value)))
                os.unlink(file_path)

                # 处理sheet的IP合法性
                error_private_ip_list, error_publish_ip_list = [], []
                value_private_list, value_publish_list = [], []
                if value_private_set:
                    for _ip in value_private_set:
                        _ip = _ip.strip()
                        if _ip:
                            ret, number = validate_ip(_ip)
                            if ret and number == 1:
                                if not PrivateIp.query.filter_by(ip=_ip).first():
                                    value_private_list.append(_ip)
                            else:
                                error_private_ip_list.append(_ip)
                if value_publish_set:
                    for _ip in value_publish_set:
                        _ip = _ip.strip()
                        if _ip:
                            ret, number = validate_ip(_ip)
                            if ret and number == 2:
                                if not PublishIp.query.filter_by(ip=_ip).first():
                                    value_publish_list.append(_ip)
                            else:
                                error_publish_ip_list.append(_ip)
                if error_private_ip_list:
                    error_total_list.append('内网错误IP: {}'.format(', '.join(error_private_ip_list)))
                if error_publish_ip_list:
                    error_total_list.append('公网错误IP: {}'.format(', '.join(error_publish_ip_list)))
                if error_total_list:
                    return render_template('asset/app_batch_create.html', error='\n'.join(error_total_list))

                # 处理产品信息
                error_business = []
                for data in data_sheet_list:
                    _service_name = data['name'].strip()
                    if _service_name:
                        _service_business = data['business'].strip()
                        _service_company = data['company'].strip()
                        if not _service_business or not _service_company:
                            error_business.append('应用{}所属产品为空'.format(_service_name))
                        else:
                            _company_business = Business.query.filter_by(name=_service_company).first()
                            _business = Business.query.filter_by(name=_service_business, pid=_company_business.id).first()
                            if not _business:
                                _business = Business(name=_service_business)
                                _business.pid = _company_business.id
                                _business.type = _company_business.type + 1
                                _business.product = '{},{}'.format(_company_business.product, str(_company_business.id))
                                _business.contact = data['contact_email'].strip()
                                db.session.add(_business)
                                db.session.commit()
                if error_business:
                    return render_template('asset/app_batch_create.html', error='\n'.join(error_business))

                # 处理sheet内部数据
                for data in data_sheet_list:
                    data_service_dict = {}
                    if not data['name'].strip():
                        continue
                    data_service_dict['name'] = data['name'].strip()
                    data_service_dict['name_alias'] = data['name_alias'].strip()
                    try:
                        data_service_dict['port'] = str(int(data['port']))
                    except:
                        data_service_dict['port'] = ''
                    data_service_dict['private_ip'] = data['private_ip'].split()
                    data_service_dict['publish_ip'] = data['publish_ip'].split()
                    data_service_dict['depend'] = []
                    for _key in ['jdk', 'tomcat']:
                        if data[_key]:
                            try:
                                value = str(int(data[_key]))
                                if value in ['6', '7', '8']:
                                    depend_name = '{}{}'.format(_key, value)
                                    _depend = Depend.query.filter_by(name=depend_name).first()
                                    data_service_dict['depend'].append(_depend)
                            except:
                                pass
                    for _key in ['resin', 'gbalancer', 'gluster', 'memcached', 'redis', 'cbase']:
                        if data[_key]:
                            try:
                                value = data[_key].strip()
                                if value == '是':
                                    _depend = Depend.query.filter_by(name=_key).first()
                                    data_service_dict['depend'].append(_depend)
                            except:
                                pass
                    data_service_dict['business_id'] = Business.query.filter_by(
                        name=data['business'].strip(), 
                        pid=Business.query.filter_by(name=data['company'].strip()).first().id).first().id
                    data_service_dict['domain'] = []
                    domain_name_list = data['domain'].split()
                    for _name in domain_name_list:
                        if checkurl(_name):
                            _domain = Domain.query.filter_by(name=_name).first()
                            if not _domain:
                                _domain = Domain(name=_name)
                                db.session.add(_domain)
                                db.session.commit()
                            data_service_dict['domain'].append(_domain)
                    if data['user'].strip() and data['user'].islower():
                        _user = ServiceUser.query.filter_by(name=data['user'].strip()).first()
                        if not _user:
                            _user = ServiceUser(name=data['user'].strip())
                            db.session.add(_user)
                            db.session.commit()
                        data_service_dict['user_id'] = _user.id
                    else:
                        data_service_dict['user_id'] = ServiceUser.query.filter_by(name='root').first().id
                    for key in ['contact_email', 'contact']:
                        data_service_dict[key] = ' '.join(data[key].split(','))
                    if data['db_instance'].strip() == '无':
                        data_service_dict['db_instance'] = ''
                    else:
                        data_service_dict['db_instance'] = ' '.join(data['db_instance'].split(','))
                    data_service_dict['status'] = 0
                    data_service_dict['priority_id'] = Priority.query.filter_by(name='高').first().id
                    data_service_list.append(data_service_dict)

                # 调用灵枢API接口
                try:
                    for data_service in data_service_list:
                        _service = Service.query.filter_by(name=data_service['name'], business_id=data_service['business_id']).first()
                        if _service:
                            db.session.delete(_service)
                        _items, _hosts = {}, set()
                        for key, value in data_service.items():
                            if not (key == 'publish_ip' or key == 'private_ip' or key == 'depend' or key == 'domain'):
                                _items[key] = value
                        _service_new = Service(**_items)
                        if data_service['publish_ip']:
                            _data = stats_api_lingshu(set(data_service['publish_ip']))
                            if _data:
                                _mess_list = Host.batch_create_host(_data)
                                for _mess_dict in _mess_list:
                                    if _mess_dict:
                                        _items = {}
                                        for key, value in _mess_dict.items():
                                            if not (key == 'publish_ip' or key == 'private_ip' or key == 'vip_ip'):
                                                _items[key] = value
                                        _host = Host.query.filter_by(name=_mess_dict['name']).first()
                                        if not _host:
                                            _host = Host(**_items)
                                            db.session.add(_host)
                                            if _mess_dict['publish_ip']:
                                                for ip in _mess_dict['publish_ip']:
                                                    _publish_ip = PublishIp.filter_by(ip=ip).first()
                                                    if not _publish_ip:
                                                        _publish_ip = PublishIp(ip=ip)
                                                        db.session.add(_publish_ip)
                                                    _host.publish_ips.append(_publish_ip)
                                            if _mess_dict['private_ip']:
                                                for ip in _mess_dict['private_ip']:
                                                    _private_ip = PrivateIp.filter_by(ip=ip).first()
                                                    if not _private_ip:
                                                        _private_ip = PrivateIp(ip=ip)
                                                        db.session.add(_private_ip)
                                                    _host.private_ips.append(_private_ip)
                                            if _mess_dict['vip_ip']:
                                                for ip in _mess_dict['vip_ip']:
                                                    _vip_ip = VipIp.query.filter_by(ip=ip).first()
                                                    if not _vip_ip:
                                                        _vip_ip = VipIp(ip=ip)
                                                        db.session.add(_vip_ip)
                                                    _host.vip_ips.append(_vip_ip)
                                        _host.business_id = data_service['business_id']
                            for ip in data_service['publish_ip']:
                                _publish_ip = PublishIp.query.filter_by(ip=ip).first()
                                try:
                                    _hosts.add(_publish_ip.host)
                                    _service_new.publish_ips.append(_publish_ip)
                                except:
                                    pass
                        if data_service['private_ip']:
                            _data = stats_api_lingshu(list(set(data_service['private_ip'])))
                            if _data:
                                _mess_list = Host.batch_create_host(_data)
                                for _mess_dict in _mess_list:
                                    if _mess_dict:
                                        _items = {}
                                        for key, value in _mess_dict.items():
                                            if not (key == 'publish_ip' or key == 'private_ip' or key == 'vip_ip'):
                                                _items[key] = value
                                        _host = Host.query.filter_by(name=_mess_dict['name']).first()
                                        if not _host:
                                            _host = Host(**_items)
                                            db.session.add(_host)
                                            if _mess_dict['publish_ip']:
                                                for ip in _mess_dict['publish_ip']:
                                                    _publish_ip = PublishIp.query.filter_by(ip=ip).first()
                                                    if not _publish_ip:
                                                        _publish_ip = PublishIp(ip=ip)
                                                        db.session.add(_publish_ip)
                                                    _host.publish_ips.append(_publish_ip)
                                            if _mess_dict['private_ip']:
                                                for ip in _mess_dict['private_ip']:
                                                    _private_ip = PrivateIp.query.filter_by(ip=ip).first()
                                                    if not _private_ip:
                                                        _private_ip = PrivateIp(ip=ip)
                                                        db.session.add(_private_ip)
                                                    _host.private_ips.append(_private_ip)
                                            if _mess_dict['vip_ip']:
                                                for ip in _mess_dict['vip_ip']:
                                                    _vip_ip = VipIp.query.filter_by(ip=ip).first()
                                                    if not _vip_ip:
                                                        _vip_ip = VipIp(ip=ip)
                                                        db.session.add(_vip_ip)
                                                    _host.vip_ips.append(_vip_ip)
                                        _host.business_id = data_service['business_id']
                            for ip in data_service['private_ip']:
                                _private_ip = PrivateIp.query.filter_by(ip=ip).first()
                                try:
                                    _hosts.add(_private_ip.host)
                                    _service_new.private_ips.append(_private_ip)
                                except:
                                    pass
                        if data_service['domain']:
                            _service_new.domains.extend(data_service['domain'])
                        if data_service['depend']:
                            _service_new.depends.extend(data_service['depend'])
                        if _hosts:
                            _service_new.hosts.extend(_hosts)
                        db.session.add(_service_new)
                    db.session.commit()
                    return redirect(url_for('asset.app_list'))
                except Exception as e:
                    print(e.args)
                    db.session.rollback()
                    _error = '批量添加操作异常'
    return render_template('asset/app_batch_create.html', error=_error)


@asset.route('/app_check/')
@login_required
@admin_required
def app_check():
    businesses = Business.choice_business_list(0, 3)
    return render_template('/asset/app_check.html', businesses=businesses)


@asset.route('/app_check_data/')
@login_required
@admin_required
def app_check_data():
    services = ServiceAgent.query.filter(ServiceAgent.state < 2).order_by(ServiceAgent.change_time.desc())
    if services.all():
        data = [_service.to_json() for _service in services]
    else:
        data = ''
    return jsonify({'data': data})


@asset.route('/check_modify_list/', methods=['POST'])
@login_required
@admin_required
def check_modify_list():
    _id = request.form.get('id', type=int)
    _service_id = request.form.get('service', type=int)
    _service = Service.query.get(_service_id)
    if _service:
        _result_dict = _service.to_modify_json()
        _result_dict['agent_id'] = _id
        return jsonify(_result_dict)
    return jsonify('')


@asset.route('/check_update_data/', methods=['POST'])
@login_required
@admin_required
def check_update_data():
    error, _form = '', {}
    data = json.loads(request.form.get('data'))
    print(data)
    if not data:
        error = '更新数据为空'
    else:
        for _item in data['params']:
            if _item['name'] == 'agent_id':
                agent_id = _item['value']
                continue
            if not (_item['name'].startswith('private_ip') or _item['name'].startswith('depend') or 
                    _item['name'].startswith('domain') or _item['name'].startswith('publish_ip')):
                _form[_item['name']] = _item['value']
        ret, error = Service.validate_service(_form)
        if ret:
            _hosts = set()
            _service = Service.query.get(_form['id'])
            if _service:
                Service.query.filter_by(id=int(_form['id'])).update(_form)
                if _service.private_ips.count():
                    for _ip in _service.private_ips.all():
                        _ip.services.remove(_service)
                if _service.publish_ips.count():
                    for _ip in _service.publish_ips.all():
                        _ip.services.remove(_service)
                if _service.domains.count():
                    for _domain in _service.domains.all():
                        _domain.services.remove(_service)
                if _service.depends.count():
                    for _depend in _service.depends.all():
                        _depend.services.remove(_service)
                if _service.hosts.count():
                    for _host in _service.hosts.all():
                        _host.services.remove(_service)
                for _id in data['publish_ip']:
                    _publish_ip = PublishIp.query.get(int(_id))
                    _service.publish_ips.append(_publish_ip)
                    _hosts.add(_publish_ip.host)
                for _id in data['private_ip']:
                    _private_ip = PrivateIp.query.get(int(_id))
                    _service.private_ips.append(_private_ip)
                    _hosts.add(_private_ip.host)
                _service.domains.extend([Domain.query.get(int(_id)) for _id in data['domain']])
                _service.depends.extend([Depend.query.get(int(_id)) for _id in data['depend']])
                _service.hosts.extend(_hosts)
                _agent = ServiceAgent.query.get(agent_id)
                if _agent:
                    _agent.state = 1
                    _agent.check_user = current_user.name    
                db.session.commit()
    return jsonify({'error': error})
            

@asset.route('/check_delete_data/', methods=['POST'])
@login_required
@admin_required
def check_delete_data():
    error = '' 
    _id = request.form.get('id', default=-1, type=int)
    _agent = ServiceAgent.query.get(_id)
    if _agent:
        _agent.state = 2
        _agent.check_user = current_user.name
        db.session.commit()
    else:
        error = '删除记录不存在'
    return jsonify({'error': error})
