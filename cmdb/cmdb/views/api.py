# coding=utf-8

from funcy import flatten
from flask import jsonify, Blueprint, make_response, request
from flask_httpauth import HTTPTokenAuth
from flask_restful import Api, Resource
from .. import db
from ..models import ApiUser, PrivateIp, Business, ServiceAgent, Service, Host, PublishIp
from .raw_sql import *

auth = HTTPTokenAuth(scheme='Token')
api_bp = Blueprint('api', __name__)
api = Api(api_bp)


@auth.verify_token
def verify_token(token):
    try:
        return ApiUser.verify_api_token(token)
    except:
        return False


@auth.error_handler
def unauthorized():
    return make_response(jsonify({'error': 'Unauthorized'}), 401)


def service_info_stats():
    company_list = []
    company_id_list = flatten(Business.query.filter_by(pid=1).values(Business.id))
    if company_id_list:
        _results = db.session.execute(CHOICE_HOST_TYPE_DATA).fetchall()
        _host_pyhsics_set = set([str(_result[0]) for _result in _results])
        for company_id in company_id_list:
            business_id_list = [mess[0] for mess in Business.query.filter(Business.type > 1).values(
                Business.id, Business.product) if str(company_id) in mess[1].split(',')]
            if not business_id_list:
                continue
            company_service_total, company_host_physics, company_host_vms = 0, set(), set()
            _company_dict, item_list = {}, []
            for business_id in business_id_list:
                _sql = BUSINESS_SERVICE_HOST_DATA.format(business_id)
                _rets = db.session.execute(_sql).fetchall()
                for _ret in _rets:
                    _business_dict = {}
                    _business_dict['business_name'] = _ret[0]
                    _business_dict['business_service'] = {'total': _ret[1]}
                    _host_set = set(_ret[-1].split(','))
                    _physics_set = _host_set.intersection(_host_pyhsics_set)
                    _vms_set = _host_set.difference(_host_pyhsics_set)
                    _business_dict['business_host'] = {'total': len(_host_set),
                                                       'physics': len(_physics_set), 'vms': len(_vms_set)}
                    item_list.append(_business_dict)
                    company_host_physics.update(_physics_set)
                    company_host_vms.update(_vms_set)
                    company_service_total += _ret[1]
            _company_dict['company_name'] = Business.query.get(company_id).name
            _company_dict['company_host'] = {'total': len(company_host_physics) + len(company_host_vms),
                                             'physics': len(company_host_physics), 'vms': len(company_host_vms)}
            _company_dict['company_service'] = {'total': company_service_total}
            _company_dict['items'] = item_list
            company_list.append(_company_dict)
    return company_list


def get_token():
    try:
        _apiuser = ApiUser.query.get(1)
        _token = _apiuser.generate_api_token().decode()
    except:
        _token = ''
    return {'token': _token}


class ServiceInfo(Resource):
    decorators = [auth.login_required]

    def post(self):
        return service_info_stats()
                    

class CreateToken(Resource):
    
    def get(self):
        return get_token()        


class GetAppInfo(Resource):
    decorators = [auth.login_required]

    def get(self):
        ip = request.args.get('ip', '')
        if not ip:
            return {'msg': 'IP参数为空', 'status': 1}
        private_ip = PrivateIp.query.filter_by(ip=ip).first()
        if not private_ip or not private_ip.services.count():
            return {'data': '', 'status': 0}
        _column = ['service_id', 'name', 'name_alias', 'port', 'business_id', 'business', 'priority_id',
                   'priority', 'user_id', 'user', 'contact', 'contact_email', 'comment',
                   'db_instance', 'status', 'private_ip', 'publish_ip', 'depend', 'domain']
        _sql = SERVICE_IP_DATA.format(ip)
        _results = db.session.execute(_sql).fetchall()
        data = [dict(zip(_column, _result)) for _result in _results]
        return {'data': data, 'status': 0}


class PostAppInfo(Resource):
    decorators = [auth.login_required]

    def post(self):
        _message = request.json
        if _message and _message['data']:
            for data in _message['data']:
                portstatus = data.get('portstatus', '')
                dependstatus = data.get('dependstatus', '')
                if not portstatus or not dependstatus:
                    continue
                depend_true_list, depend_false_list = [], []
                for depend in dependstatus:
                    for key, value in depend.items():
                        if value == 'true':
                            depend_true_list.append(key.strip('.0'))
                        else:
                            depend_false_list.append(key.strip('.0'))
                if portstatus == 'true' and not depend_false_list:
                    continue
                else:
                    try:
                        _items = {}
                        name = data.get('name', '')
                        business_id = data.get('business_id', '')
                        _old_agent = ServiceAgent.query.filter(ServiceAgent.name == name,
                                                               ServiceAgent.business_id == business_id,
                                                               ServiceAgent.state == 0)
                        if _old_agent.count():
                            _old_agent.delete()
                        for key, value in data.items():
                            if key not in ['portstatus', 'dependstatus', 'depend']:
                                if isinstance(value, (int, float)):
                                    _items[key] = int(value)
                                else:
                                    _items[key] = value.strip()
                        _agent = ServiceAgent(**_items)
                        _agent.depend = ','.join(depend_true_list)
                        db.session.add(_agent)
                    except:
                        return {'msg': '异常数据IP:{}'.format(data.get('private_ip', '')), 'status': 1}
                    else:
                        db.session.commit()
            return {'data': '', 'status': 0}
        else:
            return {'msg': '数据提交为空', 'status': 1}


