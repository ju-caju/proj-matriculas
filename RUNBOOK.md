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

## Prévia na Vercel

No projeto Vercel, conecte o repositório privado pelo GitHub e habilite uma
implantação de prévia para cada pull request. A prévia deve usar o ambiente
`Preview` e nunca deve ser promovida automaticamente para produção. Configure
as variáveis abaixo separadamente das de produção:

| Variável | Preview | Production |
| --- | --- | --- |
| `KV_REST_API_URL` | banco Redis de prévia | banco Redis de produção |
| `KV_REST_API_TOKEN` | token do banco de prévia | token do banco de produção |
| `SESSION_ENCRYPTION_KEY` | chave Fernet exclusiva de prévia | chave Fernet exclusiva de produção |
| `VERCEL_URL` | fornecida pela Vercel | fornecida pela Vercel |
| `PUBLIC_HOST` | domínio público da prévia, se houver | domínio público estável, sem protocolo |

Marque os três primeiros valores como secrets e não os copie para arquivos,
logs, comentários ou fixtures. O Redis e a chave não devem ser reutilizados
entre ambientes: isso limita o impacto de uma exposição e impede que sessões de
prévia sejam aceitas na produção. A função falha com 503 quando a configuração
obrigatória não existe.

Após uma implantação de prévia, execute a verificação sem credenciais:

```sh
python scripts/check_preview.py --sem-configuracao https://URL-DA-PREVIA
python scripts/check_preview.py https://URL-DA-PREVIA
```

O segundo comando consome as cinco tentativas de login permitidas pelo IP do
verificador; aguarde a janela de quinze minutos antes de testar manualmente.

## Produção

Nas configurações de Git da Vercel, defina `main` como a única *Production
Branch*. Pull requests continuam sendo prévias; branches diferentes de `main`
não podem disparar deploy de produção. Promova uma prévia somente após os
checks obrigatórios e a conferência manual do proprietário.

O procedimento de deploy é:

1. Faça merge em `main` depois de `make check` e do smoke test da prévia.
2. Aguarde o deploy automático da Vercel e confirme o domínio e o status da
   função em **Deployments**.
3. Execute `scripts/check_preview.py` contra o domínio publicado quando não
   houver login manual planejado para aquele IP.
4. Faça uma consulta e logout manualmente com uma sessão nova do SIGAA; nunca
   coloque a credencial em automação.

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
