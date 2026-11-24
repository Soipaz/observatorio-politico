# Observatório Político

Acompanhamento legislativo semanal **a partir de fontes oficiais**, com histórico permanente e explicações em linguagem acessível.

Você escolhe **o seu estado e o seu município**, e o programa acompanha toda semana:

| Esfera | Fonte | Como |
|---|---|---|
| Federal | Câmara dos Deputados | API Dados Abertos v2 |
| Federal | Senado Federal | API Dados Abertos |
| Estadual | Assembleia Legislativa do seu estado | SAPL/Interlegis (API aberta) ou adaptador dedicado (ALRS) |
| Municipal | Câmara Municipal da sua cidade | SAPL/Interlegis ou sistema *votacaoeletronica* |

O relatório semanal (HTML e, se você quiser, notas no Obsidian) traz:

- **o que mudou desde a última atualização**: para cada proposição que andou, a situação de antes e a de agora, os novos andamentos e, em linguagem simples, o que isso significa (as proposições acompanhadas aparecem primeiro);
- **novas proposições** nos 8 eixos temáticos: economia/orçamento, trabalho/previdência, direitos/Constituição, desigualdade/políticas sociais, educação, saúde, segurança/justiça e meio ambiente;
- **votações e decisões** da semana, com o **placar** e **como votou cada parlamentar** (nome, partido e estado), quando a Casa publica o voto nominal (Câmara, Senado e Assembleia do RS);
- **autoria com partido** em todas as proposições;
- **tramitação** das proposições acompanhadas, com linha do tempo;
- um quadro **"Do que se trata"** para cada item, escrito a partir da leitura dos anexos oficiais: texto do projeto, justificativa, mensagem e parecer;
- uma **análise do ciclo** em 5 dimensões (jurídica, econômica, social, institucional e empírica).

> Princípios: todo item tem link para a ficha oficial; a situação é a que a própria Casa registra; lacunas são declaradas, nunca preenchidas com notícias ou suposições; o conteúdo é apartidário.

---

## Instalação

