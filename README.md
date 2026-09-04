# Turmas UFPB

Aplicação independente para entrar no SIGAA e consultar turmas de graduação. HTML,
CSS e JavaScript, com servidor Python 3. As dependências são gerenciadas com `uv`
e ficam travadas em `uv.lock`.

## Desenvolvimento reproduzível

Instale o [uv](https://docs.astral.sh/uv/) e execute:

```sh
make install
make check
```

`make check` reproduz as verificações locais do CI: formatação
(`make format-check`), lint (`make lint`), tipos (`make typecheck`), os testes
Python e JavaScript (`make test`), cobertura Python (`make coverage`) e auditoria
das dependências travadas (`make audit`), o bundle estático (`make build`) e o
smoke test HTTP após iniciar o servidor; o CI ainda executa o scanner de segredos.
Para formatar os arquivos localmente, use `make format`.

Os testes usam somente fixtures HTML sanitizadas e implementações controladas.
Eles não precisam de Redis, Vercel ou acesso ao SIGAA. As regras obrigatórias
para contribuições estão em `AGENTS.md`.

Para instalações manuais legadas, `requirements.txt` ainda lista a dependência
de runtime, mas o fluxo suportado é `uv sync --locked`.

O [runbook de entrega e operação](RUNBOOK.md) documenta Docker local, smoke test,
separação de segredos entre Preview e Production, deploy, observabilidade,
incidente e rollback na Vercel.
A [arquitetura](docs/ARQUITETURA.md) descreve o caminho navegador–FastAPI–sessão–
gateway–SIGAA, os contratos e a diferença entre os ambientes. As decisões
registradas estão em [`docs/adr/`](docs/adr/), e o [modelo de ameaças](MODELO-DE-AMEACAS.md)
lista controles, riscos residuais e resposta a incidentes.

Execute `python server.py` e abra http://127.0.0.1:8765. No Windows, também pode usar `py server.py`.

O navegador envia usuário e senha somente no POST de login; o servidor os encaminha
ao SIGAA uma vez, descarta a senha ao terminar a tentativa e guarda apenas os
cookies temporários da sessão. O servidor obtém o ViewState de cada formulário e
mantém esses cookies separados por sessão. As sessões locais expiram após 30
minutos de inatividade; sair descarta a sessão local. O servidor local escuta
apenas no computador. A versão pública usa a configuração de produção do FastAPI
descrita abaixo.

Filtros iniciais: graduação, 2026.2, unidade 2151, com os demais campos da consulta capturada. A lista de unidades vem do SIGAA. Busca por texto filtra os resultados já carregados. O retorno HTML do SIGAA é convertido em dados; scripts e links de ação do portal não são executados.

Depende da estrutura atual dos formulários e da tabela do SIGAA; alterações no portal podem exigir ajustes no parser. Nenhum arquivo HAR ou credencial é necessário para executar a aplicação.

## Planejador semanal

Arraste uma turma para a semana ou use Adicionar. Os blocos são posicionados automaticamente; para remover, use o botão na lista ou clique no bloco para abrir seus detalhes. Choques ficam em vermelho e a lista abaixo da grade informa as turmas e os horários envolvidos. O planejamento não efetua matrícula, cancelamento ou qualquer outra ação no SIGAA. Esta aplicação não é afiliada à UFPB nem substitui os canais oficiais.

A grade é salva no armazenamento local deste navegador, por semestre (compartilhada entre contas que usam o mesmo navegador). Alterar unidade mantém as seleções. Limpar grade remove o planejamento do semestre atual.

A conversão usa a tabela publicada pela ACI/UFPB em https://www.ufpb.br/aci/alteracao-de-plano-de-estudos/ e suporta múltiplos dias, turnos, horários descontínuos e intervalos de datas. N1 corresponde a 19:00–19:50; T6 a 17:30–18:20. Códigos desconhecidos não são posicionados silenciosamente. A grade representa a semana recorrente; intervalos de datas aparecem nos detalhes e são considerados na detecção de choques.

### Organização do frontend

O frontend continua sendo HTML, CSS e JavaScript puro. `app.js` coordena eventos e
estado da tela; `schedule.js` concentra a conversão de horários e conflitos;
`frontend/dom.js` reúne os construtores de elementos; `frontend/plan-store.js`
mantém a grade no `localStorage` por semestre; `frontend/api-client.js` encapsula
as chamadas JSON; e `frontend/grade-image.js` gera a exportação PNG sem enviar a
grade ao servidor. Esses módulos não introduzem um framework de interface nem
alteram o contrato visual da página.

O teste `tests/test_browser.py` inicia um servidor HTTP falso e percorre login,
unidades, consulta, montagem da grade e logout no Chrome. Ele é automaticamente
ignorado quando o Chrome não está instalado e nunca usa credenciais reais ou
acessa o SIGAA.

## Organização do backend

O arquivo `server.py` inicia o FastAPI local com armazenamento em memória. O código do backend fica separado em:

- `backend/app.py`: endpoints FastAPI, validação das requisições e arquivos estáticos;
- `backend/sessions.py`: contrato de armazenamento e implementação local em memória;
- `backend/sigaa.py`: protocolo de login e consulta, com transporte HTTP substituível;
- `backend/parser.py`: leitura dos formulários, unidades e turmas retornados pelo SIGAA.

Essa separação permite testar a API e o parser sem credenciais e sem acessar o SIGAA real. O arquivo `api/index.py` é o único entrypoint publicado pela Vercel; o `vercel.json` encaminha tanto a interface quanto a API para a mesma aplicação ASGI.

## Sessões em produção

O FastAPI de produção usa Redis REST para compartilhar o limite de cinco tentativas
de login por IP em quinze minutos e para guardar somente os cookies temporários do
SIGAA, cifrados por 30 minutos após o último uso. Ele exige
`KV_REST_API_URL`, `KV_REST_API_TOKEN`, `SESSION_ENCRYPTION_KEY` e `VERCEL_URL`; sem qualquer uma
dessas variáveis, o servidor seguro não inicia. Configure `APP_HOST` com o
domínio público estável, sem protocolo ou caminho. Gere a chave com
`python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

O endereço do cliente em produção é aceito apenas de
`X-Vercel-Forwarded-For`. O cookie de sessão fica restrito a `/api`, é `HttpOnly`,
`SameSite=Strict` e recebe `Secure` no handler de produção. O servidor local continua
usando explicitamente o adaptador em memória e não deve ser publicado.

## Testes

Execute:

```sh
python3 -m unittest discover -v
node schedule.test.js
```

Os testes Python usam páginas HTML sanitizadas e implementações controladas da integração e do armazenamento.

## Prévia na Vercel

O projeto usa os arquivos estáticos da raiz sem framework de frontend. O entrypoint
`api/index.py` publica a aplicação FastAPI na mesma origem, e o `vercel.json` encaminha
as rotas para ela. O `vercel.json` aplica CSP,
`X-Content-Type-Options: nosniff` e `X-Frame-Options: DENY` também aos arquivos
estáticos.

1. Importe o repositório na Vercel em um projeto no plano Hobby.
2. Conecte um banco Upstash Redis no plano gratuito. A integração deve criar
   `KV_REST_API_URL` e `KV_REST_API_TOKEN` nos ambientes de prévia.
3. Gere uma chave Fernet e cadastre o resultado como variável sensível
   `SESSION_ENCRYPTION_KEY` somente na Vercel:

   ```sh
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

4. Confirme que `VERCEL_URL`, variável de sistema da Vercel, está disponível para
   as funções. Crie uma implantação de prévia sem promover para produção.
5. Não habilite recarga automática, plano pago nem cobrança por excedentes para
   cumprir o limite deste ticket.

Antes de cadastrar os segredos, a API deve responder 503 sem citar a configuração
ausente:

```sh
python3 scripts/check_preview.py --sem-configuracao https://URL-DA-PREVIA
```

Depois de conectar o Redis, cadastrar a chave e gerar outra prévia, execute:

```sh
python3 scripts/check_preview.py https://URL-DA-PREVIA
```

O verificador carrega a interface, consulta o estado sem sessão, testa os headers,
os corpos JSON, a origem e o limite de login. Ele usa somente corpos inválidos e
nunca envia usuário ou senha ao SIGAA. A execução consome as seis tentativas do IP
do verificador; aguarde quinze minutos antes de tentar um login manual pelo mesmo
IP.

## Produção

A produção está em https://proj-matriculas.vercel.app. O projeto Vercel usa o plano
Hobby, o preset `Other` e a raiz do repositório. A branch `main` do repositório
privado `ju-caju/proj-matriculas` dispara os deploys de produção.

Para reproduzir a configuração:

1. Importe o repositório na Vercel com o preset `Other`.
2. Crie um banco Upstash Redis no plano Free e conecte-o a Production e Preview.
   Use o prefixo `KV_REST_API` e marque as variáveis como secretas. Confirme a
   criação de `KV_REST_API_URL` e `KV_REST_API_TOKEN`.
3. Gere uma chave Fernet e salve-a como segredo `SESSION_ENCRYPTION_KEY`. Nunca
   grave o valor em arquivo local ou no Git.
4. Habilite as variáveis de sistema da Vercel. O backend valida `VERCEL_URL` para
   aceitar apenas o host e a origem do próprio deploy.
5. Faça um novo deploy da `main`. Não habilite recursos pagos, recarga automática,
   Analytics ou Speed Insights para esta aplicação.

Depois do deploy, rode `scripts/check_preview.py` apenas quando não houver login
manual previsto para os próximos quinze minutos. O script consome todas as
tentativas permitidas do IP. Para uma verificação sem consumir o limite, abra a
interface e consulte somente `/api/session`.

Use a tela de Logs da Vercel para diagnóstico. Os logs esperados contêm rota,
status, classe do resultado e duração. Eles não devem conter usuário, senha,
cookies, filtros de busca, HTML do SIGAA nem dados acadêmicos. Se aparecer algum
desses dados, interrompa o uso e remova o log antes de continuar.

Uma sessão expira após 30 minutos sem uso. Um novo login cria outra sessão; logout
apaga a sessão no Redis. Mudanças nos formulários JSF, nomes de campos ou tabela de
turmas do SIGAA podem quebrar o parser. Nesse caso, atualize as fixtures sanitizadas
e o parser sem copiar HAR, cookies ou páginas pessoais para o repositório.

O planejamento e a exportação PNG continuam no navegador. O servidor recebe apenas
as consultas necessárias ao SIGAA e não recebe a grade montada pelo usuário.

## Rate limit e modelo de ameaças

O login aceita no máximo cinco tentativas por endereço IP em uma janela de 15
minutos. O contador é compartilhado no Redis: estudantes diferentes que usam o
mesmo IP público de uma rede institucional compartilham a janela (NAT). Uma sexta
tentativa recebe `429`; depois de 15 minutos a janela pode ser iniciada novamente.
Esse comportamento é intencional para conter abuso, embora possa bloquear vários
estudantes juntos.

Os ativos, fronteiras de confiança, ameaças, controles, riscos residuais e o
procedimento de resposta a incidentes estão em
[`MODELO-DE-AMEACAS.md`](MODELO-DE-AMEACAS.md). Logs técnicos contêm apenas evento,
rota, status, classe do resultado e duração; nunca credenciais, cookies, filtros,
HTML ou dados acadêmicos.
