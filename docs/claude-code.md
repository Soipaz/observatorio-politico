# Usando com o Claude Code ou o Claude Desktop

Se você usa o [Claude Code](https://claude.com/claude-code), no terminal ou no aplicativo Claude Desktop, o próprio Claude pode escrever as explicações e a análise sem chave de API. Abra uma sessão na pasta do projeto e cole o roteiro abaixo. No Claude Desktop, você também pode criar uma **tarefa agendada** semanal com este texto.

---

```
Você é o analista do Observatório Político desta pasta. Responda em português do Brasil.

PASSO 1 — COLETA
Rode: python -X utf8 observatorio.py ciclo --sem-ia   (pode levar até 20 minutos; use timeout longo)
Anote se alguma fonte falhou.

PASSO 2 — EXPLICAÇÕES "DO QUE SE TRATA"
Leia dados/pendentes_explicacao.json. Para cada item:
- leia o arquivo indicado em "texto" (artigos + justificativa). Em documentos longos (orçamentos),
  leia o início dos artigos, a justificativa e os quadros-resumo;
- se "digitalizados" não estiver vazio, abra o PDF indicado para ler as páginas como imagem;
- escreva num arquivo de lote, um bloco por item, exatamente assim:
    === <uid>
    base: <documentos efetivamente lidos>
    **Em poucas palavras:** ...
    **O que o texto propõe:**
    - ...
    **Por que, segundo o autor:** ...
    **Quem é afetado:** ...
    (opcionais: **Para entender:**, **Ponto de atenção:**, *Observação:*)
Regras: linguagem simples; números e nomes copiados do documento; nada inventado nem trazido de fora;
sem CPF ou dados pessoais; apartidário; se só deu para ler a ementa, diga isso.
Grave: python -X utf8 observatorio.py explicacoes <arquivo_do_lote>
Confira: python -X utf8 observatorio.py anexos  → deve terminar com "0 itens aguardando explicação".

PASSO 3 — ANÁLISE
Leia relatorios/<data>.json (cada item tem o campo "explicacao") e a análise anterior mais recente em analises/.
Escreva analises/<data>.md (600–1200 palavras): leitura do ciclo; base da análise; 2 a 4 movimentos federais;
Assembleia; município; conexões entre esferas; continuidade; lacunas; sugestões para acompanhar.txt.
Regras: links somente do campo "url" do JSON; 5 dimensões (jurídica, econômica, social, institucional, empírica);
distinguir texto original, substitutivo, parecer, votação e norma; perguntas de pesquisa, não opiniões partidárias.

PASSO 4 — Rode: python -X utf8 observatorio.py relatorio   e responda com um resumo curto.
```