Você precisa do **Python 3.10 ou mais recente** ([python.org](https://www.python.org/downloads/)).

```bash
git clone https://github.com/Soipaz/observatorio-politico.git
cd observatorio-politico
pip install -r requirements.txt
```

## Primeiros passos

**1. Escolha seu estado e município**

```bash
python observatorio.py configurar
```

O assistente usa a lista oficial do IBGE e **descobre sozinho** o sistema da sua Assembleia e da sua Câmara. Ele procura SAPL em `sapl.al.<uf>.leg.br` e `sapl.<cidade>.<uf>.leg.br`, e também `<cidade>.votacaoeletronica.inf.br`. Se não encontrar, você pode colar o endereço do sistema.

**2. Rode o primeiro ciclo**

```bash
python observatorio.py ciclo
```

O primeiro ciclo cobre os últimos 7 dias. Os seguintes começam de onde o anterior parou.

**3. Abra o relatório:** `relatorios/ultimo.html` (o mais recente) ou `relatorios/index.html` (todos)

O relatório também é salvo em **PDF** (`relatorios/ultimo.pdf` e `relatorios/AAAA-MM-DD.pdf`) quando há Microsoft Edge, Google Chrome ou Chromium instalado; para desligar, use `"pdf": false` no `config.json`.

No Windows, basta dar duplo clique em **`Rodar ciclo agora.bat`**. Na primeira vez, ele abre o assistente de configuração.

### Acompanhar proposições específicas

Edite `acompanhar.txt` (criado a partir de `acompanhar.exemplo.txt`):

```
camara PL 1234/2026
senado PLP 299/2026
estado PL 409/2026
municipio PL 71/2026
```

Esses itens aparecem em destaque, com o histórico completo.

### Rodar toda semana

- **Windows:** use o Agendador de Tarefas para executar `Rodar ciclo agora.bat`.
- **Linux/macOS:** use o cron, por exemplo:

```
0 19 * * 1  cd /caminho/observatorio-politico && python3 observatorio.py ciclo
```

---

## Explicações "Do que se trata" e análise

O programa baixa e lê os anexos oficiais de cada item (PDFs) e guarda o texto em `dados/textos/`. Há três formas de escrever as explicações e a análise:

**A. Automático, pela API da Anthropic (opcional, pago por quem usa)**

1. Crie uma chave em [console.anthropic.com](https://console.anthropic.com) e defina a variável de ambiente `ANTHROPIC_API_KEY`.
2. Ative em `python observatorio.py configurar` ou em `config.json`, no campo `"ia": {"ativo": true}`.

A cada ciclo, o programa escreve as explicações que faltam e a análise. Também dá para rodar separadamente com `python observatorio.py explicar` e `python observatorio.py analisar`. O modelo padrão é `claude-opus-5-5`, com recurso automático a um modelo alternativo se o principal recusar uma solicitação. Para limitar o custo, use `"max_explicacoes_por_ciclo"`. As explicações já escritas são reaproveitadas e só são refeitas quando o texto oficial muda.

**B. Com o Claude Code ou o Claude Desktop (sem chave de API)**

Siga as instruções em [`docs/claude-code.md`](docs/claude-code.md). O Claude lê os anexos, escreve as explicações num arquivo de lote e as grava com `python observatorio.py explicacoes LOTE.md`.

**C. Sem IA**

O relatório sai com os dados oficiais, as ementas e os links. Cada item mostra o aviso "explicação ainda não escrita".

> As explicações e análises geradas por IA são identificadas como tal no rodapé de cada quadro. Elas resumem o que os documentos dizem e não substituem a leitura do texto oficial.

---

## Comandos

| Comando | O que faz |
|---|---|
| `python observatorio.py configurar` | escolhe o estado e o município e detecta os sistemas |
| `python observatorio.py ciclo [--dias N] [--sem-ia]` | coleta, baixa os anexos, escreve com IA (se ativa) e gera o relatório |
| `python observatorio.py explicar` | IA: escreve as explicações pendentes |
| `python observatorio.py analisar` | IA: escreve a análise do último ciclo |
| `python observatorio.py relatorio` | regera o relatório (por exemplo, depois de editar a análise) |
| `python observatorio.py anexos` | baixa e lê os anexos e lista o que falta explicar |
| `python observatorio.py explicacoes LOTE.md` | importa explicações escritas fora do programa |
| `python observatorio.py status` | resumo do banco de dados |

## Estrutura

```
observatorio.py          programa principal
obs/                     coletores (camara, senado, sapl, alrs, votacaoeletronica), banco, anexos, IA e relatório
config.exemplo.json      modelo de configuração (eixos, palavras-chave, temas oficiais)
acompanhar.exemplo.txt   modelo da lista de acompanhamento
docs/                    guias (uso com Claude Code)
--- criados na sua máquina (não vão para o git) ---
config.json, acompanhar.txt
dados/                   banco SQLite com o histórico + anexos baixados
relatorios/              AAAA-MM-DD.html e .json
analises/                análise de cada ciclo (Markdown)
explicacoes/             uma explicação por proposição
```

## Cobertura e limites

- **Estados:** funciona onde a Assembleia publica no **SAPL** (testado: Acre, Roraima e Piauí) e no **RS**, que tem adaptador próprio para o portal da ALRS, cobrindo só os Projetos de Lei. Em outros estados, a esfera estadual fica de fora até alguém contribuir um adaptador.
- **Municípios:** funciona em Câmaras com **SAPL** (por exemplo, Pelotas/RS e João Pessoa/PB) ou com o sistema **votacaoeletronica** (por exemplo, Encantado/RS). Muitas Câmaras usam outros sistemas: veja abaixo como ajudar.
- **Decisões nas esferas locais** são inferidas da situação registrada ("aprovado" ou "rejeitado"). Elas não incluem o placar nominal.
- **Classificação temática** é automática (palavras-chave e temas oficiais da Câmara) e serve para triagem. Pode ter falsos positivos.

## Contribuindo

O caminho mais valioso para contribuir é **escrever adaptadores** para outros sistemas legislativos, de Assembleias e de Câmaras Municipais. Veja [`CONTRIBUINDO.md`](CONTRIBUINDO.md).

## Licença

[MIT](LICENSE) © 2026 noticia_na_politica
