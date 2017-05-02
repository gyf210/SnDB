# coding=utf-8

from funcy import flatten
from flask import jsonify, Blueprint, make_response, request
from flask_httpauth import HTTPTokenAuth
from flask_restful import Api, Resource
from .. import db
from ..models import ApiUser, PrivateIp, Business, ServiceAgent
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


api.add_resource(ServiceInfo, '/serviceinfo/')
api.add_resource(CreateToken, '/token/')
api.add_resource(GetAppInfo, '/getAppInfo/')
api.add_resource(PostAppInfo, '/checkAppInfo/')
