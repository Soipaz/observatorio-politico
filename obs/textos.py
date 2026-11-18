"""Anexos e explicações em linguagem acessível.

1. Baixa os documentos oficiais (texto do projeto, justificativa, ofício) de cada item do relatório.
2. Extrai o texto dos PDFs para dados/textos/<id>.txt (PDFs digitalizados ficam marcados para leitura visual).
3. Lista em dados/pendentes_explicacao.json os itens que ainda não têm explicação escrita.
4. As explicações ficam em explicacoes/<id>.md e são lidas pelo relatório e pelo Obsidian.
"""
import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime

from .util import RAIZ, UA, baixar, carregar_config, url_permitida

PASTA_TXT = RAIZ / "dados" / "textos"
PASTA_EXP = RAIZ / "explicacoes"
PENDENTES = RAIZ / "dados" / "pendentes_explicacao.json"
MAX_BYTES = 25 * 1024 * 1024     # não baixa anexos maiores que 25 MB
MAX_PAGINAS = 60                 # LOAs têm centenas de páginas; o texto da lei e a mensagem vêm no início
MAX_CHARS = 80_000
MIN_CHARS_TEXTO = 300            # abaixo disso o PDF é provavelmente digitalizado (imagem)


def nome_arquivo(uid):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", uid)


def arquivo_explicacao(uid):
    return PASTA_EXP / f"{nome_arquivo(uid)}.md"


def ler_explicacao(uid):
    """Retorna o corpo (markdown) da explicação, sem o cabeçalho, ou ''."""
    arq = arquivo_explicacao(uid)
    if not arq.exists():
        return ""
    t = arq.read_text(encoding="utf-8")
    corpo = re.sub(r"^---\n.*?\n---\n", "", t, count=1, flags=re.S).strip()
    base = _meta_explicacao(uid).get("base")
    return corpo + (f"\n\n*Documentos lidos: {base}.*" if base else "")


def _meta_explicacao(uid):
    arq = arquivo_explicacao(uid)
    if not arq.exists():
        return {}
    m = re.match(r"^---\n(.*?)\n---\n", arq.read_text(encoding="utf-8"), re.S)
    return dict(re.findall(r"^(\w+):\s*(.*)$", m[1], re.M)) if m else {}


# ---------------------------------------------------------------- download

