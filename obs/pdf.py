"""Exporta o relatório HTML para PDF usando o modo de impressão de um navegador já instalado.

Funciona com Microsoft Edge, Google Chrome ou Chromium (Windows, macOS e Linux), sem instalar nada.
Se nenhum for encontrado, o relatório HTML continua sendo gerado normalmente e um aviso é exibido.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CANDIDATOS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
NOMES = ["msedge", "microsoft-edge", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]

CSS_IMPRESSAO = """<style>
@page{size:A4;margin:14mm 12mm}
@media print{
 body{background:#fff!important;color:#111!important;font-size:12.5px}
 .wrap{max-width:none;padding:0}
 nav.toc,.chips,.chips+*,script,.sub:has(+ .chips){display:none!important}
 .card,.diff,.significa,.explica,.tile,tr{break-inside:avoid}
 h2{break-after:avoid}
 a{color:#0a4d8c!important;text-decoration:none}
 details>summary{display:none}
 ul.nomes{columns:4;font-size:9px;line-height:1.25}
 table.por-partido{font-size:10px}
}
</style>"""


def navegador():
    for c in CANDIDATOS:
        if c and Path(c).exists():
            return c
    for n in NOMES:
        achado = shutil.which(n)
        if achado:
            return achado
    return None


def _versao_impressao(html):
    """Abre as seções recolhidas, força o tema claro e acrescenta o CSS de impressão."""
    html = html.replace("<details>", "<details open>").replace("<details ", "<details open ")
    html = html.replace('<html lang="pt-BR">', '<html lang="pt-BR" data-theme="light">', 1)
    return html.replace("</head>", CSS_IMPRESSAO + "</head>", 1)


def exportar(arq_html, arq_pdf=None, log=print):
    """Gera o PDF ao lado do HTML. Devolve o caminho do PDF, ou None se não houver navegador compatível."""
    arq_html = Path(arq_html)
    arq_pdf = Path(arq_pdf) if arq_pdf else arq_html.with_suffix(".pdf")
    exe = navegador()
    if not exe:
        log("PDF: nenhum navegador compatível (Edge/Chrome/Chromium) encontrado; o relatório segue só em HTML.")
        return None
    with tempfile.TemporaryDirectory(prefix="observatorio-pdf-") as tmp:
        temp_html = Path(tmp) / "relatorio.html"
        temp_html.write_text(_versao_impressao(arq_html.read_text(encoding="utf-8")), encoding="utf-8")
        cmd = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
               "--disable-extensions", f"--user-data-dir={Path(tmp) / 'perfil'}",
               "--no-pdf-header-footer", f"--print-to-pdf={arq_pdf}", temp_html.as_uri()]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180, check=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            log(f"PDF: não foi possível gerar ({e}).")
            return None
    if arq_pdf.exists() and arq_pdf.stat().st_size > 1000:
        return arq_pdf
    log("PDF: o navegador não gerou o arquivo; o relatório segue só em HTML.")
    return None
