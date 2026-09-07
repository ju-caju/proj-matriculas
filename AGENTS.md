# Contribuindo

## Branches e publicação

- Antes de editar, execute `git status` e `git fetch origin`. Crie uma branch
  `feat/`, `fix/` ou `chore/` a partir de `origin/main`. Preserve alterações
  locais que já existiam.
- Abra PR para `main`. Não desenvolva nem faça commits diretamente em `main`
  ou `demo`.
- Escreva commits no padrão Conventional Commits, com a descrição em português:
  `tipo(escopo opcional): descrição`. Use `feat`, `fix`, `docs`, `style`,
  `refactor`, `perf`, `test`, `build`, `ci`, `chore` ou `revert`. Comece a
  descrição com letra minúscula, use o infinitivo quando couber e não termine
  com ponto. Exemplos: `feat: adicionar filtro de turno` e
  `fix(grade): corrigir conflito entre horários`.
- Mantenha cada commit focado em uma mudança. Explique contexto adicional no
  corpo quando o título não bastar. Use `!` e um rodapé `BREAKING CHANGE:` para
  mudanças incompatíveis.
- `main` contém o código aprovado e dispara o deploy de produção na Vercel.
  Após os checks de `main`, o CI avança `demo` para o mesmo commit, disparando
  a publicação da demonstração. A sincronização nunca usa force push.
- Se `demo` tiver commits exclusivos, reúna as mudanças em uma branch de
  integração e abra PR para `main`. Preserve a ancestralidade com merge commit;
  squash ou rebase dessa integração deixariam a demo divergente.
- Demo e produção usam o mesmo código. As diferenças ficam nas variáveis da
  Vercel: Preview usa `APP_MODE=demo` e dados fictícios; Production usa SIGAA,
  Redis e chave de sessão. Não coloque segredos de produção em Preview.
- Rode `make check` e o smoke test local antes do PR. Confira os checks remotos
  antes do merge. Depois da publicação, confira os dois deployments e os SHAs;
  um push ou workflow verde, sozinho, não confirma que o site foi atualizado.
- O procedimento e a recuperação de falhas ficam em [RUNBOOK.md](RUNBOOK.md).

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
