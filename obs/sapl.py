"""Adaptador SAPL (Sistema de Apoio ao Processo Legislativo, do Interlegis) — API REST aberta.

Usado por muitas Câmaras Municipais e algumas Assembleias Legislativas, normalmente em
https://sapl.<cidade>.<uf>.leg.br ou https://sapl.al.<uf>.leg.br.

Configuração (config.json → "municipal" ou "estadual"):
  {"tipo": "sapl", "id": "pelotas", "url": "https://sapl.pelotas.rs.leg.br",
   "nome": "Câmara Municipal de Pelotas", "esfera": "municipal", "siglas": ["PLO", "PLC", ...]}
"""
import re
from urllib.parse import urlencode

from .util import baixar

SIGLAS_PADRAO = ["PL", "PLO", "PLE", "PLL", "PLC", "PEC", "PELO", "PDL", "VET", "VETO", "VEP", "PI", "PINF"]
MAX_PAGINAS = 30


def _api(fonte, caminho, **params):
    base = fonte["url"].rstrip("/") + "/api/"
    q = urlencode({k: v for k, v in params.items() if v is not None})
    return baixar(base + caminho + ("?" + q if q else ""))


def _paginar(fonte, caminho, **params):
    params.setdefault("page_size", 100)
    for pagina in range(1, MAX_PAGINAS + 1):
        d = _api(fonte, caminho, page=pagina, **params)
        yield from d.get("results", [])
        if not d.get("pagination", {}).get("next_page"):
            break


def tipos(fonte):
    """{id_tipo: sigla} dos tipos de matéria de interesse existentes nesta Casa."""
    if not fonte.get("_tipos"):
        siglas = set(fonte.get("siglas") or SIGLAS_PADRAO)
        todos = list(_paginar(fonte, "materia/tipomaterialegislativa/"))
        escolhidos = [t for t in todos if t["sigla"].strip().upper() in siglas]
        fonte["_tipos"] = {str(t["id"]): t["sigla"].strip() for t in escolhidos}
        fonte["_descricoes"] = sorted({t["descricao"].strip().lower() for t in escolhidos}, key=len, reverse=True)
    return fonte["_tipos"]


def _tramitacao_de_interesse(fonte, t):
    """Filtra pelo texto da tramitação ('<tipo> nº N de AAAA | status | data') sem abrir a matéria."""
    tipos(fonte)
    rotulo = (t.get("__str__") or "").split("|")[0].strip().lower()
    return any(rotulo.startswith(d + " nº") or rotulo.startswith(d + " n°") for d in fonte["_descricoes"])


def _tramite(t):
    partes = [x.strip() for x in (t.get("__str__") or "").split("|")]
    status = partes[1] if len(partes) > 1 else ""
    texto = re.sub(r"<[^>]+>", " ", t.get("texto") or "").strip()
    desc = status + (f" — {texto}" if texto and texto.lower() not in status.lower() else "")
    return {"data": t.get("data_tramitacao") or "", "descricao": desc or "Tramitação", "id": t["id"]}


_autores = {}


def _autor(fonte, aid):
    chave = (fonte["url"], aid)
    if chave not in _autores:
        try:
            _autores[chave] = _api(fonte, f"base/autor/{aid}/").get("nome", "")
        except RuntimeError:
            _autores[chave] = ""
    return _autores[chave]


def _tramitacoes(fonte, mid):
    trs = [_tramite(t) for t in _paginar(fonte, "materia/tramitacao/", materia=mid)]
    trs.sort(key=lambda x: (x["data"], x["id"]))
    return trs


def _montar(fonte, m, trs=None):
    sigla = tipos(fonte).get(str(m.get("tipo")), "")
    if trs is None:
        trs = _tramitacoes(fonte, m["id"])
    ultima = trs[-1] if trs else {}
    base = fonte["url"].rstrip("/")
    autores = [_autor(fonte, a) for a in (m.get("autores") or [])[:3]]
    autor = ", ".join(a for a in autores if a) + (f" e outros ({len(m['autores']) - 3})" if len(m.get("autores") or []) > 3 else "")
    return {
        "uid": f"{fonte['id']}:{m['id']}", "fonte": fonte["id"], "esfera": fonte.get("esfera", "municipal"),
        "casa": fonte["nome"], "sigla": sigla or "?", "numero": str(m.get("numero") or ""), "ano": m.get("ano"),
        "identificacao": f"{sigla or '?'} {m.get('numero')}/{m.get('ano')}",
        "apelido": m.get("apelido") or None,
        "ementa": re.sub(r"\s+", " ", m.get("ementa") or "").strip(), "autor": autor,
        "data_apresentacao": m.get("data_apresentacao") or "",
        "situacao": ultima.get("descricao", ""), "data_situacao": ultima.get("data", ""),
        "orgao": "", "url": f"{base}/materia/{m['id']}", "url_texto": m.get("texto_original") or "",
        "tramites": trs,
    }


