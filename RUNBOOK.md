# Runbook de entrega e operação

Este runbook cobre o caminho suportado entre o checkout, a execução local, uma
prévia e a produção. A aplicação publicada continua sendo a função ASGI em
`api/index.py`; o container é somente um ambiente local reproduzível e usa o
adaptador de sessão em memória.

## Desenvolvimento local

Use a versão travada das dependências e execute as mesmas verificações do CI:

```sh
make install
make check
```

`make check` inclui `make build`, uma validação estática sem rede que confirma
os arquivos referenciados pela página e que `api/index.py` é o único entrypoint
da Vercel. Para executá-la isoladamente, use `make build`.

Para testar a inicialização isolada em Docker:

```sh
docker build -t turmas-ufpb:local .
docker run --rm --publish 8765:8765 turmas-ufpb:local
make smoke-test
```

Ou use `docker compose up --build` para iniciar o mesmo serviço local.

O smoke test verifica a página, `/api/health`, o estado de sessão, os corpos
JSON e os headers de segurança. Ele não envia credenciais, não tenta login e
não acessa o SIGAA. O container não deve receber segredos de produção.

## Branches e ambientes

Crie branches `feat/`, `fix/` ou `chore/` a partir de `origin/main` e abra PR
para `main`. Cada PR executa CI e CodeQL e recebe uma prévia com dados fictícios.
O merge depende dos checks e da conferência da prévia.

`main` é a branch de produção da Vercel. O merge dispara seu deploy e uma nova
execução do CI. Quando os checks de `main` passam, o job `Sincronizar demo`
executa `scripts/sync_demo.sh` e avança a branch `demo` para o mesmo SHA. O push
em `demo` dispara a prévia com domínio estável. Não faça commits nessa branch.

A produção e a demo são deployments separados. A produção pode terminar antes
da demo; uma falha em um ambiente não desfaz a publicação do outro. Confira o
estado e o SHA de ambos no painel da Vercel antes de considerar a entrega pronta.

| Configuração | Preview, incluindo demo e PRs | Production |
| --- | --- | --- |
| `APP_MODE` | `demo` | ausente |
| `APP_HOST` | alias estável somente na branch `demo` | domínio público de produção |
| `KV_REST_API_URL` e `KV_REST_API_TOKEN` | ausentes | Redis de produção |
| `SESSION_ENCRYPTION_KEY` | ausente | chave Fernet de produção |
| `VERCEL_URL` | fornecida pela Vercel | fornecida pela Vercel |

As prévias aceitam `demo/demo`, usam dados sintéticos e não acessam SIGAA ou
Redis. O código recusa `APP_MODE=demo` no ambiente Production. Sem configuração
válida de produção, a API responde 503. Não promova o deployment da demo para
produção; publique o mesmo código com a configuração de Production.

## Verificação da entrega

1. Execute `make check` e `make smoke-test` localmente antes de abrir o PR.
2. Confira CI, CodeQL e a prévia do PR antes do merge em `main`.
3. Após o merge, confira CI e o job `Sincronizar demo`. Verifique que `main` e
   `demo` apontam para o mesmo SHA no GitHub.
4. No painel **Deployments** da Vercel, confirme que os deployments de produção
   e demo estão prontos e usam esse SHA. Confira o domínio de cada ambiente.
5. Verifique `/api/health` e a página de cada ambiente sem enviar credenciais.
   Testes automatizados do fluxo de estudante continuam usando o backend
   fictício local. Uma consulta real ao SIGAA depende de ação manual do usuário.

Para diagnosticar a configuração de produção, `scripts/check_preview.py`
continua disponível. A execução completa consome as cinco tentativas de login
permitidas por IP; não a execute junto de um teste manual naquele IP. Esse
verificador não se aplica ao contrato de autenticação da demo.

## Recuperar a sincronização

Se os checks de `main` falharem, corrija por PR. A demo permanece no último SHA
validado. Se a sincronização falhar por indisponibilidade, reexecute o workflow
CI em `main` pela opção **Run workflow**. A execução valida tudo novamente e
sincroniza somente se o SHA ainda for o mais recente de `main`.

Se houver commits exclusivos em `demo`, o script interrompe a sincronização.
Crie uma branch de integração, reúna os históricos e abra PR para `main`. Use
merge commit nesse PR para preservar a ancestralidade. Não use force push para
encobrir a divergência.

O job usa `GITHUB_TOKEN` com escrita no conteúdo apenas na sincronização.
Os demais jobs têm acesso de leitura. Os deploys são responsabilidade da
integração Git da Vercel; o workflow não recebe tokens ou variáveis da Vercel.

## Observabilidade e diagnóstico

Os logs da função contêm somente rota, status, classe do resultado, duração e
o evento `http_request`. Não devem conter usuário, senha, cookies, filtros,
HTML do SIGAA ou dados acadêmicos. Em **Logs**, filtre por rota e classe (`ok`,
`rejected`, `authentication`, `rate_limited` ou
`dependency_unavailable`) e correlacione com o horário do deploy.

Diagnóstico básico:

1. Verifique o status do deployment e `/api/health`.
2. Se houver 503 em `/api/session`, confira as variáveis do ambiente correto e
   a conectividade/cota do Redis; não habilite fallback para memória.
3. Se houver 403, confirme o domínio Vercel e a origem HTTPS da própria
   implantação.
4. Se o parser ou a consulta falhar, preserve os logs sem dados e reproduza
   somente com fixtures sanitizadas e um transporte controlado.
5. Se aparecer qualquer segredo ou dado pessoal em log, pare o diagnóstico,
   restrinja o acesso, remova o log pela retenção da Vercel e faça a rotação
   do segredo afetado.

## Incidente e rollback

Durante um incidente, não tente corrigir o problema fazendo login automatizado
nem aumentando cotas. Desabilite temporariamente o deploy de produção na
Vercel, preserve apenas identificadores técnicos e horários, e avise o
proprietário.

Para voltar à última versão conhecida:

1. Em **Deployments**, abra o deployment anterior aprovado.
2. Use **Promote to Production** e confirme o domínio, `/api/health` e os
   headers de segurança.
3. Se a versão anterior também estiver comprometida, use um commit de
   correção revertido em `main`, aguarde os checks e faça novo deploy.
4. Após estabilizar, rotacione segredos expostos e registre a causa, o impacto,
   os horários e a ação de recuperação sem incluir conteúdo de sessão.

O rollback altera somente a implantação ativa; não apaga histórico nem dados
do repositório. Nenhum comando deste processo acessa o SIGAA sem uma ação
manual explícita do proprietário.
