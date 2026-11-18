"""Coletor da Câmara dos Deputados — API de Dados Abertos v2 (dadosabertos.camara.leg.br)."""
import re
from urllib.parse import urlencode

from .util import baixar

API = "https://dadosabertos.camara.leg.br/api/v2"
FICHA = "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={}"


def _paginar(caminho, params):
    url = f"{API}/{caminho}?{urlencode({**params, 'itens': 100})}"
    while url:
        r = baixar(url)
        yield from r.get("dados", [])
        url = next((l["href"] for l in r.get("links", []) if l["rel"] == "next"), None)


def _detalhe(pid):
    d = baixar(f"{API}/proposicoes/{pid}")["dados"]
    st = d.get("statusProposicao") or {}
    autor = ""
    try:
        autores = baixar(f"{API}/proposicoes/{pid}/autores")["dados"]
        if autores:
            a = min(autores, key=lambda x: (x.get("ordemAssinatura") or 999))  # primeiro signatário
            autor = a.get("nome", "")
            extra = len(autores) - 1
            if extra > 0:
                autor += f" e outros ({extra})"
    except RuntimeError:
        pass
    situacao = st.get("descricaoSituacao") or st.get("descricaoTramitacao") or ""
    return {
        "uid": f"camara:{pid}",
        "fonte": "camara", "esfera": "federal", "casa": "Câmara dos Deputados",
        "sigla": d["siglaTipo"], "numero": str(d["numero"]), "ano": d["ano"],
        "identificacao": f"{d['siglaTipo']} {d['numero']}/{d['ano']}",
        "ementa": d.get("ementa", ""), "autor": autor,
        "data_apresentacao": (d.get("dataApresentacao") or "")[:10],
        "situacao": situacao, "data_situacao": st.get("dataHora", ""),
        "orgao": st.get("siglaOrgao", ""),
        "despacho": st.get("despacho", ""),
        "url": FICHA.format(pid), "url_texto": d.get("urlInteiroTeor") or "",
    }


def buscar_por_identificacao(sigla, numero, ano):
    r = baixar(f"{API}/proposicoes?{urlencode({'siglaTipo': sigla, 'numero': numero, 'ano': ano})}")["dados"]
    return _detalhe(r[0]["id"]) if r else None


def coletar(banco, clf, cfg, inicio, fim, log):
    tipos = ",".join(cfg["tipos_camara"])
    res = {"novas": [], "mudancas": [], "votacoes": 0}

    # 1) temas oficiais das proposições apresentadas na janela
    temas = {}
    codigos = sorted({c for e in cfg["eixos"].values() for c in e.get("temas_camara", [])})
    for cod in codigos:
        for p in _paginar("proposicoes", {"codTema": cod, "siglaTipo": tipos, "dataApresentacaoInicio": inicio, "dataApresentacaoFim": fim}):
            temas.setdefault(p["id"], set()).add(cod)

    # 2) novas proposições
    apresentadas = list(_paginar("proposicoes", {"siglaTipo": tipos, "dataApresentacaoInicio": inicio, "dataApresentacaoFim": fim}))
    log(f"Câmara: {len(apresentadas)} proposições apresentadas na janela")
    for p in apresentadas:
        eixos = clf.classificar(p["ementa"], temas.get(p["id"], ()))
        if not eixos or banco.existe(f"camara:{p['id']}"):
            continue
        d = _detalhe(p["id"])
        d["eixos"] = eixos
        if banco.salvar(d) == "nova":
            res["novas"].append(d["uid"])
    log(f"Câmara: {len(res['novas'])} novas nos 8 eixos")

    # 3) movimentação das proposições já registradas
    conhecidas = banco.uids("camara")
    movimentadas = {p["id"] for p in _paginar("proposicoes", {"siglaTipo": tipos, "dataInicio": inicio, "dataFim": fim})}
    alvo = [pid for pid in movimentadas if f"camara:{pid}" in conhecidas and f"camara:{pid}" not in res["novas"]]
    log(f"Câmara: {len(alvo)} proposições registradas com movimentação")
    for pid in alvo:
        atualizar(banco, pid, inicio, fim, res)
    # acompanhadas sempre são conferidas
    for r in banco.acompanhadas("camara"):
        pid = r["uid"].split(":")[1]
        if int(pid) not in movimentadas:
            atualizar(banco, pid, inicio, fim, res)

    # 4) votações do Plenário
    res["votacoes"] = coletar_votacoes(banco, clf, inicio, fim, log)
    banco.commit()
    return res


def atualizar(banco, pid, inicio, fim, res):
    d = _detalhe(pid)
    if banco.salvar(d) == "mudou":
        res["mudancas"].append(d["uid"])
    try:
        for t in baixar(f"{API}/proposicoes/{pid}/tramitacoes?{urlencode({'dataInicio': inicio, 'dataFim': fim})}")["dados"]:
            desc = t.get("despacho") or t.get("descricaoTramitacao") or ""
            if t.get("descricaoSituacao"):
                desc = f"[{t['descricaoSituacao']}] {desc}"
            banco.evento(d["uid"], t.get("dataHora"), "tramite", desc, t.get("siglaOrgao"), t.get("url"))
    except RuntimeError:
        pass


def coletar_votacoes(banco, clf, inicio, fim, log):
    n = 0
    for v in _paginar("votacoes", {"idOrgao": 180, "dataInicio": inicio, "dataFim": fim}):
        desc = v.get("descricao") or ""
        if re.match(r"(aprovad|rejeitad)[oa]s?[^.]{0,40}?requerimento", desc.lower()):
            continue
        if desc.lower().startswith(("aprovado o requerimento", "rejeitado o requerimento", "aprovado requerimento", "rejeitado requerimento",
                                   "alteração do regime de tramitação")):
            continue
        uid = ident = ""
        eixos = []
        det = {}
        try:
            det = baixar(f"{API}/votacoes/{v['id']}")["dados"]
            afetadas = det.get("proposicoesAfetadas") or []
            obj = det.get("ultimaApresentacaoProposicao") or {}
            alvo = afetadas[0] if afetadas else None
            if alvo:
                ident = f"{alvo.get('siglaTipo')} {alvo.get('numero')}/{alvo.get('ano')}"
                uid = f"camara:{alvo['id']}"
                eixos = clf.classificar((alvo.get("ementa") or "") + " " + desc)
                if not banco.existe(uid):  # registra mesmo fora dos 8 eixos, para o relatório poder explicar a decisão
                    d = _detalhe(alvo["id"])
                    d["eixos"] = eixos or ["outros"]
                    banco.salvar(d)
            elif obj:
                eixos = clf.classificar((obj.get("descricao") or "") + " " + desc)
        except RuntimeError:
            pass
        resultado = "aprovada" if det.get("aprovacao") == 1 else "rejeitada" if det.get("aprovacao") == 0 else ""
        banco.votacao({"id": f"camara:{v['id']}", "fonte": "camara", "data": v.get("dataHoraRegistro") or v.get("data"),
                       "orgao": "Plenário da Câmara", "descricao": desc, "resultado": resultado, "uid": uid,
                       "identificacao": ident, "url": FICHA.format(uid.split(":")[1]) if uid else v.get("uri", ""),
                       "eixos": ",".join(eixos)})
        if uid:
            banco.evento(uid, v.get("dataHoraRegistro"), "votacao", desc, "PLEN")
        n += 1
    log(f"Câmara: {n} votações de mérito no Plenário")
    return n