def detalhe(fonte, mid):
    return _montar(fonte, _api(fonte, f"materia/materialegislativa/{mid}/"))


def buscar(fonte, cfg, sigla, numero, ano):
    tid = next((k for k, v in tipos(fonte).items() if v.upper() == sigla.upper()), None)
    if not tid:
        return None
    r = _api(fonte, "materia/materialegislativa/", tipo=tid, numero=int(numero), ano=ano).get("results", [])
    return _montar(fonte, r[0]) if r else None


def salvar(banco, d, clf, fonte, eixos=None):
    p = {k: v for k, v in d.items() if k != "tramites"}
    p["eixos"] = eixos if eixos is not None else clf.classificar(d["ementa"])
    estado = banco.salvar(p)
    for tr in d["tramites"]:
        banco.evento(d["uid"], tr["data"], "tramite", tr["descricao"], fonte["nome"])
    return estado


def documentos(fonte, p):
    return [("Texto original", p["url_texto"])] if p.get("url_texto") else []


def _decisao(banco, d, inicio, fonte):
    sit = (d["situacao"] or "").lower()
    if ("aprovad" in sit or "rejeitad" in sit) and (d["data_situacao"] or "") >= inicio:
        p = banco.obter(d["uid"])
        banco.votacao({"id": f"{d['uid']}:{d['data_situacao']}", "fonte": fonte["id"], "data": d["data_situacao"],
                       "orgao": f"Plenário — {fonte['nome']}", "descricao": d["ementa"], "resultado": d["situacao"],
                       "uid": d["uid"], "identificacao": d["identificacao"], "url": d["url"],
                       "eixos": (p["eixos"] if p else "") or ""})
        return 1
    return 0


def coletar(banco, clf, cfg, fonte, inicio, fim, log):
    """Municipal: registra todas as matérias dos tipos de interesse. Estadual: só as que caem nos 8 eixos.

    Para poupar o servidor: uma única consulta traz todas as tramitações da janela; elas são filtradas pelo
    tipo de matéria (pelo próprio texto da tramitação) antes de abrir cada matéria.
    """
    res = {"novas": [], "mudancas": [], "votacoes": 0}
    nome, so_eixos = fonte["nome"], fonte.get("esfera") == "estadual"
    tps = tipos(fonte)
    log(f"{nome}: tipos acompanhados {sorted(set(tps.values()))}")

    # tramitações da janela, agrupadas por matéria (só dos tipos de interesse)
    por_materia = {}
    for t in _paginar(fonte, "materia/tramitacao/", data_tramitacao__gte=inicio, data_tramitacao__lte=fim):
        if t.get("materia") and _tramitacao_de_interesse(fonte, t):
            por_materia.setdefault(t["materia"], []).append(_tramite(t))
    for trs in por_materia.values():
        trs.sort(key=lambda x: (x["data"], x["id"]))
    log(f"{nome}: {len(por_materia)} matérias dos tipos acompanhados tramitaram na janela")

    processados = set()

    def processar(m, trs):
        uid = f"{fonte['id']}:{m['id']}"
        processados.add(m["id"])
        eixos = clf.classificar(m.get("ementa") or "")
        if so_eixos and not eixos and not banco.existe(uid):
            return
        d = _montar(fonte, m, trs if trs else None)
        estado = salvar(banco, d, clf, fonte, eixos)
        if estado == "nova" and (d["data_apresentacao"] or "") >= inicio:
            res["novas"].append(uid)
        elif estado == "mudou":
            res["mudancas"].append(uid)
        res["votacoes"] += _decisao(banco, d, inicio, fonte)

    # 1) matérias apresentadas na janela
    for tid in tps:
        for m in _paginar(fonte, "materia/materialegislativa/", tipo=tid,
                          data_apresentacao__gte=inicio, data_apresentacao__lte=fim):
            processar(m, por_materia.get(m["id"]))

    # 2) matérias antigas que tramitaram na janela
    for mid, trs in por_materia.items():
        if mid in processados:
            continue
        try:
            processar(_api(fonte, f"materia/materialegislativa/{mid}/"), trs)
        except RuntimeError as e:
            log(f"  aviso: {e}")

    # 3) acompanhadas sem tramitação na janela: atualiza mesmo assim
    for r in banco.acompanhadas(fonte["id"]):
        mid = int(r["uid"].split(":")[1])
        if mid in processados:
            continue
        try:
            d = detalhe(fonte, mid)
            if salvar(banco, d, clf, fonte) == "mudou":
                res["mudancas"].append(r["uid"])
        except RuntimeError as e:
            log(f"  aviso: {e}")
    banco.commit()
    log(f"{nome}: {len(res['novas'])} novas, {len(res['mudancas'])} com mudança, {res['votacoes']} decisões")
    return res
