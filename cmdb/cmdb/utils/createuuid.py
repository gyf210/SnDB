# coding=utf-8

import os
import uuid


def createuuid():
    return uuid.uuid3(uuid.NAMESPACE_DNS, os.urandom(32).hex()).hex
