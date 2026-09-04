# ADR 0001: uso seletivo do Full Stack FastAPI Template

- Status: aceito
- Data: 2026-09-03

## Contexto

O Full Stack FastAPI Template oferece uma base útil para APIs FastAPI,
validação com modelos, testes e organização de configuração. O planejador,
porém, já tem uma interface HTML/CSS/JavaScript simples, uma integração HTML
com o SIGAA e uma implantação como função ASGI da Vercel. Adotar o template
inteiro introduziria camadas que não são necessárias ao fluxo de consulta.

## Decisão

Usamos seletivamente as ideias do Full Stack FastAPI Template: FastAPI como
camada HTTP, modelos Pydantic para contratos, dependências injetáveis nos
testes, configuração por ambiente e separação entre aplicação e adaptadores.
Mantemos a interface estática existente, o `uv` como gerenciador, o
`MemorySessionStore` para local/testes e `api/index.py` como único entrypoint
publicado. Não copiamos scaffolding ou serviços do template sem uma necessidade
do produto.

## Consequências

Os contratos são pequenos e testáveis sem banco, navegador externo ou SIGAA.
Em troca, novas capacidades precisam respeitar as interfaces locais e não
podem pressupor os serviços opcionais de um template completo. Uma futura
adoção deve ser registrada em outro ADR.
