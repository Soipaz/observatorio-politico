# Segurança

## Como relatar uma vulnerabilidade

**Não abra uma issue pública** para problemas de segurança. Use o relato privado do GitHub: na aba **Security** deste repositório, clique em **Report a vulnerability**. Só a mantenedora vê o relato até que haja uma correção.

Descreva o problema, como reproduzi-lo e o impacto esperado. A resposta inicial deve chegar em até 7 dias.

## Versões cobertas

Apenas a versão mais recente do branch `main` recebe correções.

## O que o programa faz, e o que não faz, com seus dados

- Roda **inteiramente no seu computador**. Não há servidor do projeto, coleta de uso nem telemetria.
- Acessa **apenas** as fontes oficiais configuradas (APIs e portais legislativos), a API de localidades do IBGE (no assistente de configuração) e, se você ativar, a API da Anthropic.
- Os anexos baixados (PDFs) e o banco de dados ficam nas pastas `dados/`, `relatorios/`, `analises/` e `explicacoes/`, que o `.gitignore` mantém fora do Git.
- Só são aceitos endereços `http(s)`. Links de outros tipos vindos das fontes externas são descartados, e downloads têm tamanho máximo.
- O texto dos documentos enviado à IA é tratado como dado, não como instrução. Mesmo assim, revise as explicações geradas, que são identificadas como texto de IA.

## Chave da API da Anthropic

- Guarde a chave **somente** na variável de ambiente `ANTHROPIC_API_KEY`. O programa nunca a grava em arquivo.
- **Nunca** coloque a chave em `config.json`, em código ou em issues. Se ela vazar, revogue-a imediatamente em [console.anthropic.com](https://console.anthropic.com).
- Para limitar gastos, defina um limite de uso no Console da Anthropic e ajuste `max_explicacoes_por_ciclo` no `config.json`.

## Para quem contribui

- Pull requests de pessoas de fora passam por revisão antes de qualquer execução automática.
- As ações do GitHub usadas na verificação automática estão fixadas por hash de commit, e o fluxo roda só com permissão de leitura.
- O Dependabot avisa sobre dependências com falhas conhecidas.
