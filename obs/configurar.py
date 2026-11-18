"""Assistente de configuração: escolhe estado e município e descobre os sistemas legislativos locais.

Usa a API de localidades do IBGE para listar estados e municípios e testa os endereços mais comuns:
  - Assembleia: portal da ALRS (RS) ou SAPL em sapl.al.<uf>.leg.br
  - Câmara Municipal: SAPL em sapl.<cidade>.<uf>.leg.br ou <cidade>.votacaoeletronica.inf.br
Se nada for encontrado, a pessoa pode colar o endereço do sistema da sua Câmara/Assembleia.
"""
import json
import re
import shutil
import unicodedata
from urllib.parse import urlparse

from .util import RAIZ, baixar

IBGE = "https://servicodados.ibge.gov.br/api/v1/localidades"
EXEMPLO = RAIZ / "config.exemplo.json"
CONFIG = RAIZ / "config.json"


def _slug(nome, sep=""):
    t = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9 ]", "", t)
    return sep.join(t.split())


def _pergunta(texto, padrao=""):
    r = input(f"{texto}{f' [{padrao}]' if padrao else ''}: ").strip()
    return r or padrao


def _sim(texto, padrao=True):
    r = _pergunta(texto + (" (S/n)" if padrao else " (s/N)")).lower()
    return padrao if not r else r.startswith("s")


def testar_sapl(url):
    try:
        d = baixar(url.rstrip("/") + "/api/materia/tipomaterialegislativa/?page_size=1", tentativas=1, timeout=20)
        return isinstance(d, dict) and "results" in d
    except (RuntimeError, ValueError):
        return False


def sapl_ativo(url):
    """True se o SAPL tem matérias apresentadas nos últimos 12 meses (há Casas que abandonaram o sistema)."""
    from datetime import date, timedelta
    desde = (date.today() - timedelta(days=365)).isoformat()
    try:
        d = baixar(url.rstrip("/") + f"/api/materia/materialegislativa/?data_apresentacao__gte={desde}&page_size=1",
                   tentativas=1, timeout=30)
        return d.get("pagination", {}).get("total_entries", 0) > 0
    except (RuntimeError, ValueError, AttributeError):
        return False


def _confirmar_sapl(url):
    if sapl_ativo(url):
        return True
    print(f"  ⚠ {url} responde, mas não tem matérias registradas no último ano — a Casa pode ter trocado de sistema.")
    return _sim("  Usar mesmo assim?", False)


def testar_votacaoeletronica(url):
    try:
        t = baixar(url.rstrip("/") + "/?sec=nlistaproposicoes", json_=False, tentativas=1, timeout=20)
        return "nlistaproposicoes" in t and ("Espécie" in t or "especie" in t)
    except RuntimeError:
        return False


def detectar(url):
    """Descobre o tipo de sistema de um endereço colado pela pessoa."""
    if not url:
        return None
    if not url.startswith("http"):
        url = "https://" + url
    host = urlparse(url).hostname or ""
    base = f"{urlparse(url).scheme}://{host}"
    if "votacaoeletronica.inf.br" in host and testar_votacaoeletronica(base):
        return {"tipo": "votacaoeletronica", "url": base + "/"}
    if testar_sapl(base):
        return {"tipo": "sapl", "url": base}
    return None


def escolher_estado():
    estados = sorted(baixar(f"{IBGE}/estados"), key=lambda e: e["sigla"])
    print("\nEstados:")
    for i in range(0, len(estados), 9):
        print("  " + "  ".join(f"{e['sigla']}" for e in estados[i:i + 9]))
    while True:
        uf = _pergunta("Sigla do seu estado (ex.: RS)").upper()
        e = next((x for x in estados if x["sigla"] == uf), None)
        if e:
            return e
        print("  Sigla não encontrada, tente de novo.")


def escolher_municipio(uf):
    municipios = baixar(f"{IBGE}/estados/{uf}/municipios")
    while True:
        nome = _pergunta("Nome do seu município (Enter para pular)")
        if not nome:
            return None
        alvo = _slug(nome)
        achados = [m for m in municipios if alvo in _slug(m["nome"])]
        exato = [m for m in achados if _slug(m["nome"]) == alvo]
        if len(exato) == 1:
            return exato[0]
        if len(achados) == 1:
            return achados[0]
        if not achados:
            print("  Nenhum município encontrado com esse nome neste estado.")
            continue
        for i, m in enumerate(achados[:15], 1):
            print(f"  {i}. {m['nome']}")
        n = _pergunta("Número do município")
        if n.isdigit() and 1 <= int(n) <= len(achados[:15]):
            return achados[int(n) - 1]


PREP = {"AC": "do", "AL": "de", "AP": "do", "AM": "do", "BA": "da", "CE": "do", "DF": "do", "ES": "do", "GO": "de",
        "MA": "do", "MT": "de", "MS": "de", "MG": "de", "PA": "do", "PB": "da", "PR": "do", "PE": "de", "PI": "do",
        "RJ": "do", "RN": "do", "RS": "do", "RO": "de", "RR": "de", "SC": "de", "SP": "de", "SE": "de", "TO": "do"}


def _nome_assembleia(estado):
    if estado["sigla"] == "DF":
        return "Câmara Legislativa do Distrito Federal"
    return f"Assembleia Legislativa {PREP.get(estado['sigla'], 'de')} {estado['nome']}"


