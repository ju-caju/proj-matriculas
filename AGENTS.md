# Contribuindo

## Verificações locais

Instale o `uv` e execute `make install`. Os mesmos comandos usados no CI ficam
disponíveis como alvos do Makefile:

```sh
make format       # formata os arquivos Python
make format-check # verifica se a formatação está atualizada
make lint         # executa o Ruff
make typecheck    # executa o mypy
make test         # testes Python e os testes JavaScript
make coverage     # mede a cobertura dos testes Python
make audit        # audita as dependências travadas
make build        # valida o bundle estático e o entrypoint Vercel
make check        # executa todas as verificações
```

O lockfile `uv.lock` é versionado. Atualize-o com `uv lock` quando alterar as
dependências e confirme a instalação com `uv sync --locked`.

## Critérios de teste e mudança

Antes de abrir uma alteração, execute `make check`. Para validar a inicialização
local, inicie `uv run uvicorn server:app --host 127.0.0.1 --port 8765` em outro
terminal e execute `make smoke-test`. O fluxo completo do estudante usa somente
o backend falso do teste de navegador:
`uv run python -m unittest tests.test_browser -v`. O teste é ignorado quando o
Chrome não está instalado; nunca substitua essa fixture por credenciais ou um
SIGAA real.

Ao alterar o parser, atualize primeiro uma fixture sanitizada em
`tests/fixtures/`, preserve a validação de formulários/ViewState e adicione
testes para a forma HTML alterada. Não copie páginas pessoais, cookies ou HARs.
Ao alterar um contrato HTTP, atualize os modelos, os testes da API e o cliente
JavaScript na mesma mudança; mantenha status, formato de erro e campos
documentados em [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md). Ao alterar uma
dependência, edite `pyproject.toml`, execute `uv lock`, confirme
`uv sync --locked`, revise o motivo da mudança e rode `make audit`; não edite
`requirements.txt` como fonte independente.

## Limites de segurança

- Nunca adicione credenciais reais, senhas, tokens, chaves privadas ou segredos.
- Nunca adicione cookies de sessão, arquivos HAR ou HTML capturado de uma conta
  pessoal. Use apenas as fixtures sanitizadas em `tests/fixtures/`.
- Não automatize o acesso ao SIGAA. Os testes devem usar transportes controlados,
  fixtures sanitizadas e armazenamentos locais ou falsos; não contate o SIGAA,
  Redis ou Vercel reais.
- Não registre credenciais, cookies, HTML do SIGAA ou dados acadêmicos pessoais.

Se um teste ou uma reprodução parecer exigir dados reais, pare e substitua o
cenário por dados sintéticos antes de continuar.