def _baixar_bytes(url, tentativas=3):
    if not url_permitida(url):
        raise ValueError("endereço recusado (só http/https)")
    erro = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/pdf,*/*"})
            with urllib.request.urlopen(req, timeout=120) as r:
                tam = int(r.headers.get("Content-Length") or 0)
                if tam > MAX_BYTES:
                    raise ValueError(f"arquivo grande demais ({tam // 1048576} MB)")
                dados = r.read(MAX_BYTES + 1)
                if len(dados) > MAX_BYTES:
                    raise ValueError("arquivo grande demais (> 25 MB)")
                return dados, r.headers.get("Content-Type", "")
        except ValueError:
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            erro = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"falha ao baixar {url}: {erro}")


def _extrair_pdf(dados):
    import logging
    from pypdf import PdfReader
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    leitor = PdfReader(io.BytesIO(dados))
    total = len(leitor.pages)
    partes = []
    for i, pg in enumerate(leitor.pages[:MAX_PAGINAS]):
        try:
            partes.append(f"\n[página {i + 1}]\n" + (pg.extract_text() or ""))
        except Exception:  # página corrompida não derruba o resto
            partes.append(f"\n[página {i + 1}: não foi possível extrair]\n")
    texto = re.sub(r"[ \t]+", " ", "".join(partes))
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto[:MAX_CHARS], total


def _documentos(p, cfg):
    """Lista [(rótulo, url)] dos documentos oficiais a ler para a proposição."""
    if p["fonte"] in ("camara", "senado"):
        return [("Texto oficial (inteiro teor)", p["url_texto"])] if p.get("url_texto") else []
    from . import locais
    fonte = locais.por_id(cfg, p["fonte"])
    return locais.modulo(fonte).documentos(fonte, p) if fonte else []


def preparar(banco, uids, log=print, cfg=None):
    """Baixa e extrai os anexos dos itens indicados; grava a lista de pendentes de explicação."""
    PASTA_TXT.mkdir(parents=True, exist_ok=True)
    PASTA_EXP.mkdir(parents=True, exist_ok=True)
    pendentes, baixados, falhas = [], 0, 0
    for uid in uids:
        p = banco.obter(uid)
        if not p:
            continue
        p = dict(p)
        base = PASTA_TXT / nome_arquivo(uid)
        meta_arq = base.with_suffix(".json")
        meta = json.loads(meta_arq.read_text(encoding="utf-8")) if meta_arq.exists() else None
        # reaproveita o que já foi baixado; rebaixa só se o link do texto mudou (nova versão)
        if not meta or meta.get("url_texto") != (p.get("url_texto") or ""):
            try:
                docs = _documentos(p, cfg or carregar_config())
            except Exception as e:
                log(f"  aviso: {p['identificacao']} ({p['fonte']}): não consegui listar documentos: {e}")
                docs = []
            textos, lidos, digitalizados = [], [], []
            for i, (rot, url) in enumerate(docs):
                try:
                    dados, tipo = _baixar_bytes(url)
                    if dados[:4] == b"%PDF":
                        txt, pags = _extrair_pdf(dados)
                        pdf = base.parent / f"{base.name}_{i + 1}.pdf"
                        pdf.write_bytes(dados)
                        if len(re.sub(r"\[página \d+[^\]]*\]|\s", "", txt)) < MIN_CHARS_TEXTO:
                            digitalizados.append({"rotulo": rot, "pdf": str(pdf), "paginas": pags})
                        lidos.append({"rotulo": rot, "paginas": pags, "pdf": str(pdf)})
                    else:
                        raise ValueError("o endereço não devolveu um PDF")
                    textos.append(f"===== {rot} =====\n{txt.strip()}")
                    baixados += 1
                except Exception as e:
                    falhas += 1
                    log(f"  aviso: {p['identificacao']} — {rot}: {e}")
            texto = "\n\n".join(textos)
            base.with_suffix(".txt").write_text(texto, encoding="utf-8")
            meta = {"uid": uid, "url_texto": p.get("url_texto") or "", "documentos": lidos,
                    "digitalizados": digitalizados, "caracteres": len(texto),
                    "sha": hashlib.sha1(texto.encode()).hexdigest()[:12],
                    "baixado_em": datetime.now().isoformat(timespec="seconds")}
            meta_arq.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

        exp = _meta_explicacao(uid)
        if not exp or exp.get("texto_sha") != meta["sha"]:
            pendentes.append({
                "uid": uid, "identificacao": p["identificacao"], "casa": p["casa"], "fonte": p["fonte"],
                "ementa": p["ementa"], "autor": p.get("autor"), "situacao": p.get("situacao"),
                "texto": str(base.with_suffix(".txt")), "caracteres": meta["caracteres"],
                "documentos": [d["rotulo"] for d in meta["documentos"]],
                "digitalizados": meta["digitalizados"], "texto_sha": meta["sha"],
                "explicacao": str(arquivo_explicacao(uid)),
                "motivo": "texto novo ou atualizado" if exp else "sem explicação",
            })
    PENDENTES.write_text(json.dumps(pendentes, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Anexos: {baixados} documentos baixados agora, {falhas} falhas; {len(pendentes)} itens aguardando explicação")
    return pendentes


def salvar_explicacao(uid, corpo, texto_sha, base_lida):
    """Usado ao escrever explicações: grava com cabeçalho de controle."""
    PASTA_EXP.mkdir(parents=True, exist_ok=True)
    cab = f"---\nuid: {uid}\ntexto_sha: {texto_sha}\nbase: {base_lida}\nescrito_em: {datetime.now().date().isoformat()}\n---\n"
    arquivo_explicacao(uid).write_text(cab + corpo.strip() + "\n", encoding="utf-8")


# ---------------------------------------------------------------- dossiê compacto (base para escrever as explicações)

def _limpo(t):
    t = re.sub(r"\[página \d+[^\]]*\]", " ", t)
    t = re.sub(r"(?i)assinado eletronicamente.*?(?=\n)|para verificar.*?(?=\n)|\*CD\d+\*|Apresentação:.*?(?=\n)", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def dossie(item, n_art=1800, n_just=1300):
    """Trecho compacto do documento: início dos artigos + início da justificativa/exposição de motivos."""
    try:
        t = _limpo(open(item["texto"], encoding="utf-8").read())
    except OSError:
        t = ""
    if not t:
        return "(sem texto extraído)"
    m = re.search(r"Art\.?\s*1\s*[º°o]?", t)
    ini = max(0, (m.start() if m else 0) - 150)
    art = t[ini: ini + n_art]
    j = re.search(r"JUSTIFICA[ÇC][ÃA]O|Justificativa|JUSTIFICATIVA|EXPOSI[ÇC][ÃA]O DE MOTIVOS|Exposição de Motivos|MENSAGEM N", t[ini + 200:])
    just = t[ini + 200 + j.start(): ini + 200 + j.start() + n_just] if j else ""
    return art + (" […] ‖ " + just if just else "")


def importar_lote(arquivo, log=print):
    """Grava explicações escritas num arquivo de lote.

    Formato: cada item começa com uma linha '=== <uid>' seguida de 'base: <documentos lidos>'
    e do corpo em markdown. O vínculo com a versão do texto (texto_sha) vem de dados/pendentes_explicacao.json.
    """
    pend = {x["uid"]: x for x in json.loads(PENDENTES.read_text(encoding="utf-8"))} if PENDENTES.exists() else {}
    t = open(arquivo, encoding="utf-8").read()
    n = 0
    for bloco in re.split(r"^=== ", t, flags=re.M)[1:]:
        uid, _, resto = bloco.partition("\n")
        uid = uid.strip()
        m = re.match(r"base:\s*(.*)\n", resto)
        base_lida = m[1].strip() if m else ""
        corpo = resto[m.end():] if m else resto
        meta_arq = (PASTA_TXT / nome_arquivo(uid)).with_suffix(".json")
        sha = pend.get(uid, {}).get("texto_sha") or (json.loads(meta_arq.read_text(encoding="utf-8"))["sha"] if meta_arq.exists() else "")
        salvar_explicacao(uid, corpo, sha, base_lida)
        n += 1
    log(f"{n} explicações gravadas em {PASTA_EXP}")
    return n
