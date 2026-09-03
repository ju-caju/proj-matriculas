"""Aplicação local, sem dependências externas. Execute: python server.py."""
import json
import re
import secrets
import time
from pathlib import Path
from html.parser import HTMLParser
from http.cookies import SimpleCookie
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlsplit
from urllib.request import build_opener, HTTPCookieProcessor, Request

BASE = 'https://sigaa.ufpb.br'
LOGIN = '/sigaa/logon.jsf'
QUERY = '/sigaa/ensino/turma/busca_turma.jsf'
ROOT = Path(__file__).parent
SESSIONS = {}


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.inputs, self.units, self.rows = {}, [], []
        self.select = self.option = None
        self.table = False
        self.row = self.cell = None
        self.subject = ''
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'input' and a.get('name'):
            self.inputs[a['name']] = a.get('value', '')
        if tag == 'select': self.select = a.get('name')
        if tag == 'option' and self.select == 'form:selectUnidade':
            self.option = [a.get('value', ''), '']
        if tag == 'table' and a.get('id') == 'lista-turmas': self.table = True
        if self.table and tag == 'tr':
            self.row = {'class': a.get('class', ''), 'cells': []}
        if self.row is not None and tag in ('td', 'th'): self.cell = ''

    def handle_data(self, data):
        if self.option is not None: self.option[1] += data
        if self.cell is not None: self.cell += ' ' + data

    def handle_endtag(self, tag):
        if tag == 'option' and self.option is not None:
            self.units.append({'value': self.option[0], 'label': self.option[1].strip()})
            self.option = None
        if tag == 'select': self.select = None
        if tag in ('td', 'th') and self.cell is not None:
            self.row['cells'].append(' '.join(self.cell.split()))
            self.cell = None
        if tag == 'tr' and self.row is not None:
            cells = self.row['cells']
            if 'destaque' in self.row['class'] and cells: self.subject = cells[0]
            elif len(cells) >= 9 and re.fullmatch(r'\d{4}\.\d', cells[0]):
                self.rows.append(dict(zip(
                    ['disciplina', 'periodo', 'turma', 'docente', 'tipo', 'forma', 'situacao', 'horario', 'local', 'vagas'],
                    [self.subject] + cells[:9])))
            self.row = None
        if tag == 'table': self.table = False


