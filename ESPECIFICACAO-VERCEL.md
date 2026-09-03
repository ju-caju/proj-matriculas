# Reorganização técnica e hospedagem na Vercel

## Problem Statement

O planejador de turmas da UFPB funciona apenas como um servidor Python local. A aplicação mantém sessões do SIGAA na memória do processo, serve os arquivos da interface pelo mesmo servidor e ainda não tem estrutura de implantação para um ambiente serverless. Nesse formato, reinícios ou trocas de instância encerram as sessões e impedem uma implantação confiável na Vercel.

O proprietário quer usar a aplicação por um endereço gratuito da Vercel, sem divulgá-la. Mesmo com esse uso restrito na prática, o endereço será público. O backend precisa impedir abuso do login, proteger os cookies do SIGAA e evitar o registro de credenciais ou dados pessoais.

## Solution

Reorganizar a aplicação sem alterar sua aparência ou suas funções. A interface continuará em HTML, CSS e JavaScript puro. O backend continuará em Python, mas a integração com o SIGAA, o armazenamento de sessões e a camada HTTP serão separados.

A interface estática e as funções Python serão implantadas na Vercel. As sessões temporárias do SIGAA ficarão em Redis, criptografadas e com expiração de 30 minutos após o último uso. As tentativas de login serão limitadas por endereço IP. A grade continuará salva somente no navegador, e o usuário poderá baixar a imagem já oferecida pela aplicação.

O primeiro deploy usará um endereço gratuito `*.vercel.app` e serviços dentro das cotas gratuitas. Caso o SIGAA não aceite tráfego vindo da Vercel, a interface permanecerá na Vercel e somente o backend será transferido para outro serviço.

## User Stories

1. Como proprietário, quero acessar o planejador por um endereço gratuito da Vercel, para usá-lo sem iniciar um servidor local.
2. Como usuário, quero entrar com minhas credenciais do SIGAA, para consultar as turmas disponíveis.
3. Como usuário, quero que minha senha seja usada somente na tentativa de login atual, para que ela não permaneça armazenada pela aplicação.
4. Como usuário, quero que os cookies da minha sessão do SIGAA sejam protegidos, para que outra pessoa não consiga reutilizá-los.
5. Como usuário, quero que minha sessão expire após 30 minutos sem uso, para reduzir a exposição de uma sessão abandonada.
6. Como usuário, quero que cada acesso use uma sessão isolada, para não receber dados de outra pessoa.
7. Como usuário, quero receber uma mensagem clara quando a sessão expirar, para saber que preciso entrar novamente.
8. Como usuário, quero consultar turmas por ano e período, para planejar o semestre correto.
9. Como usuário, quero consultar por disciplina, docente ou ambos, para encontrar as turmas de interesse.
10. Como usuário, quero deixar o departamento em branco, para pesquisar em toda a UFPB.
11. Como usuário, quero continuar selecionando e removendo turmas como faço hoje, para que a mudança de hospedagem não altere meu fluxo.
12. Como usuário, quero ver conflitos de horário, para evitar uma grade incompatível.
13. Como usuário, quero que horários adjacentes não sejam marcados como conflito, para receber resultados corretos.
14. Como usuário, quero que intervalos de datas sejam considerados nos conflitos, para não descartar turmas que ocorrem em períodos diferentes.
15. Como usuário, quero que horários desconhecidos sejam sinalizados, para conferi-los diretamente no SIGAA.
16. Como usuário, quero que a grade permaneça salva somente neste navegador, para não criar uma conta adicional nem armazenar meu planejamento no servidor.
17. Como usuário, quero manter grades separadas por semestre, para consultar planejamentos diferentes.
18. Como usuário, quero baixar minha grade como imagem PNG, para guardá-la ou compartilhá-la por minha conta.
19. Como usuário, quero sair da aplicação e invalidar a sessão temporária, para encerrar o acesso ao SIGAA naquele navegador.
20. Como usuário, quero ver o aviso curto de que a aplicação é independente da UFPB, para não confundi-la com um serviço oficial.
21. Como proprietário, quero limitar tentativas de login a cinco por IP em quinze minutos, para reduzir testes automatizados de credenciais contra o SIGAA.
22. Como proprietário, quero que o limite de login funcione entre diferentes instâncias da Vercel, para que uma troca de função não contorne a proteção.
23. Como proprietário, quero que a aplicação recuse operações quando uma cota ou dependência indispensável estiver indisponível, para evitar comportamento inseguro e cobrança inesperada.
24. Como proprietário, quero logs técnicos sem usuário, senha, cookies, termos pesquisados ou HTML do SIGAA, para diagnosticar falhas sem registrar dados pessoais.
25. Como proprietário, quero manter segredos fora do repositório, para que chaves do Redis e da criptografia não sejam publicadas no Git.
26. Como proprietário, quero um repositório privado no GitHub ligado à Vercel, para versionar o código e habilitar deploys automáticos.
27. Como proprietário, quero validar uma implantação de prévia antes da produção, para detectar erros de configuração.
28. Como proprietário, quero verificar manualmente o login e a consulta reais depois do deploy, para confirmar que a Vercel consegue acessar o SIGAA.
29. Como mantenedor, quero que os testes usem páginas sanitizadas e serviços controlados, para não depender do SIGAA nem de credenciais reais.
30. Como mantenedor, quero preservar os testes existentes da conversão de horários, para evitar regressões no planejador.
31. Como mantenedor, quero uma separação clara entre protocolo do SIGAA, sessões e transporte HTTP, para alterar uma parte sem reescrever as demais.
32. Como mantenedor, quero instruções de desenvolvimento e implantação atualizadas, para reproduzir o ambiente sem recorrer ao histórico da conversa.
33. Como mantenedor, quero que arquivos HAR, variáveis locais e artefatos sensíveis permaneçam ignorados pelo Git, para evitar publicação acidental.
34. Como proprietário, quero manter a interface na Vercel se o backend precisar mudar de provedor, para preservar o endereço e a experiência do usuário.

