"""Utilidades: configuração, HTTP com repetição, normalização de texto e classificação temática."""
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
UA = "ObservatorioPolitico/1.0 (uso pessoal; dados abertos)"
MAX_RESPOSTA = 50 * 1024 * 1024  # proteção contra respostas gigantes de servidores mal configurados


def url_permitida(url):
    """Só aceita endereços http(s). Impede que uma fonte externa aponte para arquivos locais (file://) etc."""
    return isinstance(url, str) and url.lower().startswith(("https://", "http://"))


def carregar_config():
    with open(RAIZ / "config.json", encoding="utf-8") as f:
        return json.load(f)


def baixar(url, json_=True, tentativas=3, timeout=60):
    """GET com repetição. Retorna JSON (dict/list) ou texto."""
    if not url_permitida(url):
        raise RuntimeError(f"Endereço recusado (só http/https): {url[:80]}")
    erro = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json" if json_ else "text/html", "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                dados = r.read(MAX_RESPOSTA + 1)
            if len(dados) > MAX_RESPOSTA:
                raise RuntimeError(f"Resposta grande demais de {url[:80]}")
            texto = dados.decode("utf-8", errors="replace")
            return json.loads(texto) if json_ else texto
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError) as e:
            erro = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"Falha ao acessar {url}: {erro}")


def normalizar(texto):
    t = (texto or "").replace("º", "").replace("°", "").replace("ª", "")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t)


class Classificador:
    def __init__(self, config):
        self.eixos = config["eixos"]
        self.excluir = [normalizar(x) for x in config["excluir_honorificos"]]
        self.padroes = {}
        for chave, eixo in self.eixos.items():
            partes = []
            for termo in eixo["termos"]:
                n = re.escape(normalizar(termo))
                # termos curtos (siglas) precisam ser palavra inteira
                partes.append(rf"\b{n}\b" if len(termo) <= 4 else rf"\b{n}")
            self.padroes[chave] = re.compile("|".join(partes))
        self.tema_para_eixo = {}
        for chave, eixo in self.eixos.items():
            for cod in eixo.get("temas_camara", []):
                self.tema_para_eixo.setdefault(cod, []).append(chave)

    def honorifico(self, ementa):
        n = normalizar(ementa)
        return any(x in n for x in self.excluir)

    def classificar(self, ementa, temas_camara=()):
        """Retorna lista ordenada de eixos. Lista vazia = fora do escopo."""
        if self.honorifico(ementa):
            return []
        n = normalizar(ementa)
        achados = {k for k, p in self.padroes.items() if p.search(n)}
        for cod in temas_camara:
            achados.update(self.tema_para_eixo.get(cod, []))
        return [k for k in self.eixos if k in achados]
