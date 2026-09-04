# ADR 0002: não adotar React, PostgreSQL, JWT, autenticação própria ou Traefik

- Status: aceito
- Data: 2026-09-03

## Contexto

O sistema consulta turmas para uma pessoa que já possui uma conta no SIGAA.
Seu estado de planejamento é pequeno, local ao navegador e não precisa de
contas, sincronização ou escrita acadêmica. A publicação usa o rewrite da
Vercel para uma função FastAPI.

## Decisão

Continuaremos com HTML, CSS e JavaScript puro; não adotaremos React. Não
adotaremos PostgreSQL para grades ou usuários, JWT para a sessão do SIGAA,
autenticação própria (a senha é encaminhada somente ao SIGAA) nem Traefik como
proxy adicional. O servidor guarda apenas a sessão temporária necessária para
consultar o portal: em produção, cifrada no Redis REST, com TTL móvel e cookie
restrito. O gateway da Vercel fornece o roteamento e HTTPS do deployment.

## Consequências

Há menos componentes, custo e superfície de ataque, e a interface pode ser
servida junto da API sem pipeline de frontend. A aplicação não oferece contas
ou planejamento compartilhado; mudanças futuras que exijam persistência,
identidade própria ou outro proxy precisam revisar esta decisão e o modelo de
ameaças.
