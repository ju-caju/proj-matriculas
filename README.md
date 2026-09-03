# Turmas UFPB

Aplicação independente para entrar no SIGAA e consultar turmas de graduação. HTML,
CSS e JavaScript, com servidor Python 3. Instale a dependência criptográfica com
`python3 -m pip install -r requirements.txt`.

Execute `python server.py` e abra http://127.0.0.1:8765. No Windows, também pode usar `py server.py`.

O servidor obtém o ViewState de cada formulário e mantém os cookies do SIGAA na memória, separados por sessão. A senha não é salva. As sessões locais expiram após 30 minutos de inatividade; sair descarta a sessão local. O servidor local escuta apenas no computador. A versão pública usa o adaptador de produção descrito abaixo.

Filtros iniciais: graduação, 2026.2, unidade 2151, com os demais campos da consulta capturada. A lista de unidades vem do SIGAA. Busca por texto filtra os resultados já carregados. O retorno HTML do SIGAA é convertido em dados; scripts e links de ação do portal não são executados.

Depende da estrutura atual dos formulários e da tabela do SIGAA; alterações no portal podem exigir ajustes no parser. Nenhum arquivo HAR ou credencial é necessário para executar a aplicação.

## Planejador semanal

Arraste uma turma para a semana ou use Adicionar. Os blocos são posicionados automaticamente; para remover, use o botão na lista ou clique no bloco para abrir seus detalhes. Choques ficam em vermelho e a lista abaixo da grade informa as turmas e os horários envolvidos. O planejamento não efetua matrícula.

A grade é salva no armazenamento local deste navegador, por semestre (compartilhada entre contas que usam o mesmo navegador). Alterar unidade mantém as seleções. Limpar grade remove o planejamento do semestre atual.

A conversão usa a tabela publicada pela ACI/UFPB em https://www.ufpb.br/aci/alteracao-de-plano-de-estudos/ e suporta múltiplos dias, turnos, horários descontínuos e intervalos de datas. N1 corresponde a 19:00–19:50; T6 a 17:30–18:20. Códigos desconhecidos não são posicionados silenciosamente. A grade representa a semana recorrente; intervalos de datas aparecem nos detalhes e são considerados na detecção de choques.

## Organização do backend

O arquivo `server.py` apenas monta o servidor local. O código do backend fica separado em:

- `backend/http.py`: endpoints, validação das requisições e arquivos estáticos;
- `backend/sessions.py`: contrato de armazenamento e implementação local em memória;
- `backend/sigaa.py`: protocolo de login e consulta, com transporte HTTP substituível;
- `backend/parser.py`: leitura dos formulários, unidades e turmas retornados pelo SIGAA.

Essa separação permite testar a API e o parser sem credenciais e sem acessar o SIGAA real.

## Sessões em produção

O adaptador de produção usa Redis REST para compartilhar o limite de cinco tentativas
de login por IP em quinze minutos e para guardar somente os cookies temporários do
SIGAA, cifrados por 30 minutos após o último uso. Ele exige
`KV_REST_API_URL`, `KV_REST_API_TOKEN`, `SESSION_ENCRYPTION_KEY` e `VERCEL_URL`; sem qualquer uma
dessas variáveis, o servidor seguro não inicia. Gere a chave com
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

O projeto usa os arquivos estáticos da raiz sem framework de frontend. Cada arquivo
em `api/` publica um endpoint Python na mesma origem. O `vercel.json` aplica CSP,
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
