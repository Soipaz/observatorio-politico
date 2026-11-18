"""Adaptador para Câmaras Municipais que usam o sistema legislativo <cidade>.votacaoeletronica.inf.br.

Configuração (config.json → "municipal"):
  {"tipo": "votacaoeletronica", "id": "encantado", "url": "https://encantado.votacaoeletronica.inf.br/",
   "nome": "Câmara Municipal de Encantado", "especies": {"1": "PL", "4": "PV", ...}}
Se "especies" não for informado, o adaptador descobre os códigos pela página de busca do sistema.
"""
import html
import re
from datetime import date
from urllib.parse import urlencode, urlparse

from .util import baixar

# espécies acompanhadas por padrão (siglas usadas pelo sistema)
SIGLAS_PADRAO = ["PL", "PV", "PC", "PELO", "VTT", "PINF", "PLE", "PLL", "PLC", "PEL"]


def _site(fonte):
    u = fonte["url"].rstrip("/") + "/"
    return u


def _arquivos(fonte):
    # PDFs ficam num servidor separado: arquivos-<sub>.votacaoeletronica.inf.br
    host = urlparse(fonte["url"]).hostname or ""
    return f"https://arquivos-{host.split('.')[0]}.votacaoeletronica.inf.br/"


def _limpar(t):
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def _iso(dmy):
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", dmy or "")
    return f"{m[3]}-{m[2]}-{m[1]}" if m else ""


def descobrir_especies(fonte):
    """Lê a lista de espécies da página de busca e devolve {codigo: sigla} das siglas de interesse."""
    t = baixar(_site(fonte) + "?sec=nlistaproposicoes", json_=False)
    achadas = {}
    for cod, sigla in re.findall(r'<option value="(\d+)">\s*([A-Z]+)\s*-', t):
        if sigla in SIGLAS_PADRAO:
            achadas[cod] = sigla
    return achadas


def _especies(fonte):
    if not fonte.get("especies"):
        fonte["especies"] = descobrir_especies(fonte)
    return fonte["especies"]


def listar(fonte, especie, ano, max_paginas=20):
    """Retorna [(id, titulo)] de uma espécie/ano, mais recentes primeiro."""
    itens = []
    for pagina in range(1, max_paginas + 1):  # paginação do sistema começa em 1
        q = urlencode({"sec": "nlistaproposicoes", "especie": especie, "ano": ano, "page": pagina})
        t = baixar(_site(fonte) + "?" + q, json_=False)
        achados = re.findall(r'href="\?sec=proposicao&id=(\d+)"[^>]*>.*?<span class="pe_tit">(.*?)</span>', t, re.S)
        if not achados:
            break
        itens += [(int(i), _limpar(tit)) for i, tit in achados]
        if f"page={pagina + 1}" not in t:
            break
    return itens


def _ementa(titulo):
    # "PL 065/2026 - PROJETO DE LEI N°065/2026, DE 05 DE NOVEMBRO DE 2026. Altera ..." -> "Altera ..."
    _, _, resto = titulo.partition(" - ")
    resto = re.sub(r"^.{0,80}?\bDE \d{1,2}°? DE [A-ZÇ]+ DE \d{4}[.,]?\s*(que\s+)?", "", resto, flags=re.I)
    return resto.strip() or titulo


