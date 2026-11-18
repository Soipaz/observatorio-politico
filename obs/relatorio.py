"""Gera o relatório semanal: HTML (relatorios/), JSON para análise e notas no Obsidian."""
import html
import json
import re
from datetime import date, datetime

from .util import RAIZ
from .textos import ler_explicacao
from . import locais

PASTA_REL = RAIZ / "relatorios"
PASTA_ANA = RAIZ / "analises"
CASA_CURTA = {"camara": "Câmara", "senado": "Senado"}  # + fontes locais, preenchidas em configurar_nomes()
N = {}  # rótulos do estado/município configurados


def configurar_nomes(cfg):
    N.clear()
    N.update(locais.nomes(cfg))
    for f in locais.fontes(cfg):
        CASA_CURTA[f["id"]] = f.get("curta") or f.get("sigla") or f["nome"]

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def e(t):
    return html.escape(str(t or ""))


def data_br(iso):
    if not iso:
        return ""
    try:
        d = date.fromisoformat(iso[:10])
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return iso


def data_extenso(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


# ---------------------------------------------------------------- dados

def montar(banco, ciclo, cfg):
    c = banco.con
    ini, fim, cid = ciclo["inicio"], ciclo["fim"], ciclo["id"]
    props = {r["uid"]: dict(r) for r in c.execute("SELECT * FROM proposicoes")}

    novas = [props[r["uid"]] for r in c.execute(
        "SELECT DISTINCT uid FROM eventos WHERE ciclo=? AND tipo='apresentacao'", (cid,))
        if props[r["uid"]]["data_apresentacao"] and props[r["uid"]]["data_apresentacao"][:10] >= ini]
    ids_novas = {p["uid"] for p in novas}

    movs = {}
    for r in c.execute("SELECT * FROM eventos WHERE tipo IN ('situacao','tramite','votacao') AND substr(data,1,10) BETWEEN ? AND ? ORDER BY data", (ini, fim + "T99")):
        if r["uid"] in ids_novas or r["uid"] not in props:
            continue
        movs.setdefault(r["uid"], []).append(dict(r))
    movimentadas = [dict(props[u], eventos=ev) for u, ev in movs.items()]

    decisoes = [dict(r) for r in c.execute("SELECT * FROM votacoes WHERE ciclo=? ORDER BY fonte, data", (cid,))]

    acompanhadas = []
    for p in (props[u] for u in props if props[u]["acompanhar"]):
        ev = [dict(r) for r in c.execute("SELECT * FROM eventos WHERE uid=? AND tipo!='apresentacao' ORDER BY data DESC, id DESC LIMIT 6", (p["uid"],))]
        mexeu = any((x["data"] or "")[:10] >= ini for x in ev) or (p["data_situacao"] or "")[:10] >= ini
        acompanhadas.append(dict(p, eventos=ev, mexeu=mexeu))
    acompanhadas.sort(key=lambda p: (not p["mexeu"], p["fonte"], p["identificacao"]))

    resumo = json.loads(ciclo["resumo"] or "{}")
    erros = {k: v["erro"] for k, v in resumo.items() if isinstance(v, dict) and "erro" in v}
    contagem = {k: 0 for k in cfg["eixos"]}
    for p in novas:
        for x in (p["eixos"] or "").split(","):
            if x in contagem:
                contagem[x] += 1
    return {"ciclo": cid, "inicio": ini, "fim": fim, "executado_em": ciclo["executado_em"],
            "novas": novas, "movimentadas": movimentadas, "decisoes": decisoes,
            "acompanhadas": acompanhadas, "contagem_eixos": contagem, "erros": erros}


def uids_do_ciclo(d):
    uids = [p["uid"] for p in d["acompanhadas"] + d["novas"] + d["movimentadas"]]
    uids += [v["uid"] for v in d["decisoes"] if v.get("uid")]
    return list(dict.fromkeys(uids))


# ---------------------------------------------------------------- markdown mínimo (para a análise)

def md_para_html(md):
    out, lista = [], None
    for linha in md.splitlines():
        s = linha.rstrip()
        m_li = re.match(r"^\s*([-*]|\d+\.)\s+(.*)", s)
        if lista and not m_li:
            out.append(f"</{lista}>")
            lista = None
        if not s.strip():
            continue
        inl = e(s)
        inl = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", inl)
        inl = re.sub(r"(?<!\*)\*(?!\s)(.+?)\*", r"<em>\1</em>", inl)
        inl = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', inl)
        h = re.match(r"^(#{1,4})\s+(.*)", inl)
        if h:
            n = min(len(h[1]) + 2, 5)
            out.append(f"<h{n}>{h[2]}</h{n}>")
        elif m_li:
            tipo = "ol" if m_li[1][0].isdigit() else "ul"
            if not lista:
                out.append(f"<{tipo}>")
                lista = tipo
            item = re.sub(r"^\s*([-*]|\d+\.)\s+", "", inl)
            out.append(f"<li>{item}</li>")
        elif s.startswith(">"):
            citacao = re.sub(r"^&gt;\s*", "", inl)
            out.append(f"<blockquote>{citacao}</blockquote>")
        else:
            out.append(f"<p>{inl}</p>")
    if lista:
        out.append(f"</{lista}>")
    return "\n".join(out)


# ---------------------------------------------------------------- HTML

CSS = """
:root{--bg:#f6f5f1;--card:#fff;--ink:#1d1f23;--muted:#5f6670;--line:#e3e1da;--accent:#0a4d8c;--accent-soft:#e8f0f9;--warn:#9a5b00;--warn-soft:#fff4e0;--ok:#1f7a4d;--bad:#b3261e;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#15171a;--card:#1e2125;--ink:#e8e6e1;--muted:#a0a6ae;--line:#33373d;--accent:#7fb2ea;--accent-soft:#1d2a3a;--warn:#f0b35a;--warn-soft:#3a2d17;--ok:#6fcf9b;--bad:#f28b82;}}
:root[data-theme="dark"]{--bg:#15171a;--card:#1e2125;--ink:#e8e6e1;--muted:#a0a6ae;--line:#33373d;--accent:#7fb2ea;--accent-soft:#1d2a3a;--warn:#f0b35a;--warn-soft:#3a2d17;--ok:#6fcf9b;--bad:#f28b82;}
*{box-sizing:border-box}
a{color:var(--accent)}
code{background:var(--accent-soft);padding:1px 5px;border-radius:4px;font-size:.92em}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 "Segoe UI",system-ui,-apple-system,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:28px 16px 80px}
header.top{border-bottom:3px solid var(--ink);padding-bottom:14px;margin-bottom:22px}
.kicker{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-weight:600}
h1{font-family:Georgia,"Times New Roman",serif;font-size:34px;line-height:1.15;margin:6px 0 4px}
h2{font-family:Georgia,serif;font-size:24px;margin:40px 0 6px;padding-top:10px;border-top:1px solid var(--line)}
h3{font-size:17px;margin:22px 0 8px}
.sub{color:var(--muted);margin:0}
nav.toc{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:14px;margin:14px 0 0}
nav.toc a{color:var(--accent);text-decoration:none}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:18px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile b{display:block;font-size:28px;font-family:Georgia,serif}
.tile span{font-size:13px;color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 4px;position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:5}
.chip{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:4px 11px;font-size:13px;cursor:pointer}
.chip[aria-pressed="true"]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.chip i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0}
.card.hot{border-left:4px solid var(--accent)}
.head{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 10px}
.id{font-weight:700;font-size:16px}
.casa{font-size:12px;border:1px solid var(--line);border-radius:4px;padding:1px 6px;color:var(--muted)}
.apelido{font-style:italic;color:var(--muted)}
.tag{font-size:11.5px;border-radius:4px;padding:1px 7px;color:#fff;font-weight:600}
.ementa{margin:6px 0;font-size:14.5px;color:var(--muted)}
.rot{font-size:12px;text-transform:uppercase;letter-spacing:.05em;font-weight:600;margin-right:4px}
.explica{background:var(--accent-soft);border-radius:8px;padding:10px 14px;margin:8px 0;font-size:15.5px}
.explica-t{font-size:12px;text-transform:uppercase;letter-spacing:.08em;font-weight:700;color:var(--accent);margin-bottom:2px}
.explica p{margin:6px 0}.explica ul{margin:4px 0 6px;padding-left:20px}.explica li{margin:2px 0}
.sem-exp{font-style:italic}
td .explica{font-size:14px;margin:6px 0 0}
.meta{font-size:13.5px;color:var(--muted)}
.meta b{color:var(--ink);font-weight:600}
.links{font-size:13.5px;margin-top:6px;display:flex;gap:14px;flex-wrap:wrap}
.links a{color:var(--accent)}
ul.ev{margin:8px 0 0;padding-left:0;list-style:none;font-size:14px}
ul.ev li{padding:3px 0 3px 12px;border-left:2px solid var(--line)}
ul.ev li.novo{border-left-color:var(--accent)}
ul.ev .d{color:var(--muted);font-variant-numeric:tabular-nums;margin-right:6px}
.flag{font-size:12px;font-weight:700;color:var(--accent);background:var(--accent-soft);padding:1px 7px;border-radius:4px}
.res-aprovada{color:var(--ok);font-weight:700}.res-rejeitada{color:var(--bad);font-weight:700}
table{width:100%;border-collapse:collapse;font-size:14px;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.tablewrap{overflow-x:auto}
.aviso{background:var(--warn-soft);border:1px solid var(--line);border-left:4px solid var(--warn);border-radius:8px;padding:12px 14px;margin:12px 0;font-size:14.5px}
.analise{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:6px 20px 14px}
.analise h3,.analise h4{margin-top:18px}
blockquote{border-left:3px solid var(--line);margin:8px 0;padding:2px 12px;color:var(--muted)}
details summary{cursor:pointer;color:var(--accent);font-size:14px;margin:6px 0}
footer{margin-top:50px;font-size:13px;color:var(--muted);border-top:1px solid var(--line);padding-top:12px}
.hidden{display:none!important}
@media (max-width:600px){h1{font-size:27px}.tile b{font-size:23px}}
"""

JS = """
const chips=[...document.querySelectorAll('.chip')];
function aplicar(){const on=chips.filter(c=>c.getAttribute('aria-pressed')==='true').map(c=>c.dataset.eixo);
 document.querySelectorAll('[data-eixos]').forEach(el=>{const ex=el.dataset.eixos.split(',');
  el.classList.toggle('hidden',on.length>0&&!ex.some(x=>on.includes(x)));});}
chips.forEach(c=>c.addEventListener('click',()=>{c.setAttribute('aria-pressed',c.getAttribute('aria-pressed')==='true'?'false':'true');aplicar();}));
"""


def tags(p, cfg):
    out = []
    for x in (p.get("eixos") or "").split(","):
        if x in cfg["eixos"]:
            out.append(f'<span class="tag" style="background:{cfg["eixos"][x]["cor"]}">{e(cfg["eixos"][x]["nome"])}</span>')
    return "".join(out)


def cartao(p, cfg, extra="", hot=False):
    eix = p.get("eixos") or "outros"
    links = [f'<a href="{e(p["url"])}" target="_blank" rel="noopener">Ficha oficial</a>'] if p.get("url") else []
    if p.get("url_texto"):
        links.append(f'<a href="{e(p["url_texto"])}" target="_blank" rel="noopener">Inteiro teor</a>')
    apelido = f'<span class="apelido">“{e(p["apelido"])}”</span>' if p.get("apelido") else ""
    situ = f'<b>Situação:</b> {e(p["situacao"])}' + (f' ({data_br(p["data_situacao"])})' if p.get("data_situacao") else "") if p.get("situacao") else ""
    orgao = f' · <b>Órgão:</b> {e(p["orgao"])}' if p.get("orgao") and p.get("esfera") != "municipal" else ""
    exp = ler_explicacao(p["uid"])
    bloco_exp = (f'<div class="explica"><div class="explica-t">Do que se trata</div>{md_para_html(exp)}</div>' if exp else
                 '<p class="meta sem-exp">Explicação em linguagem acessível ainda não escrita para este item.</p>')
    return f"""<article class="card{' hot' if hot else ''}" data-eixos="{e(eix)}">
<div class="head"><span class="id">{e(p['identificacao'])}</span><span class="casa">{e(p['casa'])}</span>{apelido}{tags(p, cfg)}</div>
<p class="ementa"><span class="rot">Ementa oficial:</span> {e(p['ementa'])}</p>
{bloco_exp}<div class="meta"><b>Autoria:</b> {e(p.get('autor') or '—')} · <b>Apresentação:</b> {data_br(p.get('data_apresentacao'))}<br>{situ}{orgao}</div>
{extra}<div class="links">{''.join(links)}</div></article>"""


def lista_eventos(evs, ini):
    if not evs:
        return ""
    itens = "".join(
        f'<li class="{"novo" if (x["data"] or "")[:10] >= ini else ""}"><span class="d">{data_br(x["data"])}</span>{e(x["descricao"])}'
        + (f' <a href="{e(x["url"])}" target="_blank" rel="noopener">[doc]</a>' if x.get("url") else "") + "</li>" for x in evs)
    return f'<ul class="ev">{itens}</ul>'


def html_relatorio(d, cfg, analise_html):
    ini, fim = d["inicio"], d["fim"]
    fed_novas = [p for p in d["novas"] if p["esfera"] == "federal"]
    mun_novas = [p for p in d["novas"] if p["esfera"] == "municipal"]
    fed_mov = [p for p in d["movimentadas"] if p["esfera"] == "federal"]
    mun_mov = [p for p in d["movimentadas"] if p["esfera"] == "municipal" and not p["acompanhar"]]
    est_novas = [p for p in d["novas"] if p["esfera"] == "estadual"]
    est_mov = [p for p in d["movimentadas"] if p["esfera"] == "estadual" and not p["acompanhar"]]
    mexeram = [p for p in d["acompanhadas"] if p["mexeu"]]

    chips = "".join(f'<button class="chip" data-eixo="{k}" aria-pressed="false"><i style="background:{v["cor"]}"></i>{e(v["nome"])} ({d["contagem_eixos"][k]})</button>'
                    for k, v in cfg["eixos"].items())

    def secao_por_eixo(lista):
        if not lista:
            return '<p class="sub">Nenhuma proposição nesta categoria na janela do ciclo.</p>'
        partes = []
        for k, v in cfg["eixos"].items():
            grupo = [p for p in lista if (p["eixos"] or "").split(",")[0] == k]
            if grupo:
                partes.append(f'<h3 data-eixos="{k}">{e(v["nome"])} <span class="sub">({len(grupo)})</span></h3>' + "".join(cartao(p, cfg) for p in grupo))
        resto = [p for p in lista if (p["eixos"] or "").split(",")[0] not in cfg["eixos"]]
        if resto:
            partes.append('<h3 data-eixos="outros">Outros temas</h3>' + "".join(cartao(p, cfg) for p in resto))
        return "".join(partes)

    acomp = "".join(cartao(p, cfg, ('<span class="flag">MOVIMENTOU NESTA SEMANA</span>' if p["mexeu"] else '<span class="meta">Sem movimentação na janela</span>') + lista_eventos(p["eventos"], ini), hot=p["mexeu"]) for p in d["acompanhadas"])

    def dec_exp(v):
        exp = ler_explicacao(v["uid"]) if v.get("uid") else ""
        return f'<details><summary>Do que se trata</summary><div class="explica">{md_para_html(exp)}</div></details>' if exp else ""

    linhas_dec = ""
    for v in d["decisoes"]:
        res = (v["resultado"] or "").lower()
        cls = "res-aprovada" if "aprov" in res else "res-rejeitada" if "rejeit" in res else ""
        linhas_dec += (f'<tr data-eixos="{e(v["eixos"] or "outros")}"><td>{data_br(v["data"])}</td><td>{e(v["orgao"])}</td>'
                       f'<td><a href="{e(v["url"])}" target="_blank" rel="noopener">{e(v["identificacao"] or "—")}</a></td>'
                       f'<td>{e(v["descricao"])}{dec_exp(v)}</td><td class="{cls}">{e(v["resultado"])}</td></tr>')
    tabela_dec = (f'<div class="tablewrap"><table><thead><tr><th>Data</th><th>Órgão</th><th>Proposição</th><th>Decisão registrada</th><th>Resultado</th></tr></thead><tbody>{linhas_dec}</tbody></table></div>'
                  if linhas_dec else '<p class="sub">Nenhuma votação ou deliberação registrada na janela.</p>')

    def mov_cards(lista):
        if not lista:
            return '<p class="sub">Nenhuma movimentação de proposições já registradas.</p>'
        return "".join(cartao(p, cfg, lista_eventos(p["eventos"][-5:], ini)) for p in lista)

    def secao_local(esfera, novas, movs):
        casa = N["casa_municipal"] if esfera == "municipal" else N["casa_estadual"]
        titulo = (f"Município de {N['municipio']}" if esfera == "municipal" else f"{N['estado']} — {casa}")
        if esfera == "municipal":
            corpo = ''.join(cartao(p, cfg, lista_eventos(list(reversed(p.get('eventos', []))), ini)) for p in novas) or '<p class="sub">Nenhuma matéria nova na janela.</p>'
            corpo = f"<h3>Matérias apresentadas na janela</h3>{corpo}"
        else:
            corpo = f"<h3>Projetos apresentados na janela (8 eixos)</h3>{secao_por_eixo(novas)}"
        obs_ = N["obs_municipal"] if esfera == "municipal" else N["obs_estadual"]
        url = N["url_municipal"] if esfera == "municipal" else N["url_estadual"]
        aviso = (f'<div class="aviso"><b>Cobertura declarada:</b> {obs_}</div>' if obs_ else "")
        consulta = f'<p class="sub">Consulta direta: <a href="{e(url)}" target="_blank" rel="noopener">{e(casa)}</a></p>' if url else ""
        return (f'<section id="{esfera}"><h2>{{n}}. {e(titulo)}</h2>{corpo}<h3>Movimentações</h3>{mov_cards(movs)}{aviso}{consulta}</section>')

    locais_ = []
    if N.get("tem_municipal"):
        locais_.append(("municipal", N["municipio"], secao_local("municipal", mun_novas, mun_mov), len(mun_novas) + len(mun_mov), f"matérias de {N['municipio']} novas ou movimentadas"))
    if N.get("tem_estadual"):
        locais_.append(("estadual", N["uf"], secao_local("estadual", est_novas, est_mov), len(est_novas) + len(est_mov), f"proposições da {N['sigla_estadual']} novas ou movimentadas"))
    secoes_locais, nav_local, tiles_locais = "", "", ""
    for i, (ancora, curto, html_, qtd, rot) in enumerate(locais_, start=7):
        secoes_locais += html_.replace("{n}", str(i))
        nav_local += f'<a href="#{ancora}">{i}. {e(curto)}</a>'
        tiles_locais += f'<div class="tile"><b>{qtd}</b><span>{e(rot)}</span></div>'
    n_metodo = 7 + len(locais_)
    fontes_locais = "".join(f"; {e(f['nome'])}" for f in locais.fontes(cfg))
    links_fontes = "".join(f'<a href="{e(f["url"])}" target="_blank" rel="noopener">{e(f["nome"])}</a> · ' for f in locais.fontes(cfg))
    dec_local = (f" {e(N['sigla_estadual'])}: matérias aprovadas ou rejeitadas na janela." if N.get("tem_estadual") else "")
    if not locais_:
        secoes_locais = ('<div class="aviso">Nenhuma Assembleia ou Câmara Municipal configurada. Rode <code>python observatorio.py configurar</code> '
                         'para escolher seu estado e município.</div>')

    erros = "".join(f'<div class="aviso"><b>Fonte indisponível neste ciclo — {e(CASA_CURTA.get(k, k))}:</b> {e(v)}. Os dados dessa fonte serão recuperados no próximo ciclo.</div>' for k, v in d["erros"].items())
    analise = (f'<div class="analise">{analise_html}</div>' if analise_html else
               '<div class="aviso">A análise acadêmica deste ciclo ainda não foi escrita. Ela é gerada após a coleta, a partir exclusivamente dos documentos listados neste relatório.</div>')

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Observatório Político — {data_br(fim)}</title><style>{CSS}</style></head><body><div class="wrap">
<header class="top"><div class="kicker">Observatório Político · {e(N['titulo'])} · Ciclo {d['ciclo']}</div>
<h1>Relatório semanal — {data_extenso(fim)}</h1>
<p class="sub">Janela de coleta: {data_br(ini)} a {data_br(fim)} · Coleta executada em {data_br(d['executado_em'])} às {d['executado_em'][11:16]} · Fontes: APIs oficiais da Câmara e do Senado{fontes_locais}</p>
<nav class="toc"><a href="#resumo">1. Resumo</a><a href="#analise">2. Análise</a><a href="#acompanhadas">3. Acompanhadas</a><a href="#decisoes">4. Decisões</a><a href="#novas">5. Novas federais</a><a href="#movimentacoes">6. Tramitação</a>{nav_local}<a href="#metodo">{n_metodo}. Método</a><a href="index.html">Todos os relatórios</a></nav></header>
{erros}
<section id="resumo"><h2>1. Resumo executivo</h2>
<div class="tiles"><div class="tile"><b>{len(fed_novas)}</b><span>novas proposições federais nos 8 eixos</span></div>
<div class="tile"><b>{len(d['decisoes'])}</b><span>votações e deliberações registradas</span></div>
<div class="tile"><b>{len(mexeram)}/{len(d['acompanhadas'])}</b><span>acompanhadas com movimentação</span></div>
{tiles_locais}</div>
<p class="sub">Filtre todo o relatório por eixo (clique para combinar):</p><div class="chips">{chips}</div></section>
<section id="analise"><h2>2. Análise acadêmica</h2>{analise}</section>
<section id="acompanhadas"><h2>3. Proposições em acompanhamento prioritário</h2>
<p class="sub">Definidas em <code>acompanhar.txt</code>. Destacadas as que tiveram movimentação na janela; a linha azul marca eventos novos.</p>{acomp or '<p class="sub">Lista vazia.</p>'}</section>
<section id="decisoes"><h2>4. Votações e decisões da semana</h2>
<p class="sub">Câmara: votações de mérito no Plenário (requerimentos procedimentais excluídos). Senado: matérias deliberadas nos 8 eixos.{dec_local}</p>{tabela_dec}</section>
<section id="novas"><h2>5. Novas proposições federais</h2>
<p class="sub">Apresentadas na janela e classificadas nos 8 eixos (por tema oficial da Câmara e por termos da ementa). Homenagens e datas comemorativas excluídas.</p>{secao_por_eixo(fed_novas)}</section>
<section id="movimentacoes"><h2>6. Tramitação de proposições já registradas</h2>
<p class="sub">Mudanças de situação, despachos e pareceres de proposições que o observatório já acompanhava.</p>{mov_cards(fed_mov)}</section>
{secoes_locais}
<section id="metodo"><h2>{n_metodo}. Método e limites</h2>
<p>Cada item deste relatório vem de uma fonte oficial consultada automaticamente, com link para a ficha e, quando disponível, para o inteiro teor. O observatório distingue <b>texto original</b>, <b>substitutivo</b>, <b>parecer</b>, <b>votação</b> e <b>norma publicada</b>. A situação mostrada é a registrada pela própria Casa na data da coleta.</p>
<p><b>"Do que se trata":</b> explicação em linguagem acessível escrita a partir da leitura dos documentos oficiais de cada item (texto do projeto, justificativa, ofício ou mensagem). Ela resume o que o texto diz e o que o autor alega; não é opinião do observatório nem previsão de resultado. Quando o documento não pôde ser lido, isso é dito na própria explicação.</p>
<p>A classificação nos 8 eixos é automática (temas oficiais da Câmara + termos da ementa) e pode conter falsos positivos. Ela serve para triagem, não para análise. Este relatório é uma fotografia da janela indicada, não um inventário exaustivo da atividade legislativa.</p>
<p><b>Fontes:</b> <a href="https://dadosabertos.camara.leg.br" target="_blank" rel="noopener">Dados Abertos da Câmara</a> · <a href="https://legis.senado.leg.br/dadosabertos" target="_blank" rel="noopener">Dados Abertos do Senado</a> · {links_fontes}<a href="https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm" target="_blank" rel="noopener">Constituição Federal</a></p></section>
<footer>Gerado pelo Observatório Político em {datetime.now().strftime('%d/%m/%Y %H:%M')}.</footer>
</div><script>{JS}</script></body></html>"""


def html_indice(cfg):
    itens = []
    for f in sorted(PASTA_REL.glob("20*.html"), reverse=True):
        itens.append(f'<li><a href="{f.name}">Relatório de {data_extenso(f.stem[:10])}</a></li>')
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Observatório Político</title><style>{CSS} li{{margin:6px 0;font-size:17px}} li a{{color:var(--accent)}}</style></head><body><div class="wrap">
<header class="top"><div class="kicker">{e(N.get("titulo", "Brasil"))}</div><h1>Observatório Político</h1><p class="sub">Relatórios semanais a partir de fontes oficiais</p></header>
<ul>{''.join(itens)}</ul></div></body></html>"""


# ---------------------------------------------------------------- Obsidian

def nome_nota(p):
    return f"{p['identificacao'].replace('/', '-')} ({CASA_CURTA.get(p['fonte'], p['fonte'])})"


def nota_proposicao(p, cfg):
    eixos = [cfg["eixos"][x]["nome"] for x in (p["eixos"] or "").split(",") if x in cfg["eixos"]]
    tags_ = " ".join("observatorio/" + x for x in (p["eixos"] or "").split(",") if x)
    evs = "\n".join(f"- **{data_br(x['data'])}** — {x['descricao']}" + (f" ([doc]({x['url']}))" if x.get("url") else "") for x in p["eventos"])
    auto = f"""<!-- auto:inicio — esta parte é atualizada pelo observatório; escreva abaixo de 'Minhas anotações' -->
> [!info] {p['identificacao']} — {p['casa']}{(' · “' + p['apelido'] + '”') if p.get('apelido') else ''}
> **Ementa:** {p['ementa']}
> **Autoria:** {p.get('autor') or '—'} · **Apresentação:** {data_br(p.get('data_apresentacao'))}
> **Situação atual:** {p.get('situacao') or '—'} ({data_br(p.get('data_situacao'))})
> **Eixos:** {', '.join(eixos) or '—'}
> [Ficha oficial]({p['url']}){(' · [Inteiro teor](' + p['url_texto'] + ')') if p.get('url_texto') else ''}

### Do que se trata
{ler_explicacao(p['uid']) or '*Explicação ainda não escrita.*'}

### Últimos eventos
{evs or '- (sem eventos registrados)'}

*Atualizado em {datetime.now().strftime('%d/%m/%Y %H:%M')}*
<!-- auto:fim -->"""
    return auto, f"""---
tipo: proposicao
casa: {p['casa']}
identificacao: "{p['identificacao']}"
esfera: {p['esfera']}
tags: [{', '.join(t for t in tags_.split())}]
---
"""


MODELO_ANOTACOES = """

## Minhas anotações

### Dimensão jurídica
*Compatibilidade com a Constituição, legislação existente e competências federativas.*

### Dimensão econômica
*Custos, fontes de financiamento, renúncias fiscais, efeitos distributivos.*

### Dimensão social
*Grupos afetados, desigualdades, direitos e acesso a serviços.*

### Dimensão institucional
*Competências, responsabilidades, fiscalização, transparência.*

### Dimensão empírica
*Dados, estudos e indicadores que sustentam ou questionam os argumentos.*

### Perguntas em aberto
-
"""


def escrever_obsidian(d, cfg, analise_md):
    base = cfg.get("obsidian_pasta")
    if not base:
        return []
    from pathlib import Path
    base = Path(base)
    (base / "Proposições").mkdir(parents=True, exist_ok=True)
    (base / "Relatórios").mkdir(parents=True, exist_ok=True)
    gerados = []

    for p in d["acompanhadas"]:
        arq = base / "Proposições" / f"{nome_nota(p)}.md"
        auto, front = nota_proposicao(p, cfg)
        if arq.exists():
            atual = arq.read_text(encoding="utf-8")
            if "<!-- auto:inicio" in atual and "<!-- auto:fim -->" in atual:
                novo = re.sub(r"<!-- auto:inicio.*?<!-- auto:fim -->", lambda _: auto, atual, flags=re.S)
            else:
                novo = atual.rstrip() + "\n\n" + auto + "\n"
            tag_nova = re.search(r"^tags: \[.*\]$", front, re.M)
            if tag_nova:
                novo = re.sub(r"^tags: \[.*\]$", lambda _: tag_nova[0], novo, count=1, flags=re.M)
        else:
            novo = front + "\n# " + p["identificacao"] + " — " + p["casa"] + "\n\n" + auto + MODELO_ANOTACOES
        arq.write_text(novo, encoding="utf-8")
        gerados.append(arq)

    def linha(p):
        exp = ler_explicacao(p["uid"])
        m = re.search(r"\*\*Em poucas palavras:\*\*\s*(.+)", exp)
        resumo = m[1].strip() if m else p["ementa"][:220] + ("…" if len(p["ementa"]) > 220 else "")
        return f"- **{p['identificacao']}** ({p['casa']}) — {resumo} [ficha]({p['url']})"

    blocos = []
    for k, v in cfg["eixos"].items():
        g = [p for p in d["novas"] if p["esfera"] == "federal" and (p["eixos"] or "").split(",")[0] == k]
        if g:
            blocos.append(f"### {v['nome']} ({len(g)})\n" + "\n".join(linha(p) for p in g))
    dec = "\n".join(f"| {data_br(v['data'])} | {v['orgao']} | [{v['identificacao'] or '—'}]({v['url']}) | {v['descricao'][:160].replace('|', '/')} | {v['resultado']} |" for v in d["decisoes"])
    acomp = "\n".join(f"- [[{nome_nota(p)}]] — {'🔵 movimentou: ' if p['mexeu'] else ''}{p.get('situacao') or '—'} ({data_br(p.get('data_situacao'))})" for p in d["acompanhadas"])
    mun = "\n".join(linha(p) for p in d["novas"] if p["esfera"] == "municipal") or "- Nenhuma matéria nova na janela."
    est = "\n".join(linha(p) for p in d["novas"] if p["esfera"] == "estadual") or "- Nenhum projeto novo nos 8 eixos na janela."
    bloco_local = ""
    if N.get("tem_municipal"):
        bloco_local += f"## {N['municipio']} — matérias novas\n{mun}\n\n"
    if N.get("tem_estadual"):
        bloco_local += f"## {N['estado']} — {N['sigla_estadual']}\n{est}\n"
        if N.get("obs_estadual"):
            bloco_local += f"\n> [!note] {N['obs_estadual']}\n"
    nota = f"""---
tipo: relatorio-observatorio
ciclo: {d['ciclo']}
janela: {d['inicio']} a {d['fim']}
tags: [observatorio/relatorio]
---
# Observatório Político — {data_extenso(d['fim'])}

Janela: {data_br(d['inicio'])} a {data_br(d['fim'])} · [Abrir relatório completo (HTML)](file:///{(PASTA_REL / (d['fim'] + '.html')).as_posix()})

## Análise acadêmica
{analise_md.strip() if analise_md else '> [!warning] Análise ainda não escrita para este ciclo.'}

## Acompanhamento prioritário
{acomp or '- Lista vazia.'}

## Votações e decisões
| Data | Órgão | Proposição | Decisão | Resultado |
|---|---|---|---|---|
{dec or '| — | — | — | Nenhuma | — |'}

## Novas proposições federais
{chr(10).join(blocos) or '- Nenhuma.'}

{bloco_local}"""
    arq = base / "Relatórios" / f"{d['fim']} Observatório.md"
    arq.write_text(nota, encoding="utf-8")
    gerados.append(arq)

    painel = base / "Observatório Político.md"
    rels = sorted((base / "Relatórios").glob("*.md"), reverse=True)
    painel.write_text(f"""# Observatório Político
{N.get('titulo', 'Brasil')} — acompanhamento semanal a partir de fontes oficiais.

## Relatórios
{chr(10).join(f'- [[{r.stem}]]' for r in rels)}

## Em acompanhamento prioritário
{acomp or '- Lista vazia.'}

*Para incluir ou remover proposições, edite `acompanhar.txt` na pasta do programa.*
""", encoding="utf-8")
    gerados.append(painel)
    return gerados


# ---------------------------------------------------------------- principal

def gerar(banco, ciclo, cfg):
    PASTA_REL.mkdir(exist_ok=True)
    PASTA_ANA.mkdir(exist_ok=True)
    configurar_nomes(cfg)
    d = montar(banco, ciclo, cfg)
    arq_ana = PASTA_ANA / f"{d['fim']}.md"
    analise_md = arq_ana.read_text(encoding="utf-8") if arq_ana.exists() else ""

    # JSON enxuto para a análise acadêmica
    def enxuto(p):
        return dict({k: p.get(k) for k in ("uid", "identificacao", "casa", "apelido", "ementa", "autor", "data_apresentacao", "situacao", "data_situacao", "orgao", "eixos", "url", "url_texto")},
                    explicacao=ler_explicacao(p["uid"]))
    js = {"ciclo": d["ciclo"], "janela": [d["inicio"], d["fim"]],
          "acompanhadas": [dict(enxuto(p), movimentou=p["mexeu"], eventos=[{k: x[k] for k in ("data", "descricao", "url")} for x in p["eventos"]]) for p in d["acompanhadas"]],
          "decisoes": [{k: v[k] for k in ("data", "orgao", "uid", "identificacao", "descricao", "resultado", "url", "eixos")} for v in d["decisoes"]],
          "novas": [enxuto(p) for p in d["novas"]],
          "movimentadas": [dict(enxuto(p), eventos=[{k: x[k] for k in ("data", "descricao")} for x in p["eventos"]]) for p in d["movimentadas"]],
          "erros": d["erros"]}
    arq_json = PASTA_REL / f"{d['fim']}.json"
    arq_json.write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")

    arq_html = PASTA_REL / f"{d['fim']}.html"
    arq_html.write_text(html_relatorio(d, cfg, md_para_html(analise_md) if analise_md else ""), encoding="utf-8")
    (PASTA_REL / "index.html").write_text(html_indice(cfg), encoding="utf-8")
    saida = [arq_html, arq_json]
    try:
        saida += escrever_obsidian(d, cfg, analise_md)
    except OSError as ex:
        print(f"aviso: não consegui escrever no Obsidian: {ex}")
    return saida
