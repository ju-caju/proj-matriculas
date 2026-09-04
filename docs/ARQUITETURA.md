# Arquitetura

## Visão do sistema

O estudante usa uma página HTML, CSS e JavaScript puro no navegador. O
navegador chama somente a API JSON da mesma origem; não há conta própria nem
persistência do planejamento no servidor.

```text
navegador
  ├── arquivos estáticos e grade no localStorage
  └── POST/GET JSON
          │
          ▼
gateway Vercel (rewrite) ──► FastAPI (api/index.py)
                                  ├── validação e contratos HTTP
                                  ├── SessionStore + rate limiter
                                  │       └── Redis REST (produção)
                                  └── Sigaa + parser
                                          └── HTTPS allowlist ──► SIGAA
```

No desenvolvimento, `server.py` inicia a mesma aplicação com
`MemorySessionStore`; o adaptador local é explícito e não é uma alternativa de
produção. Na Vercel, `api/index.py` constrói a aplicação com Redis REST,
sessões cifradas e limite compartilhado por IP. O gateway apenas reescreve as
rotas para a função ASGI e aplica headers de segurança.

## Responsabilidades e contratos

| Componente | Responsabilidade | Fronteira que preserva |
| --- | --- | --- |
| `app.js` e `frontend/` | estado da tela, chamadas JSON e planejamento | a grade fica no navegador |
| `backend/app.py` | endpoints, validação, projeção e headers | só campos dos modelos chegam ao cliente |
| `backend/sessions.py` | sessão temporária e rate limit | senha nunca é serializada; cookies do SIGAA são cifrados em produção |
| `backend/sigaa.py` | login, consulta e transporte com cookies isolados | somente HTTPS e host permitido atravessam a fronteira |
| `backend/parser.py` | formulários, unidades e linhas de turmas | HTML não confiável não executa scripts ou ações |
| `api/index.py` e `vercel.json` | composição e publicação | configuração ausente falha fechado com 503 |

Os contratos públicos são `GET /api/session`, `POST /api/login`,
`POST /api/units`, `POST /api/turmas` e `POST /api/logout`. O backend aceita
somente JSON nos POSTs, valida tamanho e tipos, e retorna erros genéricos. Os
testes em `tests/test_fastapi_app.py`, `tests/test_http_api.py` e
`tests/test_http_security.py` são a referência executável desses contratos.

## Ambientes

| Ambiente | Entrada | Sessão e limite | Origem permitida | Uso |
| --- | --- | --- | --- | --- |
| Local | `server.py` em `127.0.0.1` | memória | localhost | desenvolvimento e testes |
| Preview | `api/index.py` em URL Vercel de preview | Redis e chave exclusivos de Preview | host HTTPS da preview | validação antes de produção |
| Production | `api/index.py` no domínio Vercel | Redis e chave exclusivos de Production | host HTTPS publicado | uso manual aprovado |

Preview e Production não compartilham Redis, token ou chave. A configuração
obrigatória ausente não faz fallback para memória. O procedimento operacional,
incluindo promoção, observabilidade e rollback, está em [`RUNBOOK.md`](../RUNBOOK.md).

## Fluxo seguro do estudante

1. O navegador envia usuário e senha uma vez a `POST /api/login`.
2. `Sigaa` obtém o ViewState atual, envia a tentativa pelo transporte permitido
   e descarta a senha ao terminar; apenas cookies temporários são associados à
   sessão.
3. O backend devolve um identificador aleatório em cookie `HttpOnly`,
   `SameSite=Strict` e, em produção, `Secure` e `Path=/api`.
4. Consultas usam a sessão isolada, validam a resposta do parser e projetam
   apenas os campos de turma previstos no contrato.
5. Logout remove a sessão e expira o cookie. A grade e sua imagem continuam
   sendo processadas localmente.

Os controles, ameaças residuais e a resposta a incidentes estão no [modelo de
ameaças](../MODELO-DE-AMEACAS.md). Nenhuma etapa automatizada deste repositório
envia credenciais, cookies ou requisições ao SIGAA real.
