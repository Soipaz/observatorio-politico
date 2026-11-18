"""Coletor do Senado Federal — API de Dados Abertos (legis.senado.leg.br/dadosabertos)."""
from datetime import date
from urllib.parse import urlencode

from .util import baixar

API = "https://legis.senado.leg.br/dadosabertos"
FICHA = "https://www25.senado.leg.br/web/atividade/materias/-/materia/{}"


def _converter(x, eixos=None):
    sigla, resto = (x["identificacao"].split(" ", 1) + [""])[:2]
    numero, _, ano = resto.split(" ")[0].partition("/")
    return {
        "uid": f"senado:{x['id']}",
        "fonte": "senado", "esfera": "federal", "casa": "Senado Federal",
        "sigla": sigla, "numero": numero, "ano": int(ano) if ano.isdigit() else None,
        "identificacao": x["identificacao"],
        "ementa": x.get("ementa", ""), "autor": x.get("autoria", ""),
        "data_apresentacao": x.get("dataApresentacao", ""),
        "situacao": (x.get("situacaoAtual") or "").capitalize(),
        "data_situacao": x.get("dataSituacaoAtual", ""),
        "url": FICHA.format(x["codigoMateria"]), "url_texto": x.get("urlDocumento", ""),
        "eixos": eixos or [],
    }


def _detalhe(pid):
    d = baixar(f"{API}/processo/{pid}")
    aut = d.get("autuacoes") or [{}]
    autores = d.get("autoriaIniciativa") or []
    autor = ""
    if autores:
        a = autores[0]
        autor = f"{a.get('descricaoTipo','').capitalize()} {a.get('autor','')}"
        if a.get("siglaPartido"):
            autor += f" ({a['siglaPartido']}/{a.get('uf','')})"
    return {
        "uid": f"senado:{d['id']}", "fonte": "senado", "esfera": "federal", "casa": "Senado Federal",
        "sigla": d["sigla"], "numero": d["numero"], "ano": d["ano"], "identificacao": d["identificacao"],
        "apelido": d.get("apelido") or "",
        "ementa": (d.get("conteudo") or {}).get("ementa", ""), "autor": autor.strip(),
        "data_apresentacao": (d.get("documento") or {}).get("dataApresentacao", ""),
        "situacao": (d.get("situacaoAtual") or "").capitalize(), "data_situacao": d.get("dataSituacaoAtual", ""),
        "orgao": aut[0].get("siglaColegiadoControleAtual", ""),
        "url": FICHA.format(d["codigoMateria"]),
        "classificacoes": [c.get("descricaoHierarquia", "") for c in d.get("classificacoes") or []],
        "deliberacao": d.get("deliberacao") or {}, "norma": d.get("normaGerada") or {},
        "despachos": d.get("despachos") or [],
    }


def buscar_por_identificacao(sigla, numero, ano):
    r = baixar(f"{API}/processo?{urlencode({'sigla': sigla, 'numero': numero, 'ano': ano})}")
    r = [x for x in r if x.get("tipoDocumento") != "Emenda"]
    return _detalhe(r[0]["id"]) if r else None


def _relevante(x, tipos):
    return x["identificacao"].split(" ")[0] in tipos and x.get("tipoDocumento") != "Emenda" and "(" not in x["identificacao"]


def coletar(banco, clf, cfg, inicio, fim, log):
    tipos = set(cfg["tipos_senado"])
    res = {"novas": [], "mudancas": [], "votacoes": 0}
    dias = min(30, (date.fromisoformat(fim) - date.fromisoformat(inicio)).days + 1)
    atualizados = [x for x in baixar(f"{API}/processo?numdias={dias}") if _relevante(x, tipos)]
    log(f"Senado: {len(atualizados)} proposições atualizadas nos últimos {dias} dias")
    vistos = set()
    for x in atualizados:
        uid = f"senado:{x['id']}"
        vistos.add(uid)
        if banco.existe(uid):
            if banco.salvar(_converter(x)) == "mudou":
                res["mudancas"].append(uid)
            continue
        if not (inicio <= (x.get("dataApresentacao") or "") <= fim):
            continue
        eixos = clf.classificar(x.get("ementa", ""))
        if eixos and banco.salvar(_converter(x, eixos)) == "nova":
            res["novas"].append(uid)
    log(f"Senado: {len(res['novas'])} novas nos 8 eixos, {len(res['mudancas'])} com mudança de situação")

    # acompanhadas que não apareceram na lista: conferir individualmente
    # acompanhadas: sempre consultar a ficha completa (órgão atual, despachos)
    for r in banco.acompanhadas("senado"):
        atualizar(banco, r["uid"].split(":")[1], res if r["uid"] not in vistos else {"mudancas": []})

    # deliberações (decisões) da janela
    try:
        delib = [x for x in baixar(f"{API}/processo?{urlencode({'dataInicioDeliberacao': inicio, 'dataFimDeliberacao': fim})}") if _relevante(x, tipos)]
    except RuntimeError:
        delib = []
    for x in delib:
        eixos = clf.classificar(x.get("ementa", ""))
        uid = f"senado:{x['id']}"
        if not eixos and not banco.existe(uid):
            continue
        if eixos and not banco.existe(uid):
            banco.salvar(_converter(x, eixos))
        banco.votacao({"id": f"senado:{x['id']}:{x.get('dataSituacaoAtual','')}", "fonte": "senado", "data": x.get("dataSituacaoAtual", ""),
                       "orgao": "Senado Federal", "descricao": x.get("ementa", ""), "resultado": (x.get("situacaoAtual") or "").capitalize(),
                       "uid": uid, "identificacao": x["identificacao"], "url": FICHA.format(x["codigoMateria"]), "eixos": ",".join(eixos)})
        res["votacoes"] += 1
    log(f"Senado: {res['votacoes']} deliberações nos 8 eixos")
    banco.commit()
    return res


def atualizar(banco, pid, res):
    d = _detalhe(pid)
    if banco.salvar({k: v for k, v in d.items() if k not in ("classificacoes", "deliberacao", "norma", "despachos")}) == "mudou":
        res["mudancas"].append(d["uid"])
    for desp in d["despachos"]:
        banco.evento(d["uid"], desp.get("data"), "tramite", desp.get("tipoMotivacao", "Despacho"), d.get("orgao"))
    return d
