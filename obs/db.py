"""Banco SQLite com histórico permanente de proposições, eventos e ciclos."""
import json
import sqlite3
from datetime import datetime

from .util import RAIZ

ARQUIVO = RAIZ / "dados" / "observatorio.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS proposicoes (
    uid TEXT PRIMARY KEY,           -- ex.: camara:2654838, senado:9127383, encantado:4538
    fonte TEXT, esfera TEXT, casa TEXT,
    sigla TEXT, numero TEXT, ano INTEGER, identificacao TEXT,
    apelido TEXT, ementa TEXT, autor TEXT,
    data_apresentacao TEXT, situacao TEXT, data_situacao TEXT, orgao TEXT,
    url TEXT, url_texto TEXT, eixos TEXT,
    acompanhar INTEGER DEFAULT 0,
    primeira_coleta TEXT, ultima_coleta TEXT
);
CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT, data TEXT, tipo TEXT, descricao TEXT, orgao TEXT, url TEXT,
    ciclo INTEGER,
    UNIQUE(uid, data, tipo, descricao)
);
CREATE TABLE IF NOT EXISTS votacoes (
    id TEXT PRIMARY KEY, fonte TEXT, data TEXT, orgao TEXT,
    descricao TEXT, resultado TEXT, uid TEXT, identificacao TEXT, url TEXT, eixos TEXT, ciclo INTEGER
);
CREATE TABLE IF NOT EXISTS ciclos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    executado_em TEXT, inicio TEXT, fim TEXT, resumo TEXT
);
CREATE INDEX IF NOT EXISTS ix_eventos_ciclo ON eventos(ciclo);
CREATE INDEX IF NOT EXISTS ix_prop_ident ON proposicoes(fonte, identificacao);
"""

CAMPOS = ["fonte", "esfera", "casa", "sigla", "numero", "ano", "identificacao", "apelido", "ementa", "autor",
          "data_apresentacao", "situacao", "data_situacao", "orgao", "url", "url_texto", "eixos"]


class Banco:
    def __init__(self, caminho=ARQUIVO):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(caminho)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)
        self.ciclo = None

    def iniciar_ciclo(self, inicio, fim):
        cur = self.con.execute("INSERT INTO ciclos(executado_em, inicio, fim) VALUES (?,?,?)",
                               (datetime.now().isoformat(timespec="seconds"), inicio, fim))
        self.ciclo = cur.lastrowid
        return self.ciclo

    def fechar_ciclo(self, resumo):
        self.con.execute("UPDATE ciclos SET resumo=? WHERE id=?", (json.dumps(resumo, ensure_ascii=False), self.ciclo))
        self.con.commit()

    def ultimo_ciclo(self):
        return self.con.execute("SELECT * FROM ciclos WHERE resumo IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()

    def obter(self, uid):
        return self.con.execute("SELECT * FROM proposicoes WHERE uid=?", (uid,)).fetchone()

    def existe(self, uid):
        return self.obter(uid) is not None

    def salvar(self, p, nova_tag="apresentacao"):
        """Insere/atualiza proposição. Registra evento quando a situação muda. Retorna 'nova', 'mudou' ou None."""
        agora = datetime.now().isoformat(timespec="seconds")
        if isinstance(p.get("eixos"), list):
            p["eixos"] = ",".join(p["eixos"])
        antigo = self.obter(p["uid"])
        if antigo is None:
            cols = ["uid"] + CAMPOS + ["primeira_coleta", "ultima_coleta"]
            vals = [p["uid"]] + [p.get(c) for c in CAMPOS] + [agora, agora]
            self.con.execute(f"INSERT INTO proposicoes({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
            self.evento(p["uid"], p.get("data_apresentacao"), nova_tag, "Proposição registrada no observatório: " + (p.get("situacao") or "apresentada"), p.get("orgao"))
            return "nova"
        mudou = (p.get("situacao") or "") != (antigo["situacao"] or "") or (p.get("data_situacao") or "") != (antigo["data_situacao"] or "")
        sets = {c: p[c] for c in CAMPOS if p.get(c) not in (None, "")}
        # nunca apaga eixos já atribuídos
        if antigo["eixos"] and "eixos" in sets:
            juntos = list(dict.fromkeys(antigo["eixos"].split(",") + [e for e in sets["eixos"].split(",") if e]))
            if len(juntos) > 1 and "outros" in juntos:
                juntos.remove("outros")
            sets["eixos"] = ",".join(juntos)
        sets["ultima_coleta"] = agora
        self.con.execute(f"UPDATE proposicoes SET {','.join(k + '=?' for k in sets)} WHERE uid=?", list(sets.values()) + [p["uid"]])
        if mudou and p.get("situacao"):
            self.evento(p["uid"], p.get("data_situacao"), "situacao", p["situacao"], p.get("orgao"))
            return "mudou"
        return None

    def evento(self, uid, data, tipo, descricao, orgao=None, url=None):
        cur = self.con.execute(
            "INSERT OR IGNORE INTO eventos(uid, data, tipo, descricao, orgao, url, ciclo) VALUES (?,?,?,?,?,?,?)",
            (uid, (data or "")[:16], tipo, (descricao or "").strip(), orgao, url, self.ciclo))
        return cur.rowcount > 0

    def votacao(self, v):
        self.con.execute(
            "INSERT OR IGNORE INTO votacoes(id, fonte, data, orgao, descricao, resultado, uid, identificacao, url, eixos, ciclo) "
            "VALUES (:id,:fonte,:data,:orgao,:descricao,:resultado,:uid,:identificacao,:url,:eixos,:ciclo)",
            {**v, "ciclo": self.ciclo})

    def marcar_acompanhar(self, uid, valor=1):
        self.con.execute("UPDATE proposicoes SET acompanhar=? WHERE uid=?", (valor, uid))

    def acompanhadas(self, fonte=None):
        q = "SELECT * FROM proposicoes WHERE acompanhar=1"
        if fonte:
            return self.con.execute(q + " AND fonte=?", (fonte,)).fetchall()
        return self.con.execute(q).fetchall()

    def uids(self, fonte):
        return {r[0] for r in self.con.execute("SELECT uid FROM proposicoes WHERE fonte=?", (fonte,))}

    def commit(self):
        self.con.commit()
