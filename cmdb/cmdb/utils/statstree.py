# coding=utf-8

import requests
import sys

INFOURL="http://ump.letv.cn/cmdb/servicetree/getNodeInfo/"
DEVICEURL="http://ump.letv.cn/cmdb/servicetree/getNodeDevice/"


def stats_tree(id):
    url = '{}{}'.format(INFOURL, id)
    results = requests.post(url, timeout=5)
    if results.status_code == 200:
        datas = results.json()
        if datas['status'] == 1:
            return datas['data']
    return ''


if __name__ == '__main__':
    id = sys.argv[1]
    data = stats_tree(id)
    print(data)