## Implementation Decisions

- O backend permanecerá em Python. Não haverá reescrita em JavaScript ou TypeScript.
- A interface permanecerá em HTML, CSS e JavaScript puro, sem React, Next.js ou mudança visual.
- A aplicação será dividida em integração com o SIGAA, armazenamento de sessão, rate limiting, configuração e camada HTTP.
- A camada HTTP será compatível com funções Python da Vercel e preservará os contratos atuais da API sempre que possível.
- O endpoint de login aceitará usuário e senha, encaminhará as credenciais ao SIGAA e descartará a senha assim que a tentativa terminar.
- A aplicação usará um identificador aleatório em cookie `HttpOnly`, `Secure` em produção, `SameSite=Strict` e restrito ao caminho adequado.
- O Redis armazenará a representação necessária da sessão do SIGAA, nunca a senha. O conteúdo será criptografado pela aplicação antes do envio ao Redis.
- A chave de criptografia e as credenciais do Redis serão variáveis de ambiente. Nenhum segredo terá valor padrão apropriado para produção.
- Cada leitura válida da sessão renovará sua expiração, limitada a 30 minutos de inatividade.
- O logout removerá a sessão do Redis e expirará o cookie local.
- O rate limiting será compartilhado pelo Redis e permitirá no máximo cinco tentativas de login por IP em uma janela de quinze minutos.
- A identificação do IP confiará apenas nos cabeçalhos definidos pela plataforma de implantação. Entradas fornecidas diretamente pelo cliente não serão aceitas sem validação.
- Quando Redis, criptografia ou configuração obrigatória falharem em produção, a aplicação falhará de modo fechado e não tentará manter sessões apenas na memória.
- O armazenamento em memória poderá existir somente como adaptador explícito para desenvolvimento e testes.
- A grade e as turmas selecionadas continuarão no `localStorage`, separadas por semestre. O servidor não persistirá o planejamento.
- A exportação PNG continuará no navegador e não enviará os dados da grade a um serviço externo.
- Logs conterão horário, rota interna, classe de resultado, duração e identificador técnico não reversível quando necessário. Não conterão credenciais, cookies, nomes pesquisados, respostas HTML ou dados acadêmicos.
- A página de login manterá o aviso curto de que a aplicação é localmente desenvolvida e independente da UFPB. Não será criada uma página jurídica nesta etapa.
- A produção usará inicialmente o domínio gratuito da Vercel.
- O código ficará em um repositório privado do GitHub, e a branch principal será a origem dos deploys de produção.
- A implantação deve permanecer dentro das cotas gratuitas. Não será habilitado gasto automático como parte deste trabalho.
- Uma implantação de prévia será validada antes da implantação de produção.
- A validação real usará uma sessão nova do SIGAA e não reutilizará HARs, cookies ou ViewStates antigos.
- Se a Vercel não conseguir acessar o SIGAA, a interface continuará na Vercel e a API poderá ser apontada para outro backend por configuração.

