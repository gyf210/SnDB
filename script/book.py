#coding: utf-8

import argparse
import requests
import json
import pprint


class ApiCmdbUrl:

    def __init__(self, host="127.0.0.1", port=9000):
        self._host = host
        self._port = port
        self._url = "http://{}:{}/api/v1".format(self._host, self._port)
        self._apis = ["getCmdCompany", "getCmdProduct", "getCmdService", "getCmdHost", "token"]

    def __call__(self):
        stats = {}
        for _api in self._apis:
            stats[_api] = "{}/{}/".format(self._url, _api)
        return stats


def getToken():
    token = ""
    apiurl = ApiCmdbUrl()
    url = apiurl()["token"]
    try:
        result = requests.get(url, timeout=3)
        if result.status_code == 200:
            token = result.json()["token"]
    except:
        pass
    return token


class QueryCmdbMessage:
    
    def __init__(self, url="", data=""):
        apiurl = ApiCmdbUrl()
        self.url = apiurl().get(url, "")
        self.data = data
        self.token = getToken()

    def __call__(self):
        data = ""
        if not self.url:
            return False, "查询接口URL为空"
        if not self.token:
            return False, "查询鉴权Token为空"
        try:
            headers = {"Authorization": "Token {}".format(self.token)}
            result = requests.get(url=self.url, params=self.data, headers=headers, timeout=3)
            if result.status_code == 200:
                data = result.json()
        except:
            return False, "查询系统内部错误"
        return True, data


def main():
    parser = argparse.ArgumentParser(prog="book", description="Query Cmdb Data Command: book")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-c", "--company", help="show company information", action="store_true", default=False, dest="company")
    group.add_argument("-p", "--product", help="show product information", action="store_true", default=False, dest="product")
    group.add_argument("-s", "--service", help="show service information", default="", dest="service")
    parser.add_argument("--id", help="show specific service host information", nargs="?", default="", dest="host_id")
    group.add_argument("-H", "--host", help="show host information", nargs="+", default="", dest="host")
    args = parser.parse_args()
    if args.company:
        query = QueryCmdbMessage("getCmdCompany")
        state, data = query()
        if state:
            pprint.pprint(data)
        else:
            pprint.pprint({'error': data, 'data': '', 'status': 0})
    elif args.product:
        query = QueryCmdbMessage("getCmdProduct")
        state, data = query()
        if state:
            pprint.pprint(data)
        else:
            pprint.pprint({'error': data, 'data': '', 'status': 0})
    elif args.host:
        hosts = args.host
        data = {"ip": ",".join(hosts)}
        query = QueryCmdbMessage("getCmdHost", data=data)
        state, data = query()
        if state:
            pprint.pprint(data)
        else:
            pprint.pprint({'error': data, 'data': '', 'status': 0})
    elif args.service:
        if args.host_id:
            host_id = args.host_id.strip()
        else:
            host_id = ""
        service = args.service.strip()
        data = {"service": service, "host_id": host_id}
        query = QueryCmdbMessage("getCmdService", data=data)
        state, data = query()
        if state:
            pprint.pprint(data)
        else:
            pprint.pprint({'error': data, 'data': '', 'status': 0})
    elif args.host_id and not args.service:
        print('usage: book [-s SERVICE] --id [HOST_ID]')
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