class Sigaa:
    def __init__(self):
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, path, fields=None):
        data = urlencode(fields).encode() if fields is not None else None
        req = Request(BASE + path, data=data, headers={'User-Agent': 'Mozilla/5.0', 'Referer': BASE + path})
        with self.opener.open(req, timeout=35) as response:
            raw = response.read()
            charset = response.headers.get_content_charset()
            if not charset:
                match = re.search(br'charset=["\s]*([a-zA-Z0-9-]+)', raw[:8000])
                charset = match.group(1).decode() if match else 'utf-8'
            return response.url, Page(raw.decode(charset, errors='replace'))

    def login(self, username, password):
        _, page = self.request(LOGIN)
        fields = {'form': 'form', 'form:width': '1920', 'form:height': '1080',
                  'form:login': username, 'form:senha': password,
                  'form:entrar': page.inputs.get('form:entrar', 'Entrar'),
                  'javax.faces.ViewState': page.inputs['javax.faces.ViewState']}
        url, page = self.request(LOGIN, fields)
        if 'form:senha' in page.inputs or 'discente' not in url:
            raise PermissionError('Login não confirmado. Confira usuário e senha no SIGAA.')

    def query(self, year, period, unit, discipline='', teacher=''):
        _, page = self.request(QUERY)
        if 'form:senha' in page.inputs: raise PermissionError('Sua sessão expirou. Entre novamente.')
        fields = {'form': 'form', 'form:checkNivel': 'on', 'form:selectNivelTurma': 'G',
                  'form:checkAnoPeriodo': 'on', 'form:inputAno': year, 'form:inputPeriodo': period,
                  'form:selectUnidade': unit or '0',
                  'form:selectModalidade': '0', 'form:selectCurso': '0', 'form:formaEnsino': '0',
                  'form:selectSituacaoTurma': '1', 'form:selectTipoTurma': '0',
                  'form:selectOpcaoOrdenacao': '1', 'turmasEAD': 'false', 'form:buttonBuscar': 'Buscar',
                  'javax.faces.ViewState': page.inputs['javax.faces.ViewState']}
        for field in ['CodDisciplina', 'CodTurma', 'Local', 'Horario', 'NomeDisciplina', 'NomeDocente']:
            fields['form:input' + field] = ''
        if unit: fields['form:checkUnidade'] = 'on'
        if discipline:
            fields['form:checkDisciplina'] = 'on'
            fields['form:inputNomeDisciplina'] = discipline
        if teacher:
            fields['form:checkDocente'] = 'on'
            fields['form:inputNomeDocente'] = teacher
        _, result = self.request(QUERY, fields)
        if 'form:senha' in result.inputs: raise PermissionError('Sua sessão expirou. Entre novamente.')
        if not result.rows and 'form:buttonBuscar' not in result.inputs:
            raise ValueError('O SIGAA retornou uma página inesperada. Tente novamente.')
        return {'rows': result.rows, 'units': page.units}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def reply(self, status, body, cookie=None, mime='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; form-action 'self'")
        if cookie: self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(data)

    def valid_host(self):
        return self.headers.get('Host') in ('127.0.0.1:8765', 'localhost:8765')

    def session(self):
        for key, (_, stamp) in list(SESSIONS.items()):
            if time.time() - stamp > 1800: SESSIONS.pop(key, None)
        cookies = SimpleCookie(self.headers.get('Cookie', ''))
        sid = cookies['session'].value if 'session' in cookies else ''
        value = SESSIONS.get(sid)
        if value: SESSIONS[sid] = (value[0], time.time())
        return sid, value[0] if value else None

    def do_GET(self):
        if not self.valid_host(): return self.reply(403, {'error': 'Host inválido.'})
        files = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/schedule.js': ('schedule.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
        if self.path == '/api/session': return self.reply(200, {'authenticated': bool(self.session()[1])})
        if self.path not in files: return self.reply(404, {'error': 'Não encontrado.'})
        filename, mime = files[self.path]
        self.reply(200, (ROOT / filename).read_bytes(), mime=mime + '; charset=utf-8')

    def do_POST(self):
        if not self.valid_host() or self.headers.get('Origin') not in (None, 'http://127.0.0.1:8765', 'http://localhost:8765'):
            return self.reply(403, {'error': 'Origem inválida.'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.reply(415, {'error': 'JSON necessário.'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 8192: raise ValueError('Dados inválidos.')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict): raise ValueError('Dados inválidos.')
            sid, client = self.session()
            if self.path == '/api/login':
                if not all(isinstance(data.get(k), str) and data[k] for k in ('username', 'password')):
                    raise ValueError('Informe usuário e senha.')
                new_client = Sigaa()
                new_client.login(data['username'], data['password'])
                SESSIONS.pop(sid, None)
                sid = secrets.token_urlsafe(32)
                SESSIONS[sid] = (new_client, time.time())
                return self.reply(200, {'ok': True}, 'session=' + sid + '; HttpOnly; SameSite=Strict; Path=/; Max-Age=1800')
            if self.path == '/api/logout':
                SESSIONS.pop(sid, None)
                return self.reply(200, {'ok': True}, 'session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if not client: raise PermissionError('Entre para consultar as turmas.')
            if self.path == '/api/units':
                _, page = client.request(QUERY)
                if 'form:senha' in page.inputs: raise PermissionError('Sua sessão expirou. Entre novamente.')
                return self.reply(200, {'units': page.units})
            if self.path == '/api/turmas':
                year, period, unit = (str(data.get(k, '')) for k in ('year', 'period', 'unit'))
                discipline, teacher = (str(data.get(k, '')).strip() for k in ('discipline', 'teacher'))
                if not re.fullmatch(r'20\d{2}', year) or period not in ('0', '1', '2', '3', '4') or (unit and not unit.isdigit()) or max(len(discipline), len(teacher)) > 60:
                    raise ValueError('Confira ano, período e unidade.')
                return self.reply(200, client.query(year, period, unit, discipline, teacher))
            self.reply(404, {'error': 'Não encontrado.'})
        except PermissionError as exc: self.reply(401, {'error': str(exc)})
        except ValueError: self.reply(400, {'error': 'Dados inválidos ou resposta inesperada do SIGAA.'})
        except Exception: self.reply(502, {'error': 'Não foi possível consultar o SIGAA. Tente novamente.'})


if __name__ == '__main__':
    print('Aplicação disponível em http://127.0.0.1:8765', flush=True)
    HTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
