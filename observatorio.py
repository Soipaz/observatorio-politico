"""
OBSERVATÓRIO POLÍTICO — acompanhamento legislativo a partir de fontes oficiais
Federal (Câmara e Senado) + Assembleia Legislativa do seu estado + Câmara do seu município.

Uso:
  python observatorio.py configurar            # assistente: escolha estado e município
  python observatorio.py ciclo                 # coleta + anexos + relatório (+ IA, se configurada)
  python observatorio.py ciclo --dias 14       # força janela de 14 dias (máx. 30)
  python observatorio.py explicar              # IA: escreve as explicações "Do que se trata" que faltam
  python observatorio.py analisar              # IA: escreve a análise do ciclo
  python observatorio.py relatorio             # regera o relatório do último ciclo
  python observatorio.py anexos                # baixa/lê os anexos e lista o que falta explicar
  python observatorio.py explicacoes LOTE.md   # importa explicações escritas à mão (ou pelo Claude Code)
  python observatorio.py status                # resumo do banco
"""
import argparse
import re
import sys
import traceback
from datetime import date, timedelta

from obs import camara, locais, senado
from obs.db import Banco
from obs.util import RAIZ, Classificador, carregar_config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def log(msg):
    print(msg, flush=True)


def ler_acompanhar(cfg):
    """Linhas 'fonte SIGLA N/ANO'. fonte: camara, senado, estado, municipio (ou o id da fonte local)."""
    linhas = []
    arq = RAIZ / "acompanhar.txt"
    if not arq.exists():
        return linhas
    apelidos = {"estado": "estadual", "estadual": "estadual", "municipio": "municipal", "município": "municipal", "municipal": "municipal"}
    for l in arq.read_text(encoding="utf-8").splitlines():
        l = l.split("#", 1)[0].strip()
        m = re.match(r"(\S+)\s+([A-Za-z]+)\s+(\d+)/(\d{4})", l)
        if not m:
            continue
        fonte = m[1].lower()
        if fonte in apelidos:
            f = locais.por_esfera(cfg, apelidos[fonte])
            if not f:
                log(f"  aviso: '{l}' — nenhuma fonte {apelidos[fonte]} configurada (rode: python observatorio.py configurar)")
                continue
            fonte = f["id"]
        linhas.append((fonte, m[2].upper(), m[3], int(m[4])))
    return linhas


def sincronizar_acompanhar(banco, clf, cfg):
    """Garante que cada item da lista esteja no banco e marcado; desmarca os removidos."""
    desejados = set()
    for fonte, sigla, numero, ano in ler_acompanhar(cfg):
        ident_num = numero.lstrip("0") or "0"
        row = banco.con.execute(
            "SELECT uid FROM proposicoes WHERE fonte=? AND sigla=? AND ano=? AND CAST(numero AS INTEGER)=?",
            (fonte, sigla, ano, int(ident_num))).fetchone()
        uid = row[0] if row else None
        if not uid:
            local = locais.por_id(cfg, fonte)
            if fonte not in ("camara", "senado") and not local:
                log(f"  aviso: fonte '{fonte}' desconhecida em acompanhar.txt (use camara, senado, estado ou municipio)")
                continue
            try:
                if fonte == "camara":
                    d = camara.buscar_por_identificacao(sigla, ident_num, ano)
                elif fonte == "senado":
                    d = senado.buscar_por_identificacao(sigla, ident_num, ano)
                    if d:
                        d = {k: v for k, v in d.items() if k not in ("classificacoes", "deliberacao", "norma", "despachos")}
                else:
                    d = locais.modulo(local).buscar(local, cfg, sigla, numero, ano)
            except RuntimeError as e:
                log(f"  aviso: não consegui consultar {fonte} {sigla} {numero}/{ano}: {e}")
                continue
            if not d:
                log(f"  aviso: {fonte} {sigla} {numero}/{ano} NÃO encontrada na fonte oficial — confira a identificação")
                continue
            if local:
                locais.modulo(local).salvar(banco, d, clf, local)
            else:
                d["eixos"] = clf.classificar(d["ementa"]) or ["outros"]
                banco.salvar(d)
            uid = d["uid"]
        desejados.add(uid)
        banco.marcar_acompanhar(uid, 1)
    for r in banco.acompanhadas():
        if r["uid"] not in desejados:
            banco.marcar_acompanhar(r["uid"], 0)
    banco.commit()
    log(f"Lista de acompanhamento: {len(desejados)} proposições")


def _cfg():
    if not (RAIZ / "config.json").exists():
        log("Ainda não há config.json. Rode primeiro:  python observatorio.py configurar")
        sys.exit(1)
    return carregar_config()


