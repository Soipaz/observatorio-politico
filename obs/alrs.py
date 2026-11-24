"""Coletor da Assembleia Legislativa do RS (ww4.al.rs.gov.br).

A ALRS não oferece API pública nem listagem paginada. Estratégia:
- descobrir proposições novas sondando a numeração sequencial (/proposicao/PL/<n>/<ano>);
- reconsultar a página de cada proposição já registrada para detectar movimentação.
Os links de PDF da ALRS expiram em poucas horas; por isso guardamos sempre o link da página oficial.
"""
import html
import json
import re
from datetime import date

from .util import RAIZ, baixar

SITE = "https://ww4.al.rs.gov.br"
ESTADO = RAIZ / "dados" / "alrs_estado.json"
TIPOS = ["PL"]          # PLC e PEC usam outro padrão de endereço no portal (ainda não mapeado)
VAZIOS_PARA_PARAR = 6   # números consecutivos inexistentes que encerram a sondagem


def _txt(t):
    t = re.sub(r"<[^>]+>", " ", t or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def _iso(dmy):
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", dmy or "")
    return f"{m[3]}-{m[2]}-{m[1]}" if m else ""


def url(sigla, numero, ano):
    return f"{SITE}/proposicao/{sigla}/{int(numero)}/{ano}"


def _campo(t, rotulo):
    m = re.search(rf"<strong>\s*{rotulo}\s*</strong>(.*?)</p>", t, re.S)
    return _txt(m[1]) if m else ""


def _tabela(t, id_):
    i = t.find(f'id="{id_}"')
    if i < 0:
        return []
    fim = t.find('id="content-', i + 10)
    secao = t[i: fim if fim > 0 else len(t)]
    bloco = re.search(r"<tbody>(.*?)</tbody>", secao, re.S)
    linhas = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", bloco[1] if bloco else "", re.S):
        cel = {}
        for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S):
            rot = re.search(r"<span>(.*?)</span>", td, re.S)
            valor = _txt(re.sub(r"<span>.*?</span>", "", td, count=1, flags=re.S))
            if rot:
                cel[_txt(rot[1]).upper()] = valor
        if cel:
            linhas.append(cel)
    return linhas


def _votacoes(t):
    """Blocos de votação da página (comissões e Plenário), com o voto de cada deputado e seu partido."""
    i = t.find('id="content-votacoes"')
    if i < 0:
        return []
    fim = t.find('id="content-', i + 10)
    secao = t[i: fim if fim > 0 else len(t)]
    saida = []
    for bloco in re.split(r'<div class="votacao-bloco">', secao)[1:]:
        titulo = _txt((re.search(r'<span class="titulo">(.*?)</span>', bloco, re.S) or [None, ""])[1])
        resumo = _txt((re.search(r'<div class="votacao-resumo">(.*?)</div>\s*</div>', bloco, re.S) or [None, ""])[1])
        resultado = (re.search(r"Resultado da Votação:\s*([^T]+?)\s*(?:Total|$)", resumo) or [None, ""])[1].strip()
        totais = re.findall(r"Total (?:de Votos|Favorável|Contrário)[^:]*:\s*\d+", resumo)
        votos = []
        for linha in re.findall(r'<div class="tabela-row">(.*?)</div>\s*</div>', bloco + "</div>", re.S):
            cel = [_txt(x) for x in re.findall(r"<div[^>]*>(.*?)</div>", linha + "</div>", re.S)]
            if len(cel) >= 3:
                votos.append({"partido": cel[0], "nome": cel[1], "voto": cel[2]})
        m = re.search(r"(\d{2}/\d{2}/\d{4})", titulo)
        saida.append({"titulo": titulo, "data": _iso(m[1]) if m else "", "resultado": resultado,
                      "placar": " · ".join(totais), "votos": votos})
    return saida


def detalhe(sigla, numero, ano):
    """Retorna dict da proposição ou None se o número não existe."""
    endereco = url(sigla, numero, ano)
    t = baixar(endereco, json_=False)
    t = re.sub(r"<(script|style|svg)[^>]*>.*?</\1>", "", t, flags=re.S)
    linha_tempo = [(_iso(d), _txt(s)) for d, s in re.findall(
        r'<div class="timeline-date">(.*?)</div>\s*<div class="timeline-status">(.*?)</div>', t, re.S)]
    if not linha_tempo:
        return None
    em = re.search(r'id="content-ementa"[^>]*>(.*?)</div>\s*</div>', t, re.S)
    ementa = _txt(re.sub(r"<h4.*?</h4>", "", em[1], flags=re.S)) if em else ""
    if not ementa:
        m = re.findall(r"Ementa\s*</h4>(.*?)</div>", t, re.S)
        ementa = _txt(m[-1]) if m else ""
    ementa = re.sub(r"^Ementa\s*", "", ementa)
    ementa = re.split(r"\s*(?:Vote e Opine|Proposições Acessórias)", ementa)[0].strip()
    situacao = _campo(t, "Situação:")
    datas = sorted(d for d, _ in linha_tempo if d)
    return {
        "uid": f"alrs:{sigla}-{int(numero)}-{ano}",
        "fonte": "alrs", "esfera": "estadual", "casa": "Assembleia Legislativa do RS",
        "sigla": sigla, "numero": str(int(numero)), "ano": int(ano),
        "identificacao": f"{sigla} {int(numero)}/{ano}",
        "ementa": ementa, "autor": _campo(t, "Proponente:"),
        "data_apresentacao": datas[0] if datas else "",
        "situacao": situacao, "data_situacao": datas[-1] if datas else "",
        "orgao": _campo(t, "Tramitação:"),
        "url": endereco, "url_texto": "",
        "linha_tempo": linha_tempo,
        "comissoes": _tabela(t, "content-comissoes"),
        "votacoes": _votacoes(t),
    }


