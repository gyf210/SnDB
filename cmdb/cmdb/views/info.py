# coding=utf-8

from funcy import flatten
from flask import Blueprint, request, render_template, jsonify
from flask_login import login_required
from ..models import Idc, Host, Business, Service, PrivateIp
from .. import db
from .raw_sql import *


info = Blueprint('info', __name__)


@info.route('/info_list/')
@login_required
def info_list():
    idcs = [{'id': idc.id, 'name': idc.name} for idc in Idc.query.all()]
    # pyhsics_id = HostType.query.filter_by(name='物理机').first().id
    # vms_id = HostType.query.filter_by(name='虚拟机').first().id
    # pyhsics = [{'idc_id': host.idc_id, 'private_ip': list(flatten(host.private_ips.values(PrivateIp.ip))),
    # 'publish_ip': list(flatten(host.publish_ips.values(PublishIp.ip)))}
    # for host in Host.query.filter_by(host_type_id=pyhsics_id).all()]
    # vms = [{'idc_id': host.idc_id, 'private_ip': list(flatten(host.private_ips.values(PrivateIp.ip))),
    # 'publish_ip': list(flatten(host.publish_ips.values(PublishIp.ip)))}
    # for host in Host.query.filter_by(host_type_id=vms_id).all()]
    apps = [{'name': service.name, 'idc_id': list(set(flatten(service.hosts.values(Host.idc_id))))}
            for service in Service.query.all()]
    companys = list({'id': str(company.id), 'name': company.name} for company in Business.query.filter_by(pid=1))
    businesses = list({'company_id': business.product.split(',')[1], 'id': business.id, 'name': business.name}
                      for business in Business.query.filter(Business.type > 1))
    services = list({'business_id': service[0], 'id': service[1], 'name': service[2]}
                    for service in Service.query.values(Service.business_id, Service.id, Service.name))
    return render_template('info/info_tree.html', idcs=idcs, companys=companys,
                           businesses=businesses, services=services, apps=apps)


@info.route('/host_list/')
@login_required
def host_list():
    return render_template('info/info_host.html')


@info.route('/idc_data_list/')
@login_required
def idc_data_list():
    idcs = [{'value': -1, 'name': '全部'}]
    idcs.extend([{'value': idc[0], 'name': idc[1]} for idc in Idc.query.values(Idc.id, Idc.name)])
    return jsonify(idcs)


@info.route('/service_data_list/')
@login_required
def service_data_list():
    idc_id = request.args.get('idc', type=int)
    businesses = []
    businesses.append({'value': -1, 'name': '全部'})
    if idc_id == -1:
        _businesses = Business.query.filter(Business.type > 1).all()
        businesses.extend([{'value': _business.id, 'name': _business.name} for _business in _businesses])
    else:
        _services = set(list(flatten(_host.services.all() for _host in Host.query.filter_by(idc_id=idc_id))))
        _businesses = set([service.business for service in _services])
        businesses.extend([{'value': _business.id, 'name': _business.name} for _business in _businesses])
    ret_data = {'state': 'success', 'data': businesses}
    return jsonify(ret_data)


@info.route('/host_data_list/')
@login_required
def host_data_list():
    idc_id = request.args.get('idc', type=int)
    hosts = []
    hosts.append({'value': -1, 'name': '全部'})
    if idc_id == -1:
        hosts.extend([{'value': ip[0], 'name': ip[1]} for ip in PrivateIp.query.values(PrivateIp.host_id, PrivateIp.ip)])
    else:
        hosts.extend([{'value': host.id, 'name': ','.join(list(host.private_ips.values(PrivateIp.ip))[0])}
                      for host in Host.query.filter_by(idc_id=idc_id)])
    ret_data = {'state': 'success', 'data': hosts}
    return jsonify(ret_data)


@info.route('/host_data/')
@login_required
def host_data():
    data = ''
    return jsonify({'data': data})