## Testing Decisions

- O principal seam de teste será a API HTTP. Os testes enviarão requisições aos endpoints e observarão status, corpo, cookies e efeitos no armazenamento por meio de adaptadores controlados.
- O cliente do SIGAA será substituído por uma implementação controlada nos testes da API. Isso permite cobrir login, expiração, consulta, erro do portal e logout sem fazer requisições reais.
- O armazenamento de sessão e o rate limiter terão um adaptador em memória para testes. Os mesmos contratos serão usados pelo adaptador Redis de produção.
- Os testes verificarão que a senha não é persistida, que os dados de sessão são criptografados antes do armazenamento e que uma sessão expirada não autoriza consultas.
- Os testes verificarão o limite de cinco tentativas por IP em quinze minutos, incluindo a resposta da sexta tentativa e a liberação após a janela.
- Os testes verificarão isolamento entre sessões, renovação da expiração, logout e falha fechada quando o armazenamento estiver indisponível.
- Os testes verificarão os contratos externos dos endpoints existentes, sem depender da organização interna das funções.
- Os testes existentes do módulo de horários continuarão cobrindo conversão dos códigos UFPB, múltiplos turnos, datas, conflitos, adjacência e layout.
- Respostas HTML sanitizadas representarão as páginas relevantes do SIGAA nos testes do parser. Elas não conterão credenciais, cookies, dados pessoais nem conteúdo integral capturado de uma sessão.
- Nenhum teste automatizado acessará o SIGAA real.
- Após a implantação de prévia, haverá uma verificação manual de carregamento, headers de segurança, rate limiting e falha sem configuração.
- Após a implantação de produção, haverá uma única verificação manual de login, consulta e logout com credenciais fornecidas diretamente pelo proprietário no navegador.

## Out of Scope

- Alterações visuais ou reformulação da experiência da interface.
- Migração para React, Next.js ou outro framework de frontend.
- Cadastro de usuários, autenticação por e-mail, lista de convidados ou código de acesso compartilhado.
- Divulgação pública do projeto ou suporte a uma comunidade de usuários.
- Matrícula, cancelamento de matrícula ou qualquer ação acadêmica no SIGAA.
- Persistência de grades no servidor, sincronização entre dispositivos ou compartilhamento dentro da aplicação.
- Armazenamento de senhas do SIGAA.
- Uso de HARs em produção ou inclusão de HARs no repositório.
- Testes automatizados contra o SIGAA real.
- Domínio próprio, disponibilidade garantida ou serviços pagos.
- Página extensa de termos de uso ou política de privacidade.
- Mudança preventiva do backend para outro provedor antes de testar a Vercel.

## Further Notes

- Embora o proprietário não pretenda divulgar o endereço, uma aplicação em `*.vercel.app` deve ser tratada como publicamente acessível.
- O parser depende da estrutura HTML e dos formulários JSF atuais do SIGAA. Mudanças no portal podem exigir manutenção.
- Uma resposta HTTP 200 do SIGAA não confirma autenticação. A integração deve continuar validando o destino e o conteúdo retornado.
- Cada formulário deve usar o `javax.faces.ViewState` obtido na sessão e na página correspondentes. Valores antigos de HAR não devem ser reutilizados.
- Os horários devem continuar seguindo a tabela oficial da UFPB: N1 começa às 19h e T6 corresponde a 17h30–18h20.
- A aplicação não foi autorizada a armazenar dados acadêmicos no servidor.
- A alternativa de backend externo só será acionada se a validação em produção demonstrar bloqueio ou incompatibilidade entre a Vercel e o SIGAA.