def fonte_estadual(estado):
    uf = estado["sigla"]
    print(f"\nProcurando o sistema da {_nome_assembleia(estado)}...")
    if uf == "RS":
        print("  ✓ Portal da ALRS (suporte dedicado)")
        return {"tipo": "alrs", "id": "alrs", "nome": "Assembleia Legislativa do RS", "sigla": "ALRS",
                "url": "https://ww4.al.rs.gov.br",
                "cobertura": "são coletados os Projetos de Lei (PL) da ALRS, com situação, linha do tempo, pareceres e votações. "
                             "PLC, PECs estaduais e o Diário Oficial ainda não são coletados."}
    for url in (f"https://sapl.al.{uf.lower()}.leg.br",):
        if testar_sapl(url) and _confirmar_sapl(url):
            print(f"  ✓ SAPL encontrado: {url}")
            return {"tipo": "sapl", "id": f"al{uf.lower()}", "nome": _nome_assembleia(estado),
                    "sigla": f"AL-{uf}", "url": url,
                    "cobertura": "dados da API pública do SAPL da Assembleia (matérias e tramitações). Decisões são inferidas da situação registrada."}
    print("  ✗ Não encontrei automaticamente um sistema compatível (SAPL) para a Assembleia.")
    url = _pergunta("  Se a Assembleia usa SAPL, cole o endereço (ou Enter para pular)")
    d = detectar(url)
    if d and d["tipo"] == "sapl":
        return {"tipo": "sapl", "id": f"al{uf.lower()}", "nome": _nome_assembleia(estado),
                "sigla": f"AL-{uf}", "url": d["url"]}
    if url:
        print("  Endereço não reconhecido. A esfera estadual ficará de fora (veja CONTRIBUINDO.md para adicionar um adaptador).")
    return None


def fonte_municipal(municipio, uf):
    if not municipio:
        return None
    nome = municipio["nome"]
    print(f"\nProcurando o sistema da Câmara Municipal de {nome}...")
    candidatos = []
    for s in dict.fromkeys([_slug(nome), _slug(nome, "-"), _slug(re.sub(r"\b(de|do|da|dos|das)\b", "", nome, flags=re.I))]):
        candidatos += [("sapl", f"https://sapl.{s}.{uf.lower()}.leg.br"),
                       ("votacaoeletronica", f"https://{s}.votacaoeletronica.inf.br/")]
    achado = None
    for tipo, url in candidatos:
        ok = (testar_sapl(url) and _confirmar_sapl(url)) if tipo == "sapl" else testar_votacaoeletronica(url)
        if ok:
            achado = {"tipo": tipo, "url": url}
            print(f"  ✓ {tipo} encontrado: {url}")
            break
    if not achado:
        print("  ✗ Não encontrei automaticamente o sistema da Câmara (testei SAPL e votacaoeletronica).")
        url = _pergunta("  Cole o endereço do sistema legislativo da sua Câmara (ou Enter para pular)")
        achado = detectar(url)
        if url and not achado:
            print("  Endereço não reconhecido. A esfera municipal ficará de fora (veja CONTRIBUINDO.md).")
            return None
    if not achado:
        return None
    f = {"tipo": achado["tipo"], "id": _slug(nome, "-") or "municipio", "nome": f"Câmara Municipal de {nome}",
         "curta": nome, "url": achado["url"]}
    if achado["tipo"] == "votacaoeletronica":
        from . import votacaoeletronica
        f["especies"] = votacaoeletronica.descobrir_especies(f)
        print(f"  espécies acompanhadas: {', '.join(sorted(set(f['especies'].values())))}")
    return f


def assistente():
    print("=" * 64)
    print(" Observatório Político — configuração")
    print(" Federal (Câmara e Senado) já vem incluído. Agora escolha seu estado e município.")
    print("=" * 64)
    if CONFIG.exists():
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        loc = cfg.get("local") or {}
        if loc and not _sim(f"Já existe configuração para {loc.get('municipio') or '-'} / {loc.get('uf') or '-'}. Reconfigurar?", False):
            return
    else:
        cfg = json.loads(EXEMPLO.read_text(encoding="utf-8"))

    estado = escolher_estado()
    municipio = escolher_municipio(estado["sigla"])
    est = fonte_estadual(estado)
    mun = fonte_municipal(municipio, estado["sigla"])

    cfg["local"] = {"uf": estado["sigla"], "estado": estado["nome"],
                    "municipio": municipio["nome"] if municipio else "", "ibge": municipio["id"] if municipio else None}
    cfg["estadual"] = est
    cfg["municipal"] = mun

    pasta = _pergunta("\nPasta de um vault do Obsidian para gerar notas (Enter para não usar)", cfg.get("obsidian_pasta") or "")
    cfg["obsidian_pasta"] = pasta or None

    ia = cfg.setdefault("ia", {"ativo": False, "modelo": "claude-opus-5-5", "esforco": "medium", "max_explicacoes_por_ciclo": 200})
    print("\nExplicações \"Do que se trata\" e análise do ciclo podem ser escritas automaticamente pelo Claude,")
    print("usando sua chave da API da Anthropic (variável de ambiente ANTHROPIC_API_KEY). Isso tem custo por uso.")
    ia["ativo"] = _sim("Ativar a escrita automática pelo Claude?", ia.get("ativo", False))

    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    acomp = RAIZ / "acompanhar.txt"
    if not acomp.exists():
        shutil.copy(RAIZ / "acompanhar.exemplo.txt", acomp)

    print("\n✓ Configuração salva em config.json")
    print(f"  Federal: Câmara dos Deputados e Senado Federal")
    print(f"  Estadual: {est['nome'] + ' (' + est['tipo'] + ')' if est else 'não configurado'}")
    print(f"  Municipal: {mun['nome'] + ' (' + mun['tipo'] + ')' if mun else 'não configurado'}")
    print("\nPróximo passo:  python observatorio.py ciclo")
