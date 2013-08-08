#!/usr/bin/env python
# -*- encoding: utf-8 -*-

from werkzeug import Response

import re
import json
import base64
import struct

from os.path import isfile
from hashlib import sha1


def encode(uid):
    if re.search('[^A-Z0-9._-]', uid, re.I):
        return base64.b32encode(sha1(uid).digest()).lower()
    return uid


class login:
    """login decorator using HTTP Basic Authentication. Pattern based on
    http://flask.pocoo.org/docs/patterns/viewdecorators/"""

    def __init__(self, methods=['GET', 'POST', 'DELETE', 'PUT']):
        self.methods = methods

    def __call__(self, f):

        def dec(app, env, req, *args, **kwargs):
            """This decorater function will send an authenticate header, if none
            is present and denies access, if HTTP Basic Auth fails."""
            if req.method not in self.methods:
                return f(app, env, req, *args, **kwargs)
            if not req.authorization:
                response = Response('Unauthorized', 401)
                response.www_authenticate.set_basic('Weave')
                return response
            else:
                user = req.authorization.username
                passwd = req.authorization.password
                if not isfile(app.dbpath(user, passwd)):
                    return Response('Unauthorized', 401)  # kinda stupid
                return f(app, env, req, *args, **kwargs)
        return dec


def wbo2dict(query):
    """converts sqlite table to WBO (dict [json-parsable])"""

    res = {'id': query[0], 'modified': round(query[1], 2),
           'sortindex': query[2], 'payload': query[3],
           'parentid': query[4], 'predecessorid': query[5], 'ttl': query[6]}

    for key in res.keys()[:]:
        if res[key] is None:
            res.pop(key)

    return res


def convert(value, mime):
    """post processor producing lists in application/newlines format."""

    if mime and mime.endswith(('/newlines', '/whoisi')):
        try:
            value = value["items"]
        except (KeyError, TypeError):
            pass

        if mime.endswith('/whoisi'):
            res = []
            for record in value:
                js = json.dumps(record)
                res.append(struct.pack('!I', len(js)) + js)
            rv = ''.join(res)
        else:
            rv = '\n'.join(json.dumps(item).replace('\n', '\000a') for item in value)
    else:

        rv, mime = json.dumps(value), 'application/json'

    return rv, mime, len(value)