@info.route('/host_new_data/')
@login_required
def host_new_data():
    idc_id = request.args.get('idc', type=int)
    host_id = request.args.get('host', type=int)
    _column = ['id', 'name', 'cpu', 'memory', 'disk', 'private_ip', 'publish_ip', 'vip_ip', 'host_ip', 'idc',
               'host_type', 'system', 'env', 'status', 'comment', 'business', 'service', 'owner']
    if idc_id == -1:
        if host_id == -1:
            _results = db.session.execute(HOST_TOTAL_DATA).fetchall()
            data = [dict(zip(_column, _result)) for _result in _results]
        elif not host_id:
            data = ''
        else:
            _sql = HOST_BUSINESS_DATA.format(host_id)
            _results = db.session.execute(_sql).fetchall()
            data = [dict(zip(_column, _result)) for _result in _results]
    elif not idc_id:
        if host_id == -1:
            _results = db.session.execute(HOST_TOTAL_DATA).fetchall()
            data = [dict(zip(_column, _result)) for _result in _results]
        else:
            data = ''
    else: 
        if host_id == -1:
            _sql = IDC_ID_DATA.format(idc_id)
            _results = db.session.execute(_sql).fetchall()
            data = [dict(zip(_column, _result)) for _result in _results]
        elif not host_id:
            data = ''
        else:
            _sql = HOST_ID_DATA.format(host_id, idc_id)
            _results = db.session.execute(_sql).fetchall()
            data = [dict(zip(_column, _result)) for _result in _results]
    return jsonify({'data': data})


@info.route('/service_list/')
@login_required
def service_list():
    return render_template('info/info_service.html')


@info.route('/service_data/')
@login_required
def service_data():
    data = ''
    return jsonify({'data': data})


@info.route('/company_data_list/')
@login_required
def company_data_list():
    companys = []
    companys.extend([{'value': _company.id, 'name': _company.name} for _company in Business.query.filter_by(pid=1)])
    return jsonify(companys)


@info.route('/business_data_list/')
@login_required
def business_data_list():
    company_id = request.args.get('company', type=int)
    businesses = []
    businesses.append({'value': -1, 'name': '全部'})
    businesses.extend([{'value': _business.id, 'name': _business.name} for _business in
                       Business.query.filter(Business.type > 1) if str(company_id) in _business.product.split(',')])
    ret_data = {'state': 'success', 'data': businesses}
    return jsonify(ret_data)


@info.route('/service_new_data/')
@login_required
def service_new_data():
    company_id = request.args.get('company', type=int)
    business_id = request.args.get('business', type=int)
    _column = ['id', 'name', 'name_alias', 'port', 'business', 'priority', 'user', 'contact', 'contact_email',
               'status', 'comment', 'db_instance', 'private_ip', 'publish_ip', 'depend', 'domain']
    if company_id:
        if business_id == -1:
            _sql = COMPANY_ID_DATA.format(str(company_id))
            _results = db.session.execute(_sql).fetchall()
            data = [dict(zip(_column, _result)) for _result in _results]
        elif not business_id:
            data = ''
        else:
            _sql = BUSINESS_ID_DATA.format(business_id)
            _results = db.session.execute(_sql).fetchall()
            data = [dict(zip(_column, _result)) for _result in _results]
    else:
        if business_id == -1:
            _results = db.session.execute(APP_COMPANY_TOTAL_DATA).fetchall()
            data = [dict(zip(_column, _result)) for _result in _results]
        else:
            data = ''
    return jsonify({'data': data})


@info.route('/show_list/')
@login_required
def show_list():
    return render_template('info/show_list.html')


@info.route('/show_host_data/', methods=['POST'])
@login_required
def show_host_data():
    message = []
    for idc in Idc.query.all():
        try:
            message.append({'name': idc.name, 'value': idc.hosts.count()})
        except:
            message.append({'name': idc.name, 'value': 0})
    if message:
        data = {'error': '', 'message': message}
    else:
        data = {'error': 1}
    return jsonify(data)


@info.route('/show_service_data/', methods=['POST'])
@login_required
def show_service_data():
    message = []
    for business in Business.query.filter(Business.type > 1).all():
        try:
            message.append({'name': business.name, 'value': business.services.count()})
        except:
            message.append({'name': business.name, 'value': 0})
    if message:
        data = {'error': '', 'message': message}
    else:
        data = {'error': 1}
    return jsonify(data)


