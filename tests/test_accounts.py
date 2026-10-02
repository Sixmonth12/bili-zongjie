import os
import sys
import tempfile
import threading
import json
import unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from unittest.mock import patch
import test_app
import accounts
app=test_app.app

class AccountTests(unittest.TestCase):
    def test_http_two_users_cannot_share_records_or_keys(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(accounts,'ROOT',Path(folder)),patch.dict(os.environ,{'STUDY_INVITE_CODE':'test-invite'}),patch.dict(sys.modules,{app.__name__:app}):
            accounts.tokens.clear();accounts.attempts.clear()
            server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);server.multi_user=True
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            base=f'http://127.0.0.1:{server.server_port}'
            def call(path,data=None,cookie=''):
                request=Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','Cookie':cookie})
                with urlopen(request) as response:return json.load(response),response.headers.get('Set-Cookie','').split(';')[0]
            try:
                with self.assertRaises(HTTPError) as error:call('/api/sessions')
                self.assertEqual(error.exception.code,401)
                _,a=call('/api/auth/register',{'username':'alice','password':'secure-password-a','invite':'test-invite'})
                _,b=call('/api/auth/register',{'username':'bravo','password':'secure-password-b','invite':'test-invite'})
                first,_=call('/api/start',{'demo':True},a)
                rows,_=call('/api/sessions',cookie=b);self.assertEqual(rows,[])
                with self.assertRaises(HTTPError):call('/api/session?id='+first['id'],cookie=b)
                record,_=call('/api/workspace/save',{'kind':'material','title':'Private','content':'Alice only'},a)
                rows,_=call('/api/workspace/list',{'kind':'material'},b);self.assertEqual(rows,[])
                call('/api/workspace/save',{'id':record['id'],'kind':'material','title':'Other','content':'Bob'},b)
                rows,_=call('/api/workspace/list',{'kind':'material'},a);self.assertEqual(rows[0]['content'],'Alice only')
                call('/api/config',{'base_url':'https://api.openai.com/v1','model':'test','api_key':'alice-key'},a)
                cfg,_=call('/api/config',cookie=b);self.assertFalse(cfg['has_key']);self.assertEqual(cfg['model'],'')
                with self.assertRaises(HTTPError):call('/api/config',{'base_url':'http://127.0.0.1:1234','model':'x'},a)
                call('/api/auth/logout',{},a)
                with self.assertRaises(HTTPError):call('/api/sessions',cookie=a)
                self.assertFalse(any(b'alice-key' in p.read_bytes() for p in Path(folder).rglob('*.sqlite3')))
            finally:server.shutdown();server.server_close();worker.join();accounts.tokens.clear()
