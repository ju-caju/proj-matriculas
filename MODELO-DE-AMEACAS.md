# Modelo de ameaças

Este documento cobre a fronteira entre o planejador e o SIGAA. O planejador é
um projeto independente e não é afiliado à UFPB; ele consulta turmas, mas não
efetua matrícula, cancelamento ou qualquer outra ação acadêmica.

## Ativos

- credenciais digitadas no login;
- cookies temporários de uma sessão autenticada do SIGAA;
- filtros de consulta e os dados acadêmicos retornados (turmas, docentes,
  horários e locais);
- chave Fernet, token do Redis e identificador de sessão;
- disponibilidade e cota dos serviços de hospedagem.

## Fronteiras de confiança

O navegador do estudante e o servidor da aplicação são fronteiras distintas:
o navegador mantém a grade apenas no `localStorage`, enquanto o servidor recebe
credenciais e consultas. O servidor e o SIGAA são serviços distintos; somente o
transporte HTTPS controlado atravessa essa fronteira. Em produção, Redis REST é
um terceiro serviço confiável apenas para dados cifrados e contadores de limite.
Logs e o serviço de hospedagem são considerados observadores não confiáveis para
segredos e dados acadêmicos.

## Ameaças e controles

| Ameaça | Controle |
| --- | --- |
| Roubo ou reutilização de senha | senha usada somente durante o login; não é colocada em sessão, logs ou Redis |
| Roubo de cookie ou sessão | cookie `HttpOnly`, `Secure`, `SameSite=Strict`, caminho `/api`, identificador aleatório e TTL móvel de 30 minutos |
| Redirecionamento para phishing ou SSRF | somente HTTPS e hosts explicitamente permitidos; redirects externos são recusados |
| Resposta maliciosa ou excessivamente grande | limite de bytes antes do parser; parser ignora scripts, estilos e templates; formulários e tabela são validados |
| Mudança do fluxo de login ou sessão expirada | categorias controladas para login expirado, formulário inesperado e transporte indisponível |
| Teste automatizado de credenciais | no máximo cinco tentativas por IP em 15 minutos, contador compartilhado no Redis |
| Vazamento por diagnóstico | logging estruturado com allowlist de evento, rota, status, resultado e duração; nenhum corpo, header, filtro ou exceção é registrado |
| Ação acadêmica indevida | o cliente implementa somente login, consulta e logout; não envia operações de matrícula |

O limite por IP é deliberadamente compartilhado: estudantes que saem pela
mesma rede institucional podem consumir a mesma janela NAT. Isso reduz abuso,
mas pode produzir bloqueio coletivo; a interface deve orientar a aguardar a
janela de 15 minutos, e o operador pode investigar o contador sem acessar
credenciais.

## Riscos residuais

O SIGAA pode alterar formulários ou bloquear o tráfego da hospedagem. Um usuário
com acesso ao próprio navegador ainda pode ler sua grade local. O limite por IP
não distingue usuários atrás de NAT, e o Redis/host continuam dependências de
disponibilidade. A aplicação não promete disponibilidade do SIGAA nem substitui
os canais oficiais da universidade.

## Resposta a incidentes

Ao detectar senha, cookie, HTML ou dado acadêmico em log, interromper consultas,
preservar somente metadados técnicos necessários e remover/restringir o log
exposto. Revogar a chave `SESSION_ENCRYPTION_KEY`, invalidar sessões no Redis e
reimplantar com uma nova chave; se houver suspeita de credencial, o estudante
deve alterá-la diretamente no SIGAA. Não coletar HAR, cookies ou páginas pessoais
para investigar. Registrar apenas rota, status, classe do resultado e horário,
e atualizar este modelo e os testes sintéticos antes de reativar o serviço.