def buscar_por_identificacao(sigla, numero, ano):
    return detalhe(sigla, numero, ano)


def salvar_detalhe(banco, d, eixos):
    p = {k: v for k, v in d.items() if k not in ("linha_tempo", "comissoes", "votacoes")}
    p["eixos"] = eixos
    estado = banco.salvar(p)
    for data, status in d["linha_tempo"]:
        banco.evento(d["uid"], data, "tramite", status.capitalize(), "ALRS")
    for c in d["comissoes"]:
        partes = [f"Comissão {c.get('COMISSÃO', '?')}"]
        if c.get("RELATOR"):
            partes.append(f"relator(a) {c['RELATOR']}")
        if c.get("PARECER"):
            partes.append(f"parecer {c['PARECER']}")
        if c.get("RESULTADO"):
            partes.append(f"resultado: {c['RESULTADO']}")
        data = _iso(c.get("VOTADO EM", "")) or _iso(c.get("DISTRIBUIÇÃO", ""))
        banco.evento(d["uid"], data, "parecer", " — ".join(partes), c.get("COMISSÃO"))
    for v in d["votacoes"]:
        for x in v["votos"]:  # guarda o partido de cada deputado (serve também para mostrar o partido dos autores)
            banco.parlamentar("alrs", x["nome"], x["partido"])
        banco.evento(d["uid"], v["data"], "votacao", f"{v['titulo']} — resultado: {v['resultado'] or '?'} ({v['placar']})", "ALRS")
        if v["data"] and v["data"] >= (banco.inicio_ciclo or "9999"):
            banco.votacao({"id": f"alrs-votacao:{d['uid']}:{v['data']}:{re.sub(r'[^a-z0-9]+', '-', v['titulo'].lower())[:60]}",
                           "fonte": "alrs", "data": v["data"], "orgao": v["titulo"], "descricao": d["ementa"],
                           "resultado": v["resultado"], "uid": d["uid"], "identificacao": d["identificacao"], "url": d["url"],
                           "eixos": ",".join(eixos) if isinstance(eixos, list) else (eixos or "")},
                          v["votos"])
    return estado


def _ler_estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _maior_numero_portal(sigla, ano):
    t = baixar(SITE + "/", json_=False)
    nums = [int(n) for n in re.findall(rf'/proposicao/{sigla}/(\d+)/{ano}"', t)]
    return max(nums) if nums else 0


