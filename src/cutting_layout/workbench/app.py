"""Authenticated, same-origin HTTP boundary for the internal workbench."""
from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import json
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from typing_extensions import Annotated
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..cutting_agent import _json_object
from .service import Service
from .store import Store, Problem, digest
from .maintenance import exclusive_lock

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    @field_validator('confirmed', mode='before', check_fields=False)
    @classmethod
    def confirm_is_boolean(cls, value):
        if value is not True:
            raise ValueError('必须明确确认')
        return value


class Login(Input):
    username: Annotated[str, StringConstraints(min_length=3, max_length=40)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class OrderInput(Input):
    title: Text
    material: Text
    profile: Text


class Generate(Input):
    parameters: dict
    process_source: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
    confirmed: Literal[True]
    request_key: Annotated[str, StringConstraints(pattern=r'^[a-zA-Z0-9_-]{16,80}$')]


class Chat(Input):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class Review(Input):
    decision: Literal['approved', 'rejected']
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]
    confirmed: Literal[True]


def create_app(data_dir=None, project_root=None, *, secure_cookie=None, service_factory=Service):
    root = Path(data_dir or os.environ.get('MPCOS_DATA_DIR', 'var/workbench')).resolve()
    project_root = Path(project_root or os.environ.get('MPCOS_PROJECT_ROOT', Path.cwd()))
    secure_cookie = (os.environ.get('MPCOS_SECURE_COOKIE') == '1') if secure_cookie is None else secure_cookie

    @asynccontextmanager
    async def lifespan(app):
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Single-host process ownership also protects offline backups and recovery.
        with exclusive_lock(root):
            store = Store(root)
            service = service_factory(store, project_root)
            app.state.store, app.state.service = store, service
            service.recover()
            try:
                yield
            finally:
                service.pool.shutdown(wait=True)

    app = FastAPI(title='MPCOS 内部下料工作台', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=os.environ.get('MPCOS_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(','))

    @app.exception_handler(Problem)
    async def problem_handler(request, exc):
        return JSONResponse({'detail': exc.message}, status_code=exc.status)

    @app.middleware('http')
    async def security(request, call_next):
        if request.url.path.startswith('/api/') and request.url.path != '/api/login':
            try:
                user(request)
            except Problem as exc:
                return JSONResponse({'detail': exc.message}, status_code=exc.status)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            origin = request.headers.get('origin')
            if origin:
                parsed = urlsplit(origin)
                if parsed.netloc != request.headers.get('host') or parsed.scheme != ('https' if secure_cookie else request.url.scheme):
                    return JSONResponse({'detail': '请求来源不匹配。'}, status_code=403)
            if request.headers.get('x-mpcos-client') != 'workbench':
                return JSONResponse({'detail': '请求缺少来源校验。'}, status_code=403)
            if request.headers.get('content-type', '').split(';')[0] != 'application/json':
                return JSONResponse({'detail': '请求必须是 JSON。'}, status_code=415)
            body = bytearray()
            async for part in request.stream():
                body.extend(part)
                if len(body) > 65536:
                    return JSONResponse({'detail': '请求过大。'}, status_code=413)
            try:
                json.loads(body, object_pairs_hook=_json_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite')))
            except (ValueError, RecursionError):
                return JSONResponse({'detail': 'JSON 无效或包含重复字段。'}, status_code=422)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers['Cache-Control'] = 'no-store'
        return response

    def user(request):
        current = app.state.store.session(request.cookies.get('mpcos_session', ''))
        if request.method != 'GET' and not hmac.compare_digest(request.headers.get('x-csrf-token', ''), current['csrf']):
            raise Problem(403, '会话校验失败，请刷新页面后再试。')
        return current

    @app.get('/healthz')
    def health():
        with app.state.store.connection() as db:
            db.execute('SELECT 1').fetchone()
        return {'status': 'ok', 'app': 'mpcos-workbench', 'schema_version': 1}

    @app.post('/api/login')
    def login(payload: Login, request: Request):
        token, csrf = app.state.store.login(payload.username, payload.password, request.client.host if request.client else 'unknown')
        response = JSONResponse({'csrf': csrf})
        response.set_cookie('mpcos_session', token, httponly=True, secure=secure_cookie, samesite='strict', max_age=28800)
        return response

    @app.get('/api/me')
    def me(request: Request):
        return user(request)

    @app.post('/api/logout')
    def logout(request: Request):
        current = user(request)
        with app.state.store.transaction() as db:
            db.execute('DELETE FROM sessions WHERE token=?', (digest(request.cookies['mpcos_session'].encode()),))
            app.state.store.audit(db, None, current['id'], 'logout')
        response = JSONResponse({'status': 'ok'})
        response.delete_cookie('mpcos_session')
        return response

    @app.get('/api/orders')
    def orders(request: Request, query: str = '', offset: int = 0):
        return app.state.service.orders(user(request), query, offset)

    @app.post('/api/orders', status_code=201)
    def create(payload: OrderInput, request: Request):
        return app.state.service.create_order(user(request), payload.title, payload.material, payload.profile)

    @app.get('/api/orders/{oid}')
    def details(oid: str, request: Request):
        return app.state.service.details(user(request), oid)

    @app.post('/api/orders/{oid}/generate', status_code=202)
    def generate(oid: str, payload: Generate, request: Request):
        return app.state.service.generate(user(request), oid, payload.parameters, payload.process_source, payload.request_key)

    @app.post('/api/orders/{oid}/chat')
    def chat(oid: str, payload: Chat, request: Request):
        return app.state.service.chat(user(request), oid, payload.text)

    @app.post('/api/orders/{oid}/versions/{vid}/review')
    def review(oid: str, vid: str, payload: Review, request: Request):
        return app.state.service.review(user(request), oid, vid, payload.decision, payload.note)

    @app.get('/api/orders/{oid}/versions/{vid}/files/{index}')
    def file(oid: str, vid: str, index: int, request: Request):
        content, name = app.state.service.file(user(request), oid, vid, index)
        from urllib.parse import quote
        media = 'image/png' if name.endswith('.png') else 'application/octet-stream'
        return Response(content, media_type=media, headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(name)}"})

    @app.get('/api/orders/{oid}/versions/{vid}/record')
    def record(oid: str, vid: str, request: Request):
        current = user(request)
        data = app.state.service.details(current, oid)
        version = next((v for v in data['versions'] if v['id'] == vid), None)
        if version is None:
            raise Problem(404, '版本不存在。')
        for index, entry in enumerate((version['result'] or {}).get('files', [])):
            app.state.service.file(current, oid, vid, index)
        order = data['order']
        return JSONResponse({'order': {k: order[k] for k in ('id','title','material','profile','owner_name')},
                             'version': version, 'notice': data['notice']},
                            headers={'Content-Disposition': f'attachment; filename="review-V{version["number"]}.json"'})

    static = Path(__file__).with_name('static')
    app.mount('/static', StaticFiles(directory=static), name='static')

    @app.get('/')
    def index():
        return FileResponse(static / 'index.html')

    return app
