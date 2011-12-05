#!/usr/bin/env python
# -*- encoding: utf-8 -*-

from werkzeug import Response
from utils import login, WeaveStorage, path, wbo2dict
import sqlite3, time

try:
    import json
except ImportError:
    import simplejson as json

WEAVE_INVALID_WRITE = "4"         # Attempt to overwrite data that can't be
WEAVE_MALFORMED_JSON = "6"        # Json parse failure

# XXX no-go!
storage = WeaveStorage()


@login(['GET', ])
def get_collections_info(environ, request, version, uid):
    """Returns a hash of collections associated with the account,
    Along with the last modified timestamp for each collection.
    """
    if request.authorization.username != uid:
        return Response('Not Authorized', 401)
    passwd = request.authorization.password
    dbpath = path(environ['data_dir'], uid, passwd)

    collections = storage.get_collection_info(dbpath)
    return Response(json.dumps(collections), 200, content_type='application/json; charset=utf-8',
                    headers={'X-Weave-Records': str(len(collections))})


# XXX
@login(['GET', ])
def get_collections_count(environ, request, version, uid):
    """Returns a hash of collections associated with the account,
    Along with the total number of items for each collection.
    """
    if request.authorization.username != uid:
        return Response('Not Authorized', 401)
    counts = storage.get_collection_counts(environ['data_dir'], uid)
    return Response(json.dumps({}), 200, content_type='application/json; charset=utf-8',
                    headers={'X-Weave-Records': str(len(counts))})


# XXX
@login(['GET', ])
def get_quota():
    # if request.authorization.username != uid:
    #     return Response('Not Authorized', 401)
    return Response('Not Implemented', 501)


# XXX
def get_storage(environ, request, version, uid):
    # XXX returns a 400 if the root is called # -- WTF?
    return Response(status_code=400)


@login(['GET', 'POST', 'DELETE'])
def collection(environ, request, version, uid, cid):
    """/<float:version>/<username>/storage/<collection>"""
    
    if request.authorization.username != uid:
        return Response('Not Authorized', 401)
    
    dbpath = path(environ['data_dir'], uid, request.authorization.password)
    
    ids = request.args.get('ids', None)
    offset = request.args.get('offset', None)
    
    if request.method == 'GET':
        """Returns a list of the WBO or ids contained in a collection."""
        
        ids    = request.args.get('ids', None)
        older  = request.args.get('older', None)
        newer  = request.args.get('newer', None)
        full   = request.args.get('full', False)
        index_above = request.args.get('index_above', None)
        index_below = request.args.get('index_below', None)
        limit  = request.args.get('limit', None)
        offset = request.args.get('offset', None)
        sort   = request.args.get('sort', None)
        
        if limit is not None:
            limit = int(limit)
        
        if offset is not None:
            # we need both
            if limit is None:
                offset = None
            else:
                offset = int(offset)
        
        if not full:
            fields = ['id']
        else:
            fields = ['id', 'modified', 'sortindex', 'payload', 'ttl']
        
        # filters used in WHERE clause
        filters = {}
        if ids is not None:
            filters['id'] =  'IN', '(%s)' % ids
        if older is not None:
            filters['modified'] = '<', older
        if newer is not None:
            filters['modified'] = '>', newer
        if index_above is not None:
            filters['sortindex'] = '>', int(index_above)
        if index_below is not None:
            filters['sortindex'] = '<', int(index_below)
        
        with sqlite3.connect(dbpath) as db:
            
            filter_query = ''; sort_query = ''; limit_query = ''
            
            # ORDER BY x ASC|DESC
            if sort is not None:
                if sort == 'index':
                    sort_query = ' ORDER BY sortindex DESC'
                elif sort == 'oldest':
                    sort_query = ' ORDER BY modified ASC'
                elif sort == 'newest':
                    sort_query = ' ORDER BY modified DESC'
            
            # WHERE x<y AND ...
            if filters:
                filter_query = ' WHERE '
                filter_query += ' AND '.join([k+' '+v[0]+' '+v[1] for k,v in filters.iteritems()])
            
            # LIMIT x [OFFSET y]
            if limit:
                limit_query += ' LIMIT %i' % limit
                if offset:
                    limit_query += ' OFFSET %i' % offset
            
            res = db.execute('SELECT %s FROM %s' % (','.join(fields), cid) \
                             + filter_query + sort_query + limit_query).fetchall()
            
            if len(fields) == 1:
                # only ids
                js = json.dumps([v[0] for v in res])
            else:
                # full WBO
                js = json.dumps([wbo2dict(v) for v in res])
        
        return Response(js, 200, content_type='application/json; charset=utf-8',
                        headers={'X-Weave-Records': str(len(js))})
                        
    elif request.method == 'POST':
        try:
            data = json.loads(request.data)
        except ValueError:
            return Response(WEAVE_MALFORMED_JSON, 200)

        success = []
        for item in data:
            # XXX remove storage-object
            o = storage.set_item(dbpath, uid, cid, item)
            success.append(o['id'])

        # XXX guidance as to possible errors (?!)
        js = json.dumps({'modified': round(time.time(), 2), 'success': success})
        return Response(js, 200, content_type='application/json; charset=utf-8',
                        headers={'X-Weave-Records': str(len(js))})
                        
    elif request.method == 'DELETE':
        with sqlite3.connect(dbpath) as db:
            # XXX implement offset
            if ids is not None:
                db.execute('DELETE FROM %s WHERE id IN (?);' % cid, [ids])
            else:
                db.execute('DROP table IF EXISTS %s' % cid)
        return Response('', 200)



@login()
def item(environ, request, version, uid, cid, id):
    """GET, PUT or DELETE an item into collection_id."""
    
    if request.authorization.username != uid:
        return Response('Not Authorized', 401)
    
    dbpath = path(environ['data_dir'], uid, request.authorization.password)
    
    if request.method == 'GET':
        try:
            with sqlite3.connect(dbpath) as db:
                res = db.execute('SELECT * FROM %s WHERE id=?' % cid, [id]).fetchone()
        except sqlite3.OperationalError:
            # table could not exists, e.g. (not a nice way to do, though)
            res = None
        
        if res is None:
            return Response('Not Found', 404)
        
        js = json.dumps({'id': res[0], 'modified': round(res[1], 2),
                         'sortindex': res[2], 'payload': res[3], 'ttl': res[4]})
        return Response(js, 200, content_type='application/json; charset=utf-8',
                        headers={'X-Weave-Records': str(len(js))})
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.data)
        except ValueError:
            return Response(WEAVE_MALFORMED_JSON, 200)
        
        if id != data['id']:
            return Response(WEAVE_INVALID_WRITE, 400)

        # XXX remove storage obj
        obj = storage.set_item(dbpath, uid, cid, data)
        js = json.dumps(obj)
        return Response(js, 200, content_type='application/json; charset=utf-8',
                        headers={'X-Weave-Records': str(len(js))})
    
    elif request.method == 'DELETE':
        with sqlite3.connect(dbpath) as db:
            db.execute('DELETE FROM %s WHERE id=?' % cid, [id])
        return Response('', 200)


def index(environ, request):
    return Response('Not Implemented', 501)