def ciclo(dias=None, sem_ia=False):
    cfg = _cfg()
    clf = Classificador(cfg)
    banco = Banco()
    fim = date.today()
    ultimo = banco.ultimo_ciclo()
    if dias:
        inicio = fim - timedelta(days=dias - 1)
    elif ultimo:
        inicio = date.fromisoformat(ultimo["fim"])  # sobrepõe 1 dia por segurança
    else:
        inicio = fim - timedelta(days=cfg.get("janela_padrao_dias", 7) - 1)
    inicio, fim = inicio.isoformat(), fim.isoformat()
    banco.iniciar_ciclo(inicio, fim)
    log(f"== Ciclo {banco.ciclo}: {inicio} a {fim} ==")

    sincronizar_acompanhar(banco, clf, cfg)
    resumo = {}
    for nome, mod in (("camara", camara), ("senado", senado)):
        try:
            resumo[nome] = mod.coletar(banco, clf, cfg, inicio, fim, log)
        except Exception as e:  # uma fonte fora do ar não derruba o ciclo
            log(f"ERRO na fonte {nome}: {e}")
            traceback.print_exc()
            resumo[nome] = {"erro": str(e)}
    for f in locais.fontes(cfg):
        try:
            resumo[f["id"]] = locais.modulo(f).coletar(banco, clf, cfg, f, inicio, fim, log)
        except Exception as e:
            log(f"ERRO na fonte {f['nome']}: {e}")
            traceback.print_exc()
            resumo[f["id"]] = {"erro": str(e)}
    banco.fechar_ciclo(resumo)
    log("Coleta concluída.")
    anexos(banco)
    if not sem_ia and (cfg.get("ia") or {}).get("ativo"):
        from obs import ia
        if ia.disponivel(log):
            ia.explicar_pendentes(cfg, log)
            gerar(banco, silencioso=True)  # JSON atualizado com as explicações, base da análise
            ia.analisar(cfg, log)
    gerar(banco)


def anexos(banco=None):
    """Baixa e lê os documentos oficiais dos itens do último ciclo; lista os que aguardam explicação."""
    from obs import relatorio, textos
    cfg = _cfg()
    banco = banco or Banco()
    ultimo = banco.ultimo_ciclo()
    if not ultimo:
        log("Nenhum ciclo executado ainda.")
        return
    d = relatorio.montar(banco, ultimo, cfg)
    uids = relatorio.uids_do_ciclo(d)
    log(f"Anexos: conferindo documentos de {len(uids)} itens do ciclo")
    textos.preparar(banco, uids, log, cfg)


def gerar(banco=None, silencioso=False):
    from obs import relatorio
    banco = banco or Banco()
    ultimo = banco.ultimo_ciclo()
    if not ultimo:
        log("Nenhum ciclo executado ainda. Rode: python observatorio.py ciclo")
        return
    caminhos = relatorio.gerar(banco, ultimo, _cfg())
    if not silencioso:
        for c in caminhos:
            log(f"Gerado: {c}")


def explicar():
    from obs import ia
    if ia.disponivel(log):
        ia.explicar_pendentes(_cfg(), log)
        gerar()


def analisar():
    from obs import ia
    if ia.disponivel(log):
        gerar(silencioso=True)
        ia.analisar(_cfg(), log)
        gerar()


def status():
    banco = Banco()
    c = banco.con
    log(f"Proposições no banco: {c.execute('SELECT COUNT(*) FROM proposicoes').fetchone()[0]}")
    for r in c.execute("SELECT fonte, COUNT(*), SUM(acompanhar) FROM proposicoes GROUP BY fonte"):
        log(f"  {r[0]}: {r[1]} (acompanhadas: {r[2]})")
    log(f"Eventos: {c.execute('SELECT COUNT(*) FROM eventos').fetchone()[0]}")
    for r in c.execute("SELECT id, executado_em, inicio, fim FROM ciclos ORDER BY id DESC LIMIT 5"):
        log(f"  ciclo {r[0]} em {r[1]} ({r[2]} a {r[3]})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Observatório Político")
    ap.add_argument("comando", choices=["configurar", "ciclo", "explicar", "analisar", "anexos", "explicacoes", "relatorio", "status"])
    ap.add_argument("arquivo", nargs="?", help="(explicacoes) arquivo de lote com as explicações escritas")
    ap.add_argument("--dias", type=int, help="tamanho da janela em dias (máx. 30 para o Senado)")
    ap.add_argument("--sem-ia", action="store_true", help="não chama a API da Anthropic neste ciclo")
    a = ap.parse_args()
    if a.comando == "configurar":
        from obs import configurar
        configurar.assistente()
    elif a.comando == "explicacoes":
        from obs import textos
        textos.importar_lote(a.arquivo, log)
    else:
        {"ciclo": lambda: ciclo(a.dias, a.sem_ia), "explicar": explicar, "analisar": analisar,
         "anexos": anexos, "relatorio": gerar, "status": status}[a.comando]()
