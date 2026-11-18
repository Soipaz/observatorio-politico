# Contribuindo

Contribuições são bem-vindas, especialmente **adaptadores para novos sistemas legislativos**. Cada Assembleia e cada Câmara Municipal usa um sistema diferente, e é isso que limita a cobertura do projeto.

## Como funciona um adaptador

Um adaptador é um módulo em `obs/` registrado em `ADAPTADORES`, no arquivo `obs/locais.py`. Ele implementa quatro funções, que recebem o dicionário `fonte` vindo de `config.json` (`"estadual"` ou `"municipal"`):

```python
def coletar(banco, clf, cfg, fonte, inicio, fim, log) -> dict:
    """Registra no banco as proposições novas e as movimentações da janela [inicio, fim] (datas ISO).
    Retorna {"novas": [uids], "mudancas": [uids], "votacoes": int}."""

def buscar(fonte, cfg, sigla, numero, ano) -> dict | None:
    """Encontra uma proposição específica (usado pela lista acompanhar.txt)."""

def salvar(banco, d, clf, fonte) -> str | None:
    """Grava a proposição e seus eventos; devolve 'nova', 'mudou' ou None."""

def documentos(fonte, p) -> list[tuple[str, str]]:
    """[(rótulo, url_do_pdf)] dos documentos oficiais a ler para as explicações."""
```

O dicionário de proposição que vai para `banco.salvar()` segue os campos de `obs/db.py`, entre eles:
`uid` (`"<id da fonte>:<id na origem>"`), `fonte` (o `id` da fonte), `esfera` (`estadual` ou `municipal`), `casa`, `sigla`, `numero`, `ano`, `identificacao`, `ementa`, `autor`, `data_apresentacao`, `situacao`, `data_situacao`, `url` (ficha oficial), `url_texto` (inteiro teor) e `eixos` (lista vinda de `clf.classificar(ementa)`).

Use `banco.evento(uid, data, tipo, descricao, orgao, url)` para registrar a tramitação (`tipo`: `tramite`, `parecer` ou `votacao`). Use `banco.votacao({...})` para as decisões da semana.

Os adaptadores `obs/sapl.py` (API REST) e `obs/votacaoeletronica.py` (leitura de HTML) são bons modelos.

## Regras do projeto

1. **Somente fontes oficiais.** Nada de notícias ou agregadores.
2. **Seja gentil com os servidores públicos:** faça poucas requisições, use paginação e não use paralelismo agressivo.
3. **Não invente dados.** Se a fonte não informa algo, deixe vazio, e o relatório declara a lacuna.
4. **Dados pessoais:** não colete nem exiba mais do que a própria Casa publica na ficha da proposição.
5. **Apartidário:** os textos do relatório e os prompts da IA devem permanecer neutros.

## Detecção automática

Se o seu sistema tem um endereço previsível (como `sapl.<cidade>.<uf>.leg.br`), adicione o teste em `obs/configurar.py` para que o assistente o encontre sozinho.

## Testando

Configure uma cópia do projeto para a Casa do seu adaptador e rode:

```bash
python observatorio.py ciclo --dias 7 --sem-ia
```

Confira o relatório em `relatorios/` e abra um Pull Request descrevendo a Casa testada e o que é coletado.