class GetCmdCompanyInfo(Resource):
    decorators = [auth.login_required]

    def get(self):
        result = []
        try:
            businesses = Business.query.filter_by(type=1).all()
            if businesses: 
                result = [{'id': _business.id, 'name': _business.name} for _business in businesses]
            return {'data': result, 'status': 1}
        except:
            return {'data': [], 'status': 0}


class GetCmdProductInfo(Resource):
    decorators = [auth.login_required]
    
    def get(self):
        result = []
        try:
            businesses = Business.query.filter(Business.type > 1).all()
            if businesses:
                for _business in businesses:
                    _names = []
                    products = _business.product.split(',')[1:]
                    for id in products:
                        _names.append(Business.query.get(id).name)
                    _names.append(_business.name)
                    result.append({'id': _business.id, 'name': '__'.join(_names)}) 
            return {'data': result, 'status': 1}
        except:
            return {'data': [], 'status': 0}    


def _service_host_info(host_id):
    _host = Host.query.get(host_id)
    if _host:
        _host_dict = {}
        _host_dict['host_id'] = _host.id
        _host_dict['env'] = _host.env.name
        _host_dict['private_ip'] = ','.join(list(flatten(_host.private_ips.values(PrivateIp.ip))))
        _host_dict['publish_ip'] = ','.join(list(flatten(_host.publish_ips.values(PublishIp.ip))))
        return _host_dict
    else:
        return ''


class GetCmdServiceInfo(Resource):
    decorators = [auth.login_required]

    def get(self):
        result = []
        service_name = request.args.get('service', '').strip()
        host_id = request.args.get('host_id', '').strip()
        try:
            if service_name:
                if host_id:
                    _host = Host.query.get(host_id)
                    if _host:
                        try:
                            for _service in _host.services:
                                if _service.name == service_name:
                                    _service_dict = {'service_id': _service.id, 'name': _service.name}
                                    _hosts = []
                                    _hosts.append(_service_host_info(_host.id))
                                    _service_dict['hosts'] = _hosts
                                    result.append(_service_dict)
                                    break
                        except:
                            pass
                else:
                    _services = Service.query.filter_by(name=service_name).all()
                    if _services:
                        for _service in _services:
                            _service_dict = {'service_id': _service.id, 'name': _service.name}
                            _hosts = []
                            try:
                                for _host in _service.hosts:
                                    _hosts.append(_service_host_info(_host.id))
                            finally:
                                _service_dict['hosts'] = _hosts
                                result.append(_service_dict)
            return {'data': result, 'status': 1}
        except:
            return {'data': [], 'status': 0}


class GetCmdHostInfo(Resource):
    decorators = [auth.login_required]

    def get(self):
        result = []
        ips = request.args.get('ip', '').strip()
        try:
            if ips:
                for ip in ips.split(','):
                    host_dict = {}
                    private_ip = PrivateIp.query.filter_by(ip=ip).first()
                    if private_ip:
                        host_dict['env'] = private_ip.host.env.name
                        host_dict['services'] = ','.join(list(flatten(private_ip.host.services.values(Service.name))))
                        host_dict['ip'] = ip
                        result.append(host_dict)
                        continue   
                    publish_ip = PublishIp.query.filter_by(ip=ip).first()
                    if publish_ip:
                        host_dict['env'] = publish_ip.host.env.name 
                        host_dict['services'] = ','.join(list(flatten(publish_ip.host.services.values(Service.name))))
                        host_dict['ip'] = ip
                        result.append(host_dict)
                        continue  
            return {'data': result, 'status': 1}
        except:
            return {'data': [], 'status': 0} 


api.add_resource(ServiceInfo, '/serviceinfo/')
api.add_resource(CreateToken, '/token/')
api.add_resource(GetAppInfo, '/getAppInfo/')
api.add_resource(PostAppInfo, '/checkAppInfo/')
api.add_resource(GetCmdCompanyInfo, '/getCmdCompany/')
api.add_resource(GetCmdProductInfo, '/getCmdProduct/')
api.add_resource(GetCmdServiceInfo, '/getCmdService/')
api.add_resource(GetCmdHostInfo, '/getCmdHost/')
