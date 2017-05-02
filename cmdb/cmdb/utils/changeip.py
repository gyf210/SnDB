# coding=utf-8

import socket
import struct
from IPy import IP


def ip2int(ip):
    try:
        number = struct.unpack("!I", socket.inet_aton(ip))[0]
    except:
        number = 0
    return number


def int2ip(number):
    try:
        if number == 0:
            return ''
        ip = socket.inet_ntoa(struct.pack("!I", number))
    except:
        ip = ''
    return ip


def validate_ip(ip):
    if '.' not in ip or len(ip.split(".")) != 4:
        return False, 0
    try:
        _ip = IP(ip)
        if _ip.iptype() == 'PRIVATE':
            return True, 1
        elif _ip.iptype() == 'PUBLIC':
            return True, 2
    except:
        return False, 0
    else:
        return False, 0