def _coletar(banco, clf, cfg, inicio, fim, log):
    res = {"novas": [], "mudancas": [], "votacoes": 0}
    estado = _ler_estado()
    ano = date.fromisoformat(fim).year
    sondadas = 0
    for sigla in TIPOS:
        chave = f"{sigla}-{ano}"
        ultimo = estado.get(chave)
        candidatos = []
        if ultimo is None:
            # primeira execução: acha a fronteira e volta no tempo até sair da janela
            base = _maior_numero_portal(sigla, ano)
            n, vazios, fronteira = base, 0, base
            while vazios < VAZIOS_PARA_PARAR:
                n += 1
                sondadas += 1
                d = detalhe(sigla, n, ano)
                if d:
                    candidatos.append(d)
                    fronteira, vazios = n, 0
                else:
                    vazios += 1
            n, fora = base + 1, 0
            while n > 1 and fora < VAZIOS_PARA_PARAR:
                n -= 1
                sondadas += 1
                d = detalhe(sigla, n, ano)
                if not d:
                    continue
                if d["data_apresentacao"] >= inicio:
                    candidatos.append(d)
                    fora = 0
                else:
                    fora += 1
        else:
            n, vazios, fronteira = ultimo, 0, ultimo
            while vazios < VAZIOS_PARA_PARAR:
                n += 1
                sondadas += 1
                d = detalhe(sigla, n, ano)
                if d:
                    candidatos.append(d)
                    fronteira, vazios = n, 0
                else:
                    vazios += 1
        estado[chave] = fronteira
        for d in candidatos:
            if banco.existe(d["uid"]):
                continue
            eixos = clf.classificar(d["ementa"])
            if eixos and salvar_detalhe(banco, d, eixos) == "nova":
                res["novas"].append(d["uid"])
        log(f"ALRS: {sigla} {ano} — fronteira nº {fronteira}, {len(candidatos)} encontradas, {sondadas} páginas sondadas")

    # matérias destacadas no portal (pauta / ordem do dia / recentes): captura votações de projetos antigos
    try:
        t = baixar(SITE + "/", json_=False)
        destaques = dict.fromkeys(re.findall(r'href="/proposicao/(PL)/(\d+)/(\d{4})"', t))
    except RuntimeError:
        destaques = {}
    registrados_destaque = 0
    for sigla, n, a in destaques:
        uid = f"alrs:{sigla}-{int(n)}-{a}"
        if banco.existe(uid):
            continue
        try:
            d = detalhe(sigla, n, a)
        except RuntimeError:
            continue
        if not d or d["data_situacao"] < inicio:
            continue
        eixos = clf.classificar(d["ementa"])
        if eixos:
            salvar_detalhe(banco, d, eixos)
            registrados_destaque += 1
            sit = d["situacao"].lower()
            if "aprovad" in sit or "rejeitad" in sit:
                banco.votacao({"id": f"alrs:{uid}:{d['data_situacao']}", "fonte": "alrs", "data": d["data_situacao"],
                               "orgao": "Plenário da ALRS", "descricao": d["ementa"], "resultado": d["situacao"],
                               "uid": uid, "identificacao": d["identificacao"], "url": d["url"], "eixos": ",".join(eixos)})
                res["votacoes"] += 1
    log(f"ALRS: {len(destaques)} matérias em destaque no portal, {registrados_destaque} registradas (movimentadas na janela, nos 8 eixos)")

    # movimentação das já registradas (inclui acompanhadas)
    conhecidas = banco.con.execute("SELECT uid, sigla, numero, ano FROM proposicoes WHERE fonte='alrs'").fetchall()
    for r in conhecidas:
        if r["uid"] in res["novas"]:
            continue
        try:
            d = detalhe(r["sigla"], r["numero"], r["ano"])
        except RuntimeError as e:
            log(f"  aviso: {e}")
            continue
        if not d:
            continue
        if salvar_detalhe(banco, d, []) == "mudou":
            res["mudancas"].append(d["uid"])
            sit = d["situacao"].lower()
            if ("aprovad" in sit or "rejeitad" in sit) and d["data_situacao"] >= inicio:
                banco.votacao({"id": f"alrs:{d['uid']}:{d['data_situacao']}", "fonte": "alrs", "data": d["data_situacao"],
                               "orgao": "Plenário da ALRS", "descricao": d["ementa"], "resultado": d["situacao"],
                               "uid": d["uid"], "identificacao": d["identificacao"], "url": d["url"],
                               "eixos": banco.obter(d["uid"])["eixos"] or ""})
                res["votacoes"] += 1
    # proposições novas que já chegaram aprovadas/rejeitadas na janela também contam como decisão
    for uid in res["novas"]:
        p = banco.obter(uid)
        sit = (p["situacao"] or "").lower()
        if ("aprovad" in sit or "rejeitad" in sit) and (p["data_situacao"] or "") >= inicio:
            banco.votacao({"id": f"alrs:{uid}:{p['data_situacao']}", "fonte": "alrs", "data": p["data_situacao"],
                           "orgao": "Plenário da ALRS", "descricao": p["ementa"], "resultado": p["situacao"],
                           "uid": uid, "identificacao": p["identificacao"], "url": p["url"], "eixos": p["eixos"] or ""})
            res["votacoes"] += 1
    ESTADO.write_text(json.dumps(estado, indent=1), encoding="utf-8")
    banco.commit()
    log(f"ALRS: {len(res['novas'])} novas nos 8 eixos, {len(res['mudancas'])} com mudança de situação, {res['votacoes']} decisões")
    return res


# ---------------------------------------------------------------- interface comum dos adaptadores
# A ALRS só existe no RS: o id da fonte é sempre "alrs" (uids "alrs:PL-409-2026").

def coletar(banco, clf, cfg, fonte, inicio, fim, log):
    return _coletar(banco, clf, cfg, inicio, fim, log)


def buscar(fonte, cfg, sigla, numero, ano):
    return detalhe(sigla, numero, ano)


def salvar(banco, d, clf, fonte):
    return salvar_detalhe(banco, d, clf.classificar(d["ementa"]) or ["outros"])


def documentos(fonte, p):
    """PDFs da página oficial (links assinados, válidos por poucas horas: baixar na hora)."""
    t = baixar(p["url"], json_=False)
    docs = []
    for u, rot in re.findall(r'href="(https://api-nopaper\.al\.rs\.gov\.br/[^"]+)"[^>]*>([^<]{0,80})', t):
        rot = re.sub(r"\s+", " ", rot).strip() or "Documento"
        if not rot.lower().startswith("anexo"):
            docs.append((rot, u.replace("&amp;", "&")))
    return docs[:2]
