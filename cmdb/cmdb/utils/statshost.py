# coding=utf-8

import requests
import sys

BASEURL = "http://lingshu.letv.cn/cmdb/cmdbservicetree/devinfo"


def stats_api_lingshu(ips):
    params = {'link_token': '659048a0f13e910f2907d3ade3d660b7', 'type': 'ip'}
    if len(ips) == 1:
        params['list'] = ips[0].strip()
    else:
        params['list'] = ','.join(ips)
    results = requests.get(BASEURL, params=params, timeout=2)
    if results.status_code == 200:
        datas = results.json()
        if datas['data'] != 'null':
            return datas['data']
    return []


if __name__ == '__main__':
    ips = sys.argv[1:]
    data = stats_api_lingshu(ips)
    print(data)
