"""Single-process beta account isolation. API keys only live in login-session memory."""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time
from contextvars import ContextVar
from http.cookies import SimpleCookie
from pathlib import Path

current = ContextVar('study_account', default=None)
lock = threading.RLock()
tokens = {}
attempts = {}
ROOT = Path(os.getenv('STUDY_DATA_DIR', 'data')).resolve() / 'accounts'
ORIGIN = os.getenv('STUDY_PUBLIC_ORIGIN', '').rstrip('/')
PROVIDERS = tuple(x.strip().rstrip('/') for x in os.getenv('STUDY_ALLOWED_PROVIDERS', 'https://api.openai.com/v1,https://api.deepseek.com,https://dashscope.aliyuncs.com/compatible-mode/v1').split(',') if x.strip())


def connect():
    ROOT.mkdir(parents=True, exist_ok=True)
    db=sqlite3.connect(ROOT/'accounts.sqlite3')
    db.execute('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY,name TEXT UNIQUE,salt TEXT,hash TEXT)')
    db.commit()
    return db


def digest(password,salt):
    return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()


def authenticate(data,register,peer):
    name=str(data.get('username','')).strip().lower()
    password=str(data.get('password',''))
    if not re.fullmatch(r'[a-z0-9_]{3,32}',name) or not 10<=len(password)<=128:
        raise ValueError('用户名为 3–32 位字母、数字或下划线；密码为 10–128 位。')
    now=time.time()
    with lock:
        for k in list(attempts):
            if attempts[k][0]<now-600:del attempts[k]
        start,count=attempts.get(peer,(now,0))
        if count>=20:raise ValueError('尝试过于频繁，请 10 分钟后再试。')
        attempts[peer]=(start,count+1)
    db=connect()
    try:
        if register:
            invite=os.getenv('STUDY_INVITE_CODE','')
            if not invite or not hmac.compare_digest(str(data.get('invite','')),invite):
                raise ValueError('测试版需要有效邀请码，请向管理员获取。')
            uid=secrets.token_hex(16);salt=secrets.token_hex(16)
            try:
                db.execute('INSERT INTO users VALUES(?,?,?,?)',(uid,name,salt,digest(password,salt)));db.commit()
            except sqlite3.IntegrityError:raise ValueError('无法注册，请更换用户名。')
        else:
            row=db.execute('SELECT id,salt,hash FROM users WHERE name=?',(name,)).fetchone()
            salt=row[1] if row else '00'*16
            computed=digest(password,salt)
            if not row or not hmac.compare_digest(computed,row[2]):raise ValueError('用户名或密码不正确。')
            uid=row[0]
    finally:db.close()
    token=secrets.token_urlsafe(32)
    with lock:
        for k in list(tokens):
            if tokens[k]['expires']<now:del tokens[k]
        tokens[hashlib.sha256(token.encode()).hexdigest()]={'id':uid,'name':name,'expires':now+43200,
            'config':{'base_url':PROVIDERS[0] if PROVIDERS else '', 'model':'','api_key':''}}
    return token,{'id':uid,'name':name}


def lookup(headers):
    try:
        cookie=SimpleCookie(headers.get('Cookie',''))
        token=cookie.get('study_login')
        key=hashlib.sha256(token.value.encode()).hexdigest() if token else ''
    except Exception:return None
    with lock:
        value=tokens.get(key)
        if value and value['expires']>time.time():return value
        tokens.pop(key,None)
    return None


def logout(headers):
    try:
        token=SimpleCookie(headers.get('Cookie','')).get('study_login')
        if token:
            with lock:tokens.pop(hashlib.sha256(token.value.encode()).hexdigest(),None)
    except Exception:pass


def db_path():
    account=current.get()
    return ROOT/'users'/account['id']/'study.sqlite3' if account else None


def config(default):
    account=current.get()
    return account['config'] if account else default
