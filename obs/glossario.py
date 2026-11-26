"""Tradução, em linguagem simples, dos termos de tramitação usados pelas Casas legislativas.

Usado no relatório para explicar "o que mudou" em cada proposição sem depender de IA.
Cada regra: (expressão regular sobre o texto normalizado, explicação). A primeira que casar é usada,
então as mais específicas vêm antes das mais genéricas.
"""
import re

from .util import normalizar

REGRAS = [
    # --- fim de linha: virou lei, foi vetado, arquivado
    (r"transformad[ao] em (norma|lei)|norma juridica gerada|sancionad|promulgad",
     "Virou lei: o texto foi sancionado (ou promulgado) e passa a valer depois de publicado no Diário Oficial."),
    (r"vetad[ao] (total|integral)|veto total",
     "O Executivo vetou o projeto inteiro. O Legislativo ainda pode derrubar o veto numa votação própria."),
    (r"vetad[ao] parcial|veto parcial",
     "O Executivo sancionou o projeto, mas vetou alguns trechos. O Legislativo ainda pode derrubar esses vetos."),
    (r"vetad",
     "O Executivo vetou o projeto (no todo ou em parte). O Legislativo ainda pode derrubar o veto numa votação própria."),
    (r"veto",
     "Há um veto em análise: o Legislativo vai decidir se mantém ou derruba a decisão do Executivo."),
    (r"remetid[ao] a sancao|enviad[ao] a sancao|a sancao",
     "O projeto foi aprovado e enviado ao Executivo (Presidente, Governador ou Prefeito), que tem 15 dias úteis para sancionar ou vetar."),
    (r"sem eficacia|perdeu (a )?eficacia|eficacia encerrada",
     "A medida provisória perdeu a validade porque não foi votada no prazo de 120 dias."),
    (r"requerimento de retirada|req.{0,40}retirada de proposicao",
     "O autor pediu a retirada do projeto. Se o pedido for aceito pela Presidência, o projeto deixa de tramitar."),
    (r"desarquivad",
     "O projeto foi desarquivado e voltou a tramitar."),
    (r"arquivad",
     "O projeto foi arquivado: sai da pauta e para de tramitar (pode ser desarquivado em alguns casos, como no início de nova legislatura)."),
    (r"retirad[ao](?! de pauta| da pauta)",
     "O projeto foi retirado e deixa de tramitar (normalmente a pedido do autor)."),
    (r"prejudicad",
     "O projeto foi considerado prejudicado (perdeu o objeto, por exemplo porque outro texto igual já foi decidido) e não será votado."),

    # --- votação
    (r"tramitacao concluida|tramitacao encerrada",
     "A tramitação nesta Casa terminou; veja a situação final no link oficial."),
    (r"encerramento de legislatura|sem parecer",
     "O parecer não chegou a ser dado (por exemplo, porque a legislatura terminou)."),
    (r"rejeitad",
     "O projeto foi rejeitado na votação."),
    (r"aprovad[ao] .*redacao final|redacao final .*aprovad",
     "Foi aprovada a redação final: a versão definitiva do texto, já com as mudanças feitas na votação."),
    (r"aprovad[ao] o parecer|parecer .*aprovad",
     "A comissão aprovou o parecer do relator: é a opinião oficial da comissão sobre o projeto, que segue adiante."),
    (r"aprovad[ao] (o |a )?requerimento de urgencia|urgencia .*aprovad|regime de urgencia",
     "Foi aprovada a urgência: o projeto pula etapas e pode ser votado diretamente no Plenário, mais rápido."),
    (r"aprovad",
     "O projeto foi aprovado nesta etapa. Veja nos eventos se ainda falta outra Casa ou a sanção."),
    (r"regime de tramitacao",
     "Mudou a forma de tramitação do projeto (por exemplo, passou a ter urgência e a andar mais rápido)."),
    (r"votacao adiada|adiad[ao]|retirad[ao] de pauta|retirad[ao] da pauta",
     "A votação foi adiada ou o projeto saiu da pauta do dia; deve voltar numa próxima sessão."),
    (r"pedido de vista|vista (coletiva|concedida)",
     "Um ou mais parlamentares pediram vista: mais tempo para estudar o projeto antes da votação."),
    (r"aguardando deliberacao|incluid[ao] (em|na) (ordem do dia|pauta)|em pauta|pauta da sessao|pronta para pauta|apreciacao em plenario|encaminhad[ao] para votacao",
     "O projeto entrou (ou está pronto para entrar) na pauta de votação do Plenário."),
    (r"^pauta$|em pauta|na pauta|^ordem do dia",
     "O projeto está na pauta: deve ser discutido ou votado em breve."),
    (r"discussao (em )?(primeiro|segundo|unico) turno|em discussao",
     "O projeto está em discussão no Plenário, etapa que antecede a votação."),
    (r"leitura em plenario|lid[ao] em plenario|enviado para leitura",
     "O projeto foi lido em Plenário: é a apresentação formal aos parlamentares, que abre a tramitação."),

    # --- comissões e relatoria
    (r"parecer (do relator )?(pela |pela )?(aprovacao|favoravel)|parecer favoravel",
     "O relator deu parecer favorável: recomenda que o projeto seja aprovado (o parecer ainda precisa ser votado na comissão)."),
    (r"parecer (pela )?rejeicao|parecer contrario|desfavoravel",
     "O relator deu parecer contrário: recomenda que o projeto seja rejeitado."),
    (r"parecer distribuido|relator\(a\)",
     "O projeto foi entregue a um relator na comissão, que vai estudá-lo e dar o parecer."),
    (r"parecer da comissao",
     "A comissão emitiu seu parecer, a opinião oficial dela sobre o projeto (veja no link se foi favorável ou contrário)."),
    (r"apresentacao do parecer|parecer do relator|parecer apresentado|parecer juridico|para emissao de parecer|para parecer|aguardando parecer",
     "O projeto está na fase de parecer: um relator (ou a assessoria jurídica) analisa o texto e recomenda aprovar, mudar ou rejeitar."),
    (r"aguardando designacao (do |de )?relator|para designacao de relator",
     "O projeto está na comissão esperando que seja escolhido um relator, o parlamentar que vai estudá-lo."),
    (r"designad[ao] relator|designacao de relator|relator designado|distribuid[ao] ao relator",
     "Um parlamentar foi escolhido relator: é quem vai estudar o projeto e dar o parecer na comissão."),
    (r"prazo para (apresentacao de )?emendas|recebimento de emendas|abertura de prazo",
     "Está aberto o prazo de emendas: os parlamentares podem sugerir mudanças no texto antes da análise."),
    (r"emenda",
     "Foram apresentadas emendas: propostas de mudança no texto original."),
    (r"substitutivo",
     "Foi apresentado um substitutivo: uma nova versão do texto que substitui a original."),
    (r"audiencia publica",
     "Haverá (ou houve) audiência pública: reunião aberta para ouvir especialistas e a sociedade sobre o tema."),
    (r"(ag\.?|aguardando) analise de (in)?constitucionalidade",
     "A Presidência da Câmara está fazendo uma análise preliminar: verifica se o projeto pode seguir para as comissões ou se deve ser devolvido ao autor por ser claramente inconstitucional."),
    (r"aguardando (autorizacao do )?despacho",
     "O projeto chegou e aguarda o despacho da Mesa, que define por quais comissões ele vai passar."),
    (r"despach|^distribuicao$|distribuid[ao] (as|a) comiss|encaminhad[ao] (as|a) comiss|comissoes tematicas",
     "A Mesa definiu o caminho do projeto: quais comissões vão analisá-lo antes de ir (ou não) ao Plenário."),

    # --- movimentos entre Casas e órgãos
    (r"resposta ao pedido de informac",
     "Chegou a resposta do Executivo ao pedido de informação; o documento foi anexado ao processo."),
    (r"parecer igam|igam",
     "Foi anexado um parecer técnico do IGAM, consultoria que orienta Câmaras Municipais sobre a legalidade dos projetos."),
    (r"documento anexado|anexad[ao]",
     "Um novo documento foi juntado ao processo (veja no link oficial)."),
    (r"aguardando envio ao (senado|a camara)",
     "O projeto foi aprovado nesta Casa e está sendo preparado para seguir à outra (Câmara ou Senado)."),
    (r"apresentacao de requerimento|requerimento",
     "Foi apresentado um requerimento ligado ao projeto (por exemplo, pedido de urgência, de audiência ou de informações)."),
    (r"remetid[ao] (ao|a) (senado|camara)|enviad[ao] (ao|a) (senado|camara)|aguardando apreciacao pelo senado",
     "O projeto terminou a votação nesta Casa e foi enviado à outra (Câmara ou Senado), onde recomeça a análise."),
    (r"apensad|tramitando em conjunto|tramitacao conjunta",
     "O projeto foi juntado a outro sobre o mesmo tema (apensado): os dois passam a tramitar e ser votados juntos."),
    (r"procuradoria|assessoria juridica",
     "O projeto foi enviado à Procuradoria/Assessoria Jurídica, que analisa se ele é legal e constitucional."),
    (r"decisao da presidencia",
     "A Presidência da Casa tomou uma decisão sobre o andamento do projeto (detalhes no link oficial)."),
    (r"aguardando encaminhamento|encaminhad[ao] a publicacao|publicacao inicial",
     "O projeto foi registrado e publicado oficialmente; aguarda ser encaminhado às comissões."),
    (r"encaminhad[ao] para o destinatario|via oficio",
     "Foi enviado um ofício sobre o projeto (comunicação oficial entre os Poderes ou órgãos)."),
    (r"recebid[ao]|protocolad|autuad|cadastrad[ao] no sistema|apresentacao (de|da) proposicao|apresentad[ao]",
     "O projeto foi protocolado e começou a tramitar."),
]

_COMPILADAS = [(re.compile(rx), txt) for rx, txt in REGRAS]


def explicar(texto):
    """Explicação simples para um texto de situação/tramitação; '' se nenhum termo for reconhecido."""
    t = normalizar(texto or "")
    for rx, txt in _COMPILADAS:
        if rx.search(t):
            return txt
    return ""


def explicar_varios(textos, limite=3):
    """Explicações distintas (na ordem) para uma lista de textos, sem repetir."""
    vistas = []
    for t in textos:
        x = explicar(t)
        if x and x not in vistas:
            vistas.append(x)
        if len(vistas) >= limite:
            break
    return vistas
