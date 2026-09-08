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

## Compromissos pessoais

O planejamento local de cada semestre, em `ufpb-plan:<semestre>`, contém turmas
no formato anterior e compromissos com `type: "commitment"`, `id`, `nome`,
`periodo` e `horario`. O identificador permanece estável na edição. Os horários
contêm blocos semanais da tabela da UFPB, sem datas, ordenados e sem repetições.
Nenhum campo de compromisso é enviado à API.

O formulário combina dias e blocos por horário. A grade, o detalhamento e o PNG
usam o mesmo cálculo de sobreposição, incluindo as restrições de datas das
turmas. Conflitos avisam sem impedir o cadastro. Limpar a grade apaga os dois
tipos de item somente no semestre selecionado. Os testes de navegador usam
backend fictício; `BROWSER_ARTIFACT_DIR` permite guardar os PNGs baixados para
inspeção visual.

## Compartilhamento por link

`frontend/shared-plan.js` oferece `encode`, `decode`, `validate`, `compare` e
`merge`. A fotografia da grade usa JSON UTF-8 codificado em base64url no
fragmento `#grade=`, com `version: 1`, `periodo` e `items`. O fragmento da URL
não integra a requisição HTTP nem o Referer. A aplicação não o envia em chamadas
à API, logs ou métricas. Não há endpoint de compartilhamento ou armazenamento
de grades no servidor, e abrir ou copiar um link não consulta turmas no SIGAA.

O contrato contém somente disciplina, período, turma, docente, tipo, forma,
horário e local. Para compromissos, contém `type: "commitment"`, nome, período
e horário, sem a identidade local do autor. Situação, vagas, identificação do
autor e campos extras não entram na projeção. A revisão exclui compromissos
por padrão e mostra os itens antes da geração. Qualquer pessoa com o link pode
consultá-lo indefinidamente; não há revogação, assinatura ou atualização.

Geração e leitura validam o contrato inteiro. São permitidos de 1 a 40 itens,
campos de até 240 unidades UTF-16, horário de até 1.000 unidades e fragmento
final de até 16.000 caracteres, incluindo `#grade=`. O período deve ter a forma
`20AA.P`, com `P` entre 0 e 4, e ser o mesmo em todos os itens. Horários usam
o parser público de `Schedule`; compromissos aceitam somente blocos semanais
sem datas. Controles de texto, campos extras, tipos incorretos, codificação
inválida e versões desconhecidas invalidam todo o link. Nenhum item é exibido
antes dessa validação. Textos são inseridos por `textContent`, nunca como HTML.

`frontend/share-ui.js` mantém a visualização pública e a intenção de cópia
durante o login. A visualização reutiliza a semana e os detalhes em modo de
consulta, sem alterar o planejamento local. A sessão é verificada antes da
prévia e novamente ao confirmar. O login sozinho não importa itens.

A prévia compara o link com o armazenamento do período compartilhado e mostra
itens novos, duplicatas e choques da união calculados por `Schedule.conflicts`.
Turmas usam `Schedule.key`. Compromissos usam período, nome normalizado em NFC,
sem diferenças de caixa ou espaços, e o conjunto ordenado dos blocos semanais.
Na confirmação, os compromissos novos recebem UUIDs locais e horários no mesmo
formato do editor. Se outra aba alterar a grade durante a prévia, é necessário
revisar a comparação atualizada antes de confirmar novamente.

Uma única chamada a `PlanStore.save` grava a união. A interface só troca a
grade em memória depois do sucesso; uma falha de gravação preserva a grade
anterior e mantém a prévia aberta com o aviso existente. Choques não bloqueiam
a cópia. O sucesso abre o período compartilhado e informa as contagens de
itens adicionados e ignorados. Essas operações mantêm as decisões dos ADRs
existentes, sem acrescentar identidade, colaboração ou persistência no backend.
