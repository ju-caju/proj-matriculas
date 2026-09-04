# Contribuindo

## Verificações locais

Instale o `uv` e execute `make install`. Os mesmos comandos usados no CI ficam
disponíveis como alvos do Makefile:

```sh
make format       # formata os arquivos Python
make format-check # verifica se a formatação está atualizada
make lint         # executa o Ruff
make typecheck    # executa o mypy
make test         # 28 testes Python e os testes JavaScript
make coverage     # mede a cobertura dos testes Python
make check        # executa todas as verificações
```

O lockfile `uv.lock` é versionado. Atualize-o com `uv lock` quando alterar as
dependências e confirme a instalação com `uv sync --locked`.

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
