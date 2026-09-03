# Turmas UFPB

Aplicação independente para entrar no SIGAA e consultar turmas de graduação. HTML,
CSS e JavaScript, com servidor Python 3. Instale a dependência criptográfica com
`python3 -m pip install -r requirements.txt`.

Execute `python server.py` e abra http://127.0.0.1:8765. No Windows, também pode usar `py server.py`.

O servidor obtém o ViewState de cada formulário e mantém os cookies do SIGAA na memória, separados por sessão. A senha não é salva. As sessões locais expiram após 30 minutos de inatividade; sair descarta a sessão local. O servidor escuta apenas no computador local. Não foi preparado para hospedagem pública.

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
