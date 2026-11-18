"""Fontes estaduais e municipais configuráveis (config.json → "estadual" e "municipal").

Cada fonte é um dicionário com, no mínimo: tipo (adaptador), id (prefixo dos identificadores), nome, url.
Adaptadores disponíveis:
  alrs               Assembleia Legislativa do RS (portal ww4.al.rs.gov.br)
  sapl               qualquer Casa que use o SAPL/Interlegis (API REST aberta)
  votacaoeletronica  Câmaras no sistema <cidade>.votacaoeletronica.inf.br
Para adicionar outro sistema, crie obs/<nome>.py com as funções coletar, buscar, salvar e documentos
(veja CONTRIBUINDO.md) e registre-o em ADAPTADORES.
"""
from . import alrs, sapl, votacaoeletronica

ADAPTADORES = {"alrs": alrs, "sapl": sapl, "votacaoeletronica": votacaoeletronica}


def fontes(cfg):
    """Lista as fontes locais configuradas e ativas, com 'esfera' preenchida."""
    saida = []
    for esfera in ("estadual", "municipal"):
        f = cfg.get(esfera)
        if f and f.get("tipo") in ADAPTADORES and f.get("ativo", True):
            f.setdefault("esfera", esfera)
            saida.append(f)
    return saida


def por_id(cfg, fid):
    return next((f for f in fontes(cfg) if f["id"] == fid), None)


def por_esfera(cfg, esfera):
    return next((f for f in fontes(cfg) if f["esfera"] == esfera), None)


def modulo(fonte):
    return ADAPTADORES[fonte["tipo"]]


def nomes(cfg):
    """Rótulos usados no relatório."""
    loc = cfg.get("local") or {}
    est, mun = por_esfera(cfg, "estadual"), por_esfera(cfg, "municipal")
    uf = loc.get("uf") or ""
    municipio = loc.get("municipio") or ""
    partes = ["Brasil"] + ([uf] if uf else []) + ([municipio] if municipio else [])
    return {
        "titulo": " • ".join(partes),
        "uf": uf, "estado": loc.get("estado") or uf, "municipio": municipio,
        "casa_estadual": est["nome"] if est else "", "sigla_estadual": (est or {}).get("sigla") or (est or {}).get("nome", ""),
        "casa_municipal": mun["nome"] if mun else "",
        "url_estadual": (est or {}).get("url", ""), "url_municipal": (mun or {}).get("url", ""),
        "tem_estadual": bool(est), "tem_municipal": bool(mun),
        "obs_estadual": (est or {}).get("cobertura", ""), "obs_municipal": (mun or {}).get("cobertura", ""),
    }
