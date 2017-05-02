# coding=utf-8

import re
import sys


def checkurl(url):
    url = url.split('/')[0].split(':')[0]
    pattern = re.compile(r'^(?=^.{3,255}$)[a-zA-Z0-9][-a-zA-Z0-9]{0,62}(\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62})+$')
    ret = pattern.search(url)
    if ret:
        return True
    else:
        return False


if __name__ == '__main__':
    ret = checkurl(sys.argv[1])
    print(ret)