def detalhe(fonte, pid):
    site = _site(fonte)
    t = baixar(f"{site}?sec=proposicao&id={pid}", json_=False)
    titulo = _limpar((re.search(r'<div class="row proposicao">\s*<h1>(.*?)</h1>', t, re.S) or [None, ""])[1])
    proponente = _limpar((re.search(r"Proponente:\s*(.*?)</h3>", t, re.S) or [None, ""])[1])
    docs = [(_limpar(n), site + html.unescape(h)) for h, n in re.findall(r'<a href="(pdf\.view\.php[^"]+)" class="btn-green[^"]*">(.*?)</a>', t)]
    tramites = []
    corpo = (re.search(r'id="tbl_tramite".*?<tbody>(.*?)</tbody>', t, re.S) or [None, ""])[1]
    for linha in re.findall(r"<tr>(.*?)</tr>", corpo, re.S):
        cols = re.findall(r"<td[^>]*>(.*?)</td>", linha, re.S)
        if len(cols) >= 2:
            link = re.search(r'href="(pdf\.view\.php[^"]+)"', cols[2] if len(cols) > 2 else "")
            tramites.append({"data": _iso(_limpar(cols[0])), "descricao": _limpar(cols[1]),
                             "url": site + html.unescape(link[1]) if link else None})
    m = re.match(r"([A-Z]+)\s+(\d+)/(\d{4})", titulo)
    ultima = tramites[-1] if tramites else {}
    inicio = _iso((re.search(r"In[ií]cio da Tramita[çc][ãa]o da Proposi[çc][ãa]o:\s*([\d/]+)", t) or [None, ""])[1])
    return {
        "uid": f"{fonte['id']}:{pid}", "fonte": fonte["id"], "esfera": fonte.get("esfera", "municipal"),
        "casa": fonte["nome"],
        "sigla": m[1] if m else "", "numero": m[2] if m else "", "ano": int(m[3]) if m else None,
        "identificacao": f"{m[1]} {m[2]}/{m[3]}" if m else titulo[:30],
        "ementa": _ementa(titulo), "autor": proponente.replace("()", "").strip(),
        "data_apresentacao": inicio or (tramites[0]["data"] if tramites else ""),
        "situacao": ultima.get("descricao", ""), "data_situacao": ultima.get("data", ""),
        "url": f"{site}?sec=proposicao&id={pid}",
        "url_texto": next((u for n, u in docs if "original" in n.lower()), docs[0][1] if docs else ""),
        "documentos": docs, "tramites": tramites,
    }


def buscar(fonte, cfg, sigla, numero, ano):
    especie = next((k for k, v in _especies(fonte).items() if v == sigla), None)
    if not especie:
        return None
    q = urlencode({"sec": "nlistaproposicoes", "especie": especie, "numero": int(numero), "ano": ano})
    t = baixar(_site(fonte) + "?" + q, json_=False)
    m = re.search(r'href="\?sec=proposicao&id=(\d+)"', t)
    return detalhe(fonte, int(m[1])) if m else None


def salvar(banco, d, clf, fonte):
    eixos = clf.classificar(d["ementa"])
    p = {k: v for k, v in d.items() if k not in ("documentos", "tramites")}
    p["eixos"] = eixos
    estado = banco.salvar(p)
    for tr in d["tramites"]:
        banco.evento(d["uid"], tr["data"], "tramite", tr["descricao"], fonte["nome"], tr["url"])
    return estado


def documentos(fonte, p):
    """[(rótulo, url do PDF)] — o pdf.view.php é só um visualizador; o PDF real está no parâmetro url=."""
    d = detalhe(fonte, int(p["uid"].split(":")[1]))

    def direto(u):
        m = re.search(r"[?&]url=([^&]+)", u)
        return _arquivos(fonte) + m[1] if m else u
    docs = [(n, direto(u)) for n, u in d["documentos"]]
    principais = [x for x in docs if not re.search(r"anexad|anexo|planilha", x[0], re.I)]
    return (principais + [x for x in docs if x not in principais])[:3]


def coletar(banco, clf, cfg, fonte, inicio, fim, log):
    res = {"novas": [], "mudancas": [], "votacoes": 0}
    nome = fonte["nome"]
    anos = {date.fromisoformat(fim).year, date.fromisoformat(inicio).year}
    ids = []
    for especie in _especies(fonte):
        for a in anos:
            ids += [i for i, _ in listar(fonte, especie, a)]
    for r in banco.acompanhadas(fonte["id"]):
        ids.append(int(r["uid"].split(":")[1]))
    ids = list(dict.fromkeys(ids))
    log(f"{nome}: {len(ids)} proposições do ano para conferir")
    for pid in ids:
        try:
            d = detalhe(fonte, pid)
        except RuntimeError as e:
            log(f"  aviso: {e}")
            continue
        estado = salvar(banco, d, clf, fonte)
        if estado == "nova":
            res["novas"].append(d["uid"])
        elif estado == "mudou":
            res["mudancas"].append(d["uid"])
    banco.commit()
    log(f"{nome}: {len(res['novas'])} registradas pela primeira vez, {len(res['mudancas'])} com nova movimentação")
    return res
