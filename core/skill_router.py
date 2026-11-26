"""
Roteador Semântico de Skills baseado em ChromaDB para F.R.Y.I.Vs.
Implementa os padrões da skill vector-database-engineer:
- Indexação semântica com espaço vetorial HNSW cosseno.
- Recuperação top-K com threshold de similaridade para acelerar inferência do Ollama.
- Eliminação de sobrecarga de tokens e prevenção de alucinações de ferramentas.
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any, Final
from core.vector_db import get_or_create_collection
from skills import ALL_SKILL_SCHEMAS


def _sem_acentos(texto: str) -> str:
    """Remove acentuação preservando caracteres ASCII minúsculos."""
    return unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode("ascii")

SKILL_SEMANTIC_PROFILES: Final[dict[str, dict[str, str]]] = {
    "abrir_programa": {
        "description": "Abre um programa, software, aplicativo ou utilitário no computador pelo nome ou apelido.",
        "intents": (
            "abrir programa iniciar aplicativo software executar app lançar software "
            "abrir bloco de notas abrir calculadora abrir google chrome abrir navegador "
            "abrir visual studio code abrir vscode abrir cmd abrir terminal abrir explorador de arquivos "
            "abrir spotify discord steam gerenciador de tarefas start application open app launch program"
        )
    },
    "listar_janelas": {
        "description": "Lista todas as janelas e programas abertos e visíveis no sistema operacional.",
        "intents": (
            "listar janelas abertas quais janelas estão abertas mostrar programas em execução "
            "ver janelas ativas verificar telas abertas lista de aplicativos abertos list open windows"
        )
    },
    "focar_janela": {
        "description": "Foca e traz para primeiro plano uma janela aberta pelo título ou nome.",
        "intents": (
            "focar janela trazer para frente alternar para janela colocar em foco ativar tela "
            "mudar para janela do bloco de notas focar no navegador alternar aplicativo focus window bring to front"
        )
    },
    "minimizar_janela": {
        "description": "Minimiza uma janela ativa pelo título.",
        "intents": (
            "minimizar janela diminuir janela esconder tela ocultar janela abaixar janela "
            "minimizar aplicativo minimize window hide window"
        )
    },
    "maximizar_janela": {
        "description": "Maximiza uma janela pelo título para ocupar a tela inteira.",
        "intents": (
            "maximizar janela tela cheia aumentar janela expandir tela maximizar tela maximize window fullscreen"
        )
    },
    "fechar_janela": {
        "description": "Fecha uma janela aberta pelo título.",
        "intents": (
            "fechar janela encerrar programa sair do aplicativo fechar tela kill process fechar aba close window exit app"
        )
    },
    "digitar_texto": {
        "description": "Digita um texto automaticamente no aplicativo que estiver com o cursor ativo.",
        "intents": (
            "digitar texto escrever mensagem preencher campo teclado escrever na tela automatizar digitação type text write"
        )
    },
    "pressionar_atalho": {
        "description": "Executa uma combinação de teclas de atalho no teclado.",
        "intents": (
            "pressionar atalho teclas de atalho combinação de teclas ctrl c ctrl v alt tab win d enter hotkey shortcut press keys"
        )
    },
    "controlar_volume": {
        "description": "Ajusta ou muta o som e volume do computador.",
        "intents": (
            "controlar volume áudio som aumentar volume diminuir som mutar desmutar mudo "
            "volume mais alto mais baixo abaixar o volume silenciar sound volume up down mute"
        )
    },
    "tirar_screenshot": {
        "description": "Tira uma captura da tela inteira (print) e salva em arquivo de imagem.",
        "intents": (
            "tirar screenshot capturar tela tirar print printscreen foto da tela registrar imagem do monitor capture screen take screenshot"
        )
    },
    "obter_hora_data": {
        "description": "Informa a hora exata, minutos, dia da semana e data atual do sistema.",
        "intents": (
            "que horas são que horas sao que dia e hoje que dia é hoje data atual horario que horas horario agora dia da semana calendario"
        )
    },
    "pesquisar_informacao_web": {
        "description": "Pesquisa informações, notícias, fatos ou dúvidas na internet em segundo plano e retorna a resposta diretamente no chat sem abrir navegador.",
        "intents": (
            "pesquise sobre pesquisar sobre pesquise na internet busque informacao "
            "o que e quem e quem foi qual a cotacao qual o valor ultimas noticias "
            "noticias de hoje como funciona resumo sobre fatos sobre search web info"
        )
    },
    "pesquisar_google": {
        "description": "Abre o navegador Google Chrome ou Edge em segundo plano com a pesquisa realizada. Use APENAS quando o usuário pedir para abrir o navegador ou pesquisar no Chrome/Edge.",
        "intents": (
            "abra o chrome e pesquise pesquisar no chrome abrir chrome pesquisa "
            "abra o edge e pesquise pesquisar no edge abrir navegador e pesquisar "
            "pesquise no navegador abra o google no navegador open chrome search"
        )
    },
    "pesquisar_youtube": {
        "description": "Pesquisa ou toca músicas e vídeos no YouTube pelo navegador.",
        "intents": (
            "pesquisar no youtube pesquisa no youtube tocar musica no youtube toca uma musica ouvir musica no youtube abrir video youtube play music"
        )
    },
    "status_sistema": {
        "description": "Mostra o consumo atual de processador CPU, memória RAM e bateria do computador.",
        "intents": (
            "status do sistema uso de cpu uso de memoria consumo de ram bateria saude do computador desempenho do sistema system metrics"
        )
    },
    "bloquear_tela": {
        "description": "Bloqueia a tela do computador imediatamente para segurança.",
        "intents": (
            "bloquear tela bloquear pc travar tela trancar computador lock screen bloquear computador"
        )
    },
    "navegar_para": {
        "description": "Acessa um site ou endereço web diretamente no navegador (ex: 'youtube.com', 'google.com', 'globo.com').",
        "intents": (
            "navegar para acesse o site entrar no site abra o site entrar na pagina "
            "ir para o site abrir pagina web carregar site open website visit url"
        )
    },
    "pesquisar_na_web": {
        "description": "Pesquisa qualquer termo no Google, YouTube, DuckDuckGo ou Bing e exibe os resultados no navegador.",
        "intents": (
            "pesquisar na web busque na internet procurar na web pesquisar online "
            "buscar informacoes na internet pesquisar no google ou youtube search online web search"
        )
    },
    "clicar_elemento_web": {
        "description": "Abre um link ou resultado da página web aberta ('primeiro link', 'segundo resultado', 'primeiro vídeo') ou clica em qualquer botão, menu ou elemento.",
        "intents": (
            "clicar no botao clicar no link clicar no elemento aperta o botao no site "
            "abra o primeiro link abra o segundo link abra o primeiro resultado entre no primeiro site "
            "clique no primeiro video abrir link da pagina clicar em entrar clicar em pesquisar "
            "click web element click link click button open first link"
        )
    },
    "interagir_pagina_web": {
        "description": "Controla e navega dentro da aba aberta do navegador: rolar para baixo/cima, topo/fim, voltar, avançar, atualizar, listar links ou fechar aba.",
        "intents": (
            "rolar pagina para baixo rolar para cima descer a pagina subir a pagina "
            "voltar para a pagina anterior avancar pagina atualizar pagina recarregar site "
            "ir para o final da pagina ir para o topo fechar aba listar links da pagina scroll down back"
        )
    },
    "digitar_campo_web": {
        "description": "Preenche campos de formulário, barra de busca ou caixa de texto no navegador.",
        "intents": (
            "digitar no campo preencher formulario digitar na busca do site preencher campo web "
            "escrever na caixa de pesquisa type in field fill form input text web"
        )
    },
    "ler_conteudo_pagina": {
        "description": "Lê e resume o texto da página da web atualmente aberta no navegador.",
        "intents": (
            "ler pagina ler o conteudo do site o que esta escrito no site ler noticia "
            "extrair texto do site resumir o site read web page page content"
        )
    },
    "capturar_tela_web": {
        "description": "Tira uma captura de tela da página aberta no navegador.",
        "intents": (
            "print da pagina print do site screenshot do navegador salvar imagem do site capture webpage"
        )
    },
    "fechar_navegador": {
        "description": "Fecha a janela do navegador web controlada pela assistente.",
        "intents": (
            "fechar navegador encerrar browser fechar chrome fechar internet fechar pagina web close browser"
        )
    },
    "localizar_e_clicar_imagem": {
        "description": "Localiza visualmente um botão ou ícone na tela usando OpenCV e clica nele.",
        "intents": (
            "encontrar botao na tela clicar no icone buscar imagem na tela localizar visualmente "
            "clicar pelo botao visual achar botao find image on screen click visual icon"
        )
    },
    "ler_texto_da_tela": {
        "description": "Extrai e lê em voz alta textos escritos na tela do computador usando OCR (PyTesseract).",
        "intents": (
            "ler texto da tela o que esta escrito na tela ler foto o que diz aqui "
            "extrair texto da imagem ler tela ler palavras na tela screen ocr read screen text"
        )
    },
    "gerenciar_arquivos": {
        "description": "Copia, move, deleta, cria pastas ou lista arquivos no computador usando Pathlib e Shutil.",
        "intents": (
            "copiar arquivo mover pasta deletar arquivo criar pasta listar arquivos na pasta "
            "apagar arquivo transferir pasta organizar arquivos manage files folder copy move delete"
        )
    },
    "consultar_planilha": {
        "description": "Lê, processa e filtra dados em planilhas Excel (.xlsx) e CSVs com Pandas e OpenPyXL.",
        "intents": (
            "analisar planilha ler excel ler arquivo csv consultar dados na planilha "
            "filtrar tabela ver linhas do excel processar planilha pandas excel csv data"
        )
    },
    "criar_planilha": {
        "description": "Cria uma nova planilha Excel (.xlsx) personalizada e a abre no Microsoft Excel.",
        "intents": (
            "criar planilha gerar planilha fazer planilha nova planilha criar excel "
            "gerar tabela excel exportar para excel criar planilha de vendas create spreadsheet"
        )
    },
    "abrir_planilha": {
        "description": "Abre o aplicativo Microsoft Excel ou abre um arquivo de planilha diretamente no Excel na tela.",
        "intents": (
            "abrir excel abrir aplicativo excel abrir planilha iniciar excel mostrar excel "
            "abrir arquivo excel ver planilha no excel launch excel open spreadsheet"
        )
    },
    "editar_planilha": {
        "description": "Edita uma planilha existente: adiciona ou remove linhas, altera valores, adiciona ou remove colunas.",
        "intents": (
            "adicionar linha na planilha remover linha da planilha apagar registro da planilha "
            "editar valor na planilha alterar celula atualizar planilha mudar valor no excel "
            "adicionar coluna remover coluna inserir dados na planilha edit spreadsheet update row"
        )
    },
    "criar_documento_word": {
        "description": "Cria um novo documento Microsoft Word (.docx) formatado com título, subtítulo, parágrafos e seções, abrindo-o em segundo plano.",
        "intents": (
            "criar documento word criar word novo documento word gerar relatorio word "
            "escrever documento docx criar texto no word montar contrato no word create word document"
        )
    },
    "editar_documento_word": {
        "description": "Edita um documento Word (.docx) existente ao vivo: adiciona parágrafos, adiciona seções, substitui ou remove trechos de texto.",
        "intents": (
            "editar documento word adicionar paragrafo no word escrever paragrafo no documento "
            "adicionar secao no word substituir texto no word remover paragrafo do word edit word doc"
        )
    },
    "ler_documento_word": {
        "description": "Lê e extrai todo o conteúdo de texto, parágrafos e tabelas de um documento Word (.docx).",
        "intents": (
            "ler documento word ler arquivo docx o que esta escrito no word "
            "mostrar conteudo do documento word resumir documento word read word document"
        )
    },
    "abrir_documento_word": {
        "description": "Abre o Microsoft Word ou um documento .docx específico em segundo plano na tela.",
        "intents": (
            "abrir word abrir documento word iniciar microsoft word abrir arquivo docx "
            "mostrar documento no word open word document launch word"
        )
    },
    "agendar_execucao": {
        "description": "Agenda uma tarefa ou alarme no robô com a biblioteca schedule.",
        "intents": (
            "agendar tarefa agendar para as rodar todo dia as a cada minutos "
            "marcar compromisso lembrete agendado agendar execucao schedule task at time"
        )
    },
    "listar_agendamentos": {
        "description": "Lista todas as tarefas agendadas ativas na assistente.",
        "intents": (
            "quais tarefas estao agendadas listar agendamentos ver lembretes agendados list scheduled tasks"
        )
    },
    "enviar_alerta_webhook": {
        "description": "Envia uma notificação externa para WhatsApp, Telegram ou Discord via webhook com Requests.",
        "intents": (
            "enviar alerta mandar mensagem no whatsapp enviar notificacao telegram "
            "disparar webhook avisar no celular send webhook alert notification"
        )
    },
    "consultar_mapa_codigo": {
        "description": "Consulta o mapa mental e arquitetural da FRYIVS (Graphify) para localizar onde funções, classes, arquivos e módulos estão no código e suas conexões.",
        "intents": (
            "consultar mapa do codigo onde fica a funcao onde esta definido no projeto "
            "arquitetura do codigo mapa mental localizar arquivo modulo graphify onde fica o codigo "
            "procurar funcao no sistema mapa de arquivos code graph query"
        )
    },
    "explicar_modulo_grafo": {
        "description": "Explica em detalhes a anatomia de um componente específico no grafo de conhecimento, dependências e conexões.",
        "intents": (
            "explicar modulo anatomia da funcao dependencias de entrada e saida "
            "o que essa funcao chama relacoes no grafo analisar componente detalhes do modulo"
        )
    },
    "caminho_entre_componentes": {
        "description": "Traça a rota arquitetural e o caminho mais curto de chamadas entre dois componentes ou módulos da FRYIVS.",
        "intents": (
            "caminho entre componentes fluxo de chamadas ligacao entre modulos como conecta "
            "rota no grafo distancia estrutural shortest path between modules"
        )
    },
    "resumo_arquitetura_sistema": {
        "description": "Retorna uma visão panorâmica e macroscópica de toda a arquitetura da FRYIVS, God Nodes e componentes centrais.",
        "intents": (
            "resumo da arquitetura visao geral do projeto mapa da fryivs estrutura do sistema "
            "god nodes nucleos centrais componentes principais arquitetura geral"
        )
    },
    "atualizar_mapa_codigo": {
        "description": "Reindexa e atualiza o grafo de conhecimento e o mapa do código da FRYIVS via Graphify.",
        "intents": (
            "atualizar mapa do codigo reindexar grafo graphify atualizar arquitetura "
            "recarregar mapa mental reindexar codigo rebuild code graph"
        )
    },
    "disparar_workflow_n8n": {
        "description": "Dispara um workflow corporativo no n8n (briefing, alerta, status ou automação externa) via webhook assinado com HMAC-SHA256 e proteção SSRF.",
        "intents": (
            "disparar workflow n8n acionar workflow n8n executar fluxo n8n rodar automacao n8n "
            "chamar webhook n8n enviar briefing n8n disparar alerta n8n trigger n8n workflow"
        )
    },
    "listar_workflows_n8n": {
        "description": "Lista os workflows cadastrados e ativos na instância n8n corporativa, com filtro opcional por tag.",
        "intents": (
            "listar workflows n8n quais workflows n8n mostrar fluxos n8n ver automacoes n8n "
            "workflows ativos no n8n list n8n workflows"
        )
    },
    "consultar_execucoes_n8n": {
        "description": "Consulta o histórico de execuções recentes de workflows no n8n (status success, error, running, waiting).",
        "intents": (
            "consultar execucoes n8n historico de execucoes n8n logs do n8n verificar execucoes n8n "
            "ultimas execucoes workflow n8n status execucao n8n list n8n executions"
        )
    },
    "delegar_missao_hermes": {
        "description": "Delega uma missão longa ou especializada em segundo plano para um subagente especialista (pesquisador, organizador, ideias ou engenheiro).",
        "intents": (
            "delegar missao hermes delegar tarefa para agente acionar subagente "
            "mandar agente pesquisador organizador de dados ideias engenheiro executar em segundo plano "
            "orquestrar subagente delegate agent mission"
        )
    },
    "consultar_status_agentes": {
        "description": "Consulta o status das missões delegadas aos subagentes Hermes, consumo do Budget Guard (tokens/USD, concorrência) e aprovações Tier 3 pendentes.",
        "intents": (
            "consultar status agentes status dos agentes status do hermes como estao os agentes "
            "missoes em andamento orcamento budget guard aprovacoes pendentes tier 3 check agent status"
        )
    },
    "cancelar_missao_agente": {
        "description": "Cancela uma missão específica do Hermes Agent ou aciona o Kill-Switch de emergência para encerrar todos os agentes ativos.",
        "intents": (
            "cancelar missao agente cancelar job hermes parar agente encerrar agentes "
            "kill switch kill all abortar missao subagente cancel agent job"
        )
    },
    "listar_perfis_hermes": {
        "description": "Lista os 4 perfis especialistas do Hermes Agent (pesquisador, engenheiro, analista e sentinela), suas ferramentas e sandboxes.",
        "intents": (
            "listar perfis hermes quais perfis hermes quais subagentes existem "
            "mostrar agentes especialistas perfis disponiveis hermes list hermes profiles"
        )
    },
}


SKILL_KEYWORD_RULES: Final[dict[str, list[str]]] = {
    "abrir_programa": [
        "abrir", "abre", "abra", "iniciar", "inicie", "executar", "execute", "lancar", "lanca",
        "roda", "rodar", "rode", "programa", "aplicativo", "app", "software", "bloco de notas", "notepad",
        "calculadora", "calc", "chrome", "navegador", "browser", "cmd", "terminal", "powershell",
        "vscode", "code", "spotify", "spotfy", "discord", "wordpad", "mspaint", "paint", "explorer", "pastas",
        "mostre o explorador", "explorador de arquivos", "gerenciador de tarefas", "task manager",
        "quero ver o", "me mostra o", "me mostre o", "me abre o", "me abra o",
        "abre o", "abra o", "inicia o", "roda o", "rode o",
    ],
    "listar_janelas": [
        "listar janelas", "quais janelas", "janelas abertas", "janelas ativas",
        "programas abertos", "mostrar janelas", "telas abertas", "ver janelas"
    ],
    "focar_janela": [
        "focar", "foca", "foque", "foco na janela", "trazer para frente", "alternar para",
        "mudar para", "ir para janela", "ativar janela"
    ],
    "minimizar_janela": [
        "minimizar", "minimiza", "minimize", "ocultar janela", "esconder janela", "abaixar janela"
    ],
    "maximizar_janela": [
        "maximizar", "maximiza", "maximize", "tela cheia", "expandir janela", "aumentar tela"
    ],
    "fechar_janela": [
        "fechar", "fecha", "feche", "encerrar", "encerra", "encerre", "finalizar", "mata o processo"
    ],
    "digitar_texto": [
        "digitar", "digite", "digita", "escrever", "escreva", "escreve", "preencher campo"
    ],
    "pressionar_atalho": [
        "atalho", "pressionar", "pressione", "aperte", "apertar", "teclas", "ctrl", "alt", "enter"
    ],
    "controlar_volume": [
        "volume", "som", "áudio", "audio", "mutar", "mudo", "desmutar", "silenciar",
        "silencie", "silencia", "mute", "muta", "desmute",
        "aumentar som", "aumentar volume", "abaixar volume", "diminuir som"
    ],
    "tirar_screenshot": [
        "screenshot", "print", "printscreen", "captura de tela", "capturar tela", "tirar print", "foto da tela"
    ],
    "obter_hora_data": [
        "que horas", "qual a hora", "qual e a hora", "horario", "horário", "hora atual", "data atual",
        "que dia e hoje", "que dia é hoje", "dia de hoje", "em que dia estamos", "em que dia",
        "data de hoje", "qual a data", "qual e a data", "dia da semana", "calendario", "calendário",
        "diga as horas", "fale as horas", "dizer as horas", "falar as horas", "sabe as horas",
        "informe a hora", "informa a hora", "informe a data", "informa a data", "horas sao", "horas são"
    ],
    "pesquisar_informacao_web": [
        "pesquise sobre", "pesquisar sobre", "pesquisa sobre", "busque sobre", "buscar sobre",
        "procure sobre", "procurar sobre", "o que é", "o que e", "quem é", "quem e", "quem foi",
        "qual a cotação", "qual a cotacao", "qual o valor", "notícias sobre", "noticias sobre",
        "notícias de hoje", "noticias de hoje", "últimas notícias", "ultimas noticias",
        "pesquise na internet", "pesquisar na internet", "busca na internet", "buscar na internet",
        "pesquise na web", "pesquisar na web", "busca na web", "pesquisa na web",
        "pesquise informações", "pesquisar informacoes", "pesquisa informacoes",
        "como funciona", "fatos sobre", "resumo sobre",
        "clima", "previsão do tempo", "previsao do tempo", "como está o tempo", "como esta o tempo",
        "temperatura em", "temperatura hoje", "vai chover"
    ],
    "pesquisar_google": [
        "abra o chrome e pesquise", "abra o edge e pesquise", "abra o navegador e pesquise",
        "pesquise no chrome", "pesquisar no chrome", "pesquisa no chrome", "procure no chrome",
        "pesquise no edge", "pesquisar no edge", "pesquisa no edge", "procure no edge",
        "abra o chrome e procure", "abra o edge e procure",
        "no chrome pesquise", "no edge pesquise", "no navegador pesquise",
        "abrir no chrome", "abrir no edge", "abrir chrome e pesquisar", "abrir edge e pesquisar",
        "pesquisa no google", "pesquisar no google", "pesquise no google", "busca no google", "buscar no google"
    ],
    "pesquisar_youtube": [
        "pesquisa no youtube", "pesquisar no youtube", "tocar musica", "toca uma musica",
        "toca musica", "tocar no youtube", "toca no youtube", "ouvir musica", "ouvir música",
        "musica no youtube", "música no youtube", "video no youtube", "vídeo no youtube", "pesquise no youtube",
        "busca videos", "busque videos", "buscar videos", "procure videos", "procurar videos"
    ],
    "status_sistema": [
        "status do sistema", "uso de cpu", "uso de memoria", "uso de memória", "uso de ram",
        "consumo de ram", "bateria", "desempenho do pc", "como esta o pc", "como está o pc", "status do computador"
    ],
    "bloquear_tela": [
        "bloquear tela", "bloquear pc", "bloquear computador", "travar tela", "trancar tela", "bloqueie a tela"
    ],
    "navegar_para": [
        "navegar para", "acesse o site", "abra o site", "entrar no site", "acesse https",
        "navegue para", "abra o link", "ir para o site", "abrir pagina",
        "acesse esse link", "acesse o link", "acessar o link", "acessar esse link",
        "acesse no chrome", "acesse no edge", "acessar no chrome", "acessar no edge",
    ],
    "pesquisar_na_web": [
        "automacao web", "automação web", "navegacao com selenium", "interagir no site"
    ],
    "clicar_elemento_web": [
        "clique no botao", "clique no link", "clicar no elemento", "clicar no botao", "clique em", "aperte o botao no site",
        "abra o primeiro", "abra o segundo", "abra o terceiro", "abra o quarto", "abra o quinto",
        "acesse o primeiro", "acesse o segundo", "acesse o terceiro",
        "primeiro link", "segundo link", "terceiro link", "quarto link", "quinto link", "ultimo link", "último link",
        "primeiro resultado", "segundo resultado", "terceiro resultado",
        "primeiro video", "primeiro vídeo", "segundo video", "segundo vídeo",
        "abra esse link", "abrir o link", "entre no link", "entre no primeiro", "entre no segundo",
        "clique no primeiro", "clique no segundo", "clique no terceiro", "clique no resultado", "clique no video", "clique no vídeo"
    ],
    "interagir_pagina_web": [
        "rolar pagina", "rolar página", "role a pagina", "role a página", "role para baixo", "role para cima",
        "rolar para baixo", "rolar para cima", "desça a pagina", "desça a página", "desca a pagina", "descer a pagina",
        "suba a pagina", "suba a página", "subir a pagina", "voltar pagina", "voltar página", "volte a pagina",
        "pagina anterior", "página anterior", "avancar pagina", "avançar página", "atualizar pagina", "atualize a pagina",
        "recarregar pagina", "fechar aba", "feche a aba", "listar links"
    ],
    "digitar_campo_web": [
        "digitar no campo", "digite no site", "preencher campo no site", "escreva no campo web"
    ],
    "ler_conteudo_pagina": [
        "ler pagina", "leia a pagina", "conteudo do site", "o que esta no site", "ler noticia", "leia o site"
    ],
    "capturar_tela_web": [
        "print da pagina", "print do site", "captura da pagina web"
    ],
    "fechar_navegador": [
        "fechar navegador", "feche o navegador", "fechar browser", "feche a internet"
    ],
    "localizar_e_clicar_imagem": [
        "localizar botao", "clique no icone", "achar botao na tela", "busca visual"
    ],
    "ler_texto_da_tela": [
        "ler texto da tela", "o que esta escrito na tela", "leia a tela", "ler o que esta na tela", "ocr na tela"
    ],
    "gerenciar_arquivos": [
        "copiar arquivo", "mover arquivo", "deletar arquivo", "criar pasta", "listar arquivos"
    ],
    "consultar_planilha": [
        "analisar planilha", "consultar planilha", "filtrar planilha", "ler csv", "dados da planilha", "ver planilha"
    ],
    "criar_planilha": [
        "criar planilha", "crie uma planilha", "cria uma planilha", "crie planilha", "cria planilha",
        "gerar planilha", "gere uma planilha", "gera uma planilha", "fazer planilha", "faca uma planilha",
        "faca planilha", "monte uma planilha", "montar planilha", "desenvolva uma planilha",
        "desenvolver planilha", "nova planilha", "criar excel", "crie um excel", "gerar excel",
        "gere um excel", "planilha de vendas", "planilha de controle", "planilha financeira"
    ],
    "abrir_planilha": [
        "abrir planilha", "abrir excel", "iniciar excel", "mostrar excel", "excel para planilhas", "planilha no excel", "ver excel"
    ],
    "editar_planilha": [
        "adicionar na planilha", "adicione na planilha", "adicione uma linha", "adicionar linha",
        "adiciona uma linha", "bota mais um item", "insere uma linha", "coloca na planilha",
        "remover da planilha", "remova da planilha", "remova a linha", "remover linha", "apague a linha",
        "editar planilha", "edite a planilha", "alterar na planilha", "altere na planilha",
        "atualizar planilha", "atualize a planilha", "adicionar coluna", "adicione uma coluna",
        "remover coluna", "remova a coluna"
    ],
    "criar_documento_word": [
        "criar documento word", "crie um documento word", "cria um documento word",
        "criar um word", "crie um word", "cria um word", "novo documento word",
        "gerar documento word", "gere um documento word", "fazer um word", "faca um documento word",
        "criar arquivo docx", "criar relatorio no word", "crie um relatorio no word"
    ],
    "editar_documento_word": [
        "editar documento word", "edite o documento word", "edita o word",
        "adicionar paragrafo", "adicione um paragrafo", "adicione um parágrafo",
        "adiciona um paragrafo", "adiciona um parágrafo", "escreve um paragrafo", "escreve um parágrafo",
        "escreva um paragrafo", "escreva um parágrafo", "insira um paragrafo", "insere um paragrafo",
        "adicionar secao no word", "adicione uma secao", "adicione uma seção",
        "substituir texto no word", "substitua no word", "remover paragrafo do word"
    ],
    "ler_documento_word": [
        "ler documento word", "leia o documento word", "le o documento word", "lê o documento word",
        "ler o word", "leia o word", "conteudo do word", "conteúdo do word", "ler arquivo docx"
    ],
    "abrir_documento_word": [
        "abrir documento word", "abra o documento word", "abre o documento word",
        "abrir o word", "abra o word", "abre o word", "iniciar word", "abrir arquivo docx"
    ],
    "agendar_execucao": [
        "agendar tarefa", "agende para", "todo dia as", "a cada minutos", "agendar rotina"
    ],
    "listar_agendamentos": [
        "listar agendamentos", "tarefas agendadas", "quais agendamentos"
    ],
    "enviar_alerta_webhook": [
        "enviar alerta", "mandar no whatsapp", "notificacao no telegram", "disparar webhook"
    ],
    "consultar_mapa_codigo": [
        "mapa do codigo", "mapa do projeto", "onde fica", "onde esta", "onde esta definido",
        "onde fica a funcao", "onde fica o modulo", "localizar no codigo", "grafo do codigo",
        "consultar codigo", "buscar no codigo", "mapa mental do codigo", "onde fica o arquivo"
    ],
    "explicar_modulo_grafo": [
        "explicar modulo", "explique o modulo", "explique modulo", "explicar a funcao", "explique a funcao",
        "dependencias da funcao", "o que chama", "anatomia da funcao", "relacoes da funcao", "detalhar modulo",
        "detalhe o modulo", "explique o componente", "explicar componente"
    ],
    "caminho_entre_componentes": [
        "caminho entre", "rota entre", "fluxo entre", "como se conecta", "ligacao entre",
        "comunicacao entre", "caminho no grafo"
    ],
    "resumo_arquitetura_sistema": [
        "resumo da arquitetura", "visao geral do sistema", "mapa da fryivs", "estrutura do sistema",
        "god nodes", "arquitetura geral", "visao macro", "como o sistema e estruturado", "mapa geral"
    ],
    "atualizar_mapa_codigo": [
        "atualizar mapa", "reindexar grafo", "reindexar codigo", "atualizar grafo",
        "recarregar mapa", "atualizar mapa mental"
    ],
    "disparar_workflow_n8n": [
        "disparar workflow", "dispare o workflow", "acionar workflow", "acione o workflow",
        "executar workflow", "execute o workflow", "rodar workflow", "rode o workflow",
        "workflow n8n", "fluxo n8n", "fluxo no n8n", "automacao n8n", "automacao no n8n",
        "webhook n8n", "briefing n8n", "briefing no n8n", "disparar n8n", "dispare no n8n",
        "acionar n8n", "rodar no n8n", "chamar n8n"
    ],
    "listar_workflows_n8n": [
        "listar workflows", "liste os workflows", "quais workflows", "mostrar workflows",
        "mostre os workflows", "ver workflows", "workflows do n8n", "workflows no n8n",
        "workflows n8n", "workflows ativos", "listar fluxos n8n", "quais fluxos n8n"
    ],
    "consultar_execucoes_n8n": [
        "consultar execucoes", "consulte as execucoes", "execucoes n8n", "execucoes do n8n",
        "execucoes no n8n", "historico n8n", "historico do n8n", "historico de execucoes",
        "ultimas execucoes n8n", "ultimas execucoes do n8n", "status das execucoes",
        "logs do n8n", "logs n8n", "ver execucoes"
    ],
    "delegar_missao_hermes": [
        "delegar missao", "delegue a missao", "delegue uma missao", "delegar tarefa",
        "delegue a tarefa", "delegar para o hermes", "delegar ao hermes", "delegar para agente",
        "delegar ao agente", "mandar o hermes", "mande o hermes", "pedir ao hermes",
        "acionar hermes", "acionar subagente", "subagente pesquisador", "subagente engenheiro",
        "subagente analista", "subagente sentinela", "agente pesquisador", "agente engenheiro",
        "agente analista", "agente sentinela", "perfil pesquisador", "perfil engenheiro",
        "perfil analista", "perfil sentinela", "missao hermes", "missao para o hermes",
        "delegar para o pesquisador", "delegar para o engenheiro",
        "delegar para o analista", "delegar para o sentinela"
    ],
    "consultar_status_agentes": [
        "status dos agentes", "status de agentes", "status do hermes", "status hermes",
        "consultar agentes", "consultar status dos agentes", "como estao os agentes",
        "agentes ativos", "missoes ativas", "missoes em andamento", "orcamento dos agentes",
        "budget guard", "budget dos agentes", "aprovacoes pendentes", "aprovacoes tier 3",
        "status da missao", "progresso do agente", "progresso da missao"
    ],
    "cancelar_missao_agente": [
        "cancelar missao", "cancele a missao", "cancelar agente", "cancele o agente",
        "cancelar job", "cancele o job", "parar agente", "pare o agente",
        "parar agentes", "pare os agentes", "encerrar agentes", "encerre os agentes",
        "encerrar todos os agentes", "matar agentes", "kill switch", "kill-switch",
        "kill all", "abortar missao", "aborte a missao", "abortar agente"
    ],
    "listar_perfis_hermes": [
        "listar perfis hermes", "perfis hermes", "perfis do hermes", "quais perfis",
        "perfis de agentes", "perfis especialistas", "quais agentes", "quais subagentes",
        "listar agentes", "listar subagentes", "agentes disponiveis", "subagentes disponiveis"
    ],
}


_SUBSTITUICOES_FONETICAS: Final[tuple[tuple[str, str], ...]] = (
    ("ex sel", "excel"),
    ("ec sel", "excel"),
    ("ecsel", "excel"),
    ("exel", "excel"),
    ("ekcel", "excel"),
    ("pai ton", "python"),
    ("paiton", "python"),
    ("payton", "python"),
    ("pyton", "python"),
    ("uordi", "word"),
    ("uord", "word"),
    ("wordi", "word"),
    ("guord", "word"),
    ("do cumento", "documento"),
    ("es poti fai", "spotify"),
    ("espotifai", "spotify"),
    ("ispotifai", "spotify"),
    ("spotfai", "spotify"),
    ("crome", "chrome"),
    ("cromi", "chrome"),
    ("gugou", "google"),
    ("gugo", "google"),
    ("iu tubi", "youtube"),
    ("iutubi", "youtube"),
    ("utube", "youtube"),
    ("pri inti", "print"),
    ("printi", "print"),
    ("iscreenshot", "screenshot"),
    ("noti pedi", "notepad"),
    ("noteped", "notepad"),
    (" uatizapi", " whatsapp"),
    (" zap ", " whatsapp "),
    ("joga pra baixo", "role a página para baixo"),
    ("joga para baixo", "role a página para baixo"),
    ("desce a pagina", "role a página para baixo"),
    ("desce a página", "role a página para baixo"),
    ("desce a tela", "role a página para baixo"),
    ("desce ai", "role a página para baixo"),
    ("desce aí", "role a página para baixo"),
    ("rola pra baixo", "role a página para baixo"),
    ("role pra baixo", "role a página para baixo"),
    ("joga pra cima", "role a página para cima"),
    ("joga para cima", "role a página para cima"),
    ("sobe a pagina", "role a página para cima"),
    ("sobe a página", "role a página para cima"),
    ("sobe a tela", "role a página para cima"),
    ("rola pra cima", "role a página para cima"),
    ("role pra cima", "role a página para cima"),
    ("da um zoom", "pressione o atalho ctrl+mais"),
    ("dá um zoom", "pressione o atalho ctrl+mais"),
    ("aumenta o zoom", "pressione o atalho ctrl+mais"),
    ("aproxima a tela", "pressione o atalho ctrl+mais"),
    ("tira o zoom", "pressione o atalho ctrl+menos"),
    ("diminui o zoom", "pressione o atalho ctrl+menos"),
    ("da um confere nas janelas", "listar janelas abertas"),
    ("dá um confere nas janelas", "listar janelas abertas"),
    ("bota mais som", "aumentar volume"),
    ("sobe o som", "aumentar volume"),
    ("abaixa o som", "diminuir som"),
    ("baixa o som", "diminuir som"),
    ("corta o som", "mutar volume"),
    ("tira o som", "mutar volume"),
)


def normalizar_consulta_roteamento(query: str) -> str:
    """
    Corrige erros fonéticos típicos do Whisper, remove acentuação para matching uniforme
    e traduz gírias/informalidades para a forma canônica compreendida pelo roteador de skills.
    """
    if not query:
        return ""
    q = f" {_sem_acentos(query.lower().strip())} "
    for errado, correto in _SUBSTITUICOES_FONETICAS:
        err_norm = _sem_acentos(errado)
        cor_norm = _sem_acentos(correto)
        if err_norm in q:
            q = q.replace(err_norm, cor_norm)
    return q.strip()


def eh_comando_vago_ou_perigoso(query: str) -> tuple[bool, str]:
    """
    Detecta comandos vagos ou potencialmente destrutivos que não especificam
    o alvo (ex.: 'fecha tudo', 'apaga isso', 'manda ver', 'manda isso pro Discord').
    Retorna `(True, mensagem_segura)` quando deve ser bloqueado.
    """
    q = normalizar_consulta_roteamento(query)
    if not q:
        return False, ""

    if any(p in q for p in (
        "fecha tudo", "feche tudo", "fechar tudo", "mata tudo", "encerrar tudo",
        "encerra tudo", "fecha todas as janelas", "feche todas as janelas", "apaga tudo",
        "deleta tudo", "delete tudo", "exclui tudo", "formata o pc", "formatar o pc",
        "apaga o windows", "deleta o windows", "apague tudo"
    )):
        return True, (
            "Por segurança, senhor, não executo fechamento ou exclusão global indiscriminada. "
            "Informe especificamente qual janela ou arquivo deseja fechar ou remover."
        )

    if any(p in q for p in (
        "apaga isso", "apague isso", "deleta isso", "delete isso",
        "exclui isso", "exclua isso", "remove isso", "remova isso", "joga isso fora"
    )) and not any(alvo in q for alvo in ("linha", "paragrafo", "parágrafo", "coluna", "planilha", "word")):
        return True, (
            "Por segurança, senhor, especifique exatamente o nome do arquivo, linha ou item que deseja remover."
        )

    if any(p in q for p in (
        "manda isso pro discord", "envia isso pro discord", "posta isso no discord",
        "joga isso no discord", "manda isso no discord", "manda isso pro whatsapp",
        "envia isso no whatsapp", "manda isso pro telegram"
    )) and "http" not in q:
        return True, (
            "Senhor, para enviar um alerta externo preciso saber a mensagem exata e a URL do webhook de destino."
        )

    if q in (
        "manda ver", "manda bala", "faz ai", "faz aí", "executa ai", "executa aí",
        "pode fazer", "arrocha", "vai fundo", "faz isso", "faca isso", "faça isso"
    ):
        return True, "Estou pronta, senhor. Qual comando específico deseja que eu execute?"

    return False, ""


def eh_consulta_memoria_ou_rag(query: str) -> bool:
    """
    Identifica perguntas voltadas à memória episódica da conversa ou aos documentos
    técnicos indexados na base de conhecimento RAG (sem disparar skills de automação).
    """
    q = normalizar_consulta_roteamento(query)
    gatilhos_mem_rag = (
        "o que eu te disse", "o que eu falei", "o que conversamos", "lembra do que",
        "qual foi o projeto que", "sobre o projeto ontem", "eu te contei", "voce lembra",
        "você lembra", "na nossa conversa", "segundo a base de conhecimento",
        "no documento indexado", "nos documentos indexados", "segundo o guia",
        "como usar procx", "como funciona o procx", "indice e corresp", "índice e corresp",
        "tabela dinamica no guia", "checklist de qualidade", "arquitetura de abas",
        "padrão de cores da planilha", "padrao de cores da planilha", "formulas matriciais",
        "fórmulas matriciais", "power query", "power pivot", "medidas dax",
    )
    return any(g in q for g in gatilhos_mem_rag)


class SkillRouter:
    """Gerenciador de roteamento e busca semântica de skills no ChromaDB."""

    def __init__(self, collection_name: str = "fryvis_skills_v2"):
        self.collection_name = collection_name
        self.collection = get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        self._schemas_by_name: dict[str, dict[str, Any]] = {
            schema.get("function", {}).get("name", ""): schema
            for schema in ALL_SKILL_SCHEMAS
            if "function" in schema
        }

    def ensure_skills_indexed(self, force: bool = False) -> None:
        """
        Garante que todas as skills cadastradas estejam vetorizadas na coleção do ChromaDB.
        Executado de forma rápida para não bloquear inicializações subsequentes.
        """
        try:
            current_count = self.collection.count()
            expected_count = len(ALL_SKILL_SCHEMAS)

            if not force and current_count >= expected_count:
                return

            ids: list[str] = []
            documents: list[str] = []
            metadatas: list[dict[str, Any]] = []

            for schema in ALL_SKILL_SCHEMAS:
                func_data = schema.get("function", {})
                name = func_data.get("name", "")
                if not name:
                    continue

                profile = SKILL_SEMANTIC_PROFILES.get(name, {})
                desc = profile.get("description", func_data.get("description", ""))
                intents = profile.get("intents", "")

                doc_text = f"Skill: {name}. Ação: {desc}. Termos: {intents}"
                
                ids.append(name)
                documents.append(doc_text)
                metadatas.append({
                    "name": name,
                    "schema_json": json.dumps(schema)
                })

            if ids:
                self.collection.upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas
                )
        except Exception as e:
            print(f"[SkillRouter] Aviso ao indexar skills: {e}")

    def search_relevant_skills(
        self,
        query: str,
        top_k: int = 6,
        threshold: float = 0.50
    ) -> list[dict[str, Any]]:
        """
        Busca híbrida de skills (RAG): combina detecção léxica/keyword com busca
        semântica densa HNSW no ChromaDB para garantir recall máximo sem poluir o contexto.
        """
        if not query or not query.strip():
            return []

        bloqueado, _ = eh_comando_vago_ou_perigoso(query)
        if bloqueado or eh_consulta_memoria_ou_rag(query):
            return []

        q_lower = normalizar_consulta_roteamento(query)
        matched_names: list[str] = []
        _weak_question_starters = ("o que e", "como funciona")

        for skill_name, triggers in SKILL_KEYWORD_RULES.items():
            for trigger in triggers:
                trig_norm = _sem_acentos(trigger)
                if threshold <= 0.35 and trig_norm in _weak_question_starters:
                    continue
                if trig_norm == "o que e" and "o que e " not in f"{q_lower} ":
                    continue
                if trig_norm in q_lower:
                    if skill_name not in matched_names:
                        matched_names.append(skill_name)
                    break

        if "abrir_programa" in matched_names and len(matched_names) > 1:
            matched_names.remove("abrir_programa")


        _is_expl_grafo = any(k in q_lower for k in (
            "explica o modulo", "explique o modulo", "explicar modulo", "explique modulo",
            "detalhe o modulo", "detalhar modulo", "anatomia da funcao", "dependencias da funcao",
        ))
        _is_caminho_grafo = any(k in q_lower for k in (
            "caminho entre", "rota entre", "fluxo entre", "ligacao entre", "como se conecta", "caminho no grafo",
        ))
        _is_resumo_grafo = any(k in q_lower for k in (
            "resumo da arquitetura", "visao geral do sistema", "mapa da fryivs",
            "estrutura do sistema", "god nodes", "arquitetura geral", "visao macro",
        ))
        _is_atualizar_grafo = any(k in q_lower for k in (
            "atualizar mapa", "reindexar grafo", "reindexar codigo", "atualizar grafo", "recarregar mapa",
        ))
        _is_consulta_grafo = any(k in q_lower for k in (
            "mapa do codigo", "onde fica a funcao", "onde fica o modulo", "onde esta definido",
            "localizar no codigo", "no seu codigo", "consultar mapa", "grafo do codigo",
        ))
        _is_graphify = any((
            _is_expl_grafo, _is_caminho_grafo, _is_resumo_grafo, _is_atualizar_grafo, _is_consulta_grafo
        ))
        if _is_graphify:
            if _is_expl_grafo:
                prim_g = "explicar_modulo_grafo"
            elif _is_caminho_grafo:
                prim_g = "caminho_entre_componentes"
            elif _is_resumo_grafo:
                prim_g = "resumo_arquitetura_sistema"
            elif _is_atualizar_grafo:
                prim_g = "atualizar_mapa_codigo"
            else:
                prim_g = "consultar_mapa_codigo"
            if prim_g in matched_names:
                matched_names.remove(prim_g)
            matched_names.insert(0, prim_g)
            matched_schemas = [
                self._schemas_by_name[name]
                for name in matched_names
                if name in self._schemas_by_name
            ]
            return matched_schemas[:top_k]

        _is_n8n_execucoes = (
            any(k in q_lower for k in (
                "consultar execucoes", "consulte as execucoes", "execucoes n8n",
                "execucoes do n8n", "execucoes no n8n", "historico n8n", "historico do n8n",
                "historico de execucoes", "ultimas execucoes n8n", "ultimas execucoes do n8n",
                "status das execucoes", "logs do n8n", "logs n8n", "ver execucoes",
            ))
            or (
                "n8n" in q_lower
                and any(w in q_lower for w in ("execuc", "historico", "log", "erros", "falhas"))
            )
        )
        _is_n8n_listar = (
            not _is_n8n_execucoes
            and (
                any(k in q_lower for k in (
                    "listar workflows", "liste os workflows", "quais workflows",
                    "mostrar workflows", "mostre os workflows", "ver workflows",
                    "workflows ativos", "listar fluxos n8n", "quais fluxos n8n",
                ))
                or (
                    any(k in q_lower for k in ("n8n", "workflow"))
                    and any(w in q_lower for w in ("listar", "liste", "quais", "mostrar", "mostre", "ativos", "cadastrados"))
                )
            )
        )
        _is_n8n_disparar = (
            not _is_n8n_execucoes
            and not _is_n8n_listar
            and (
                any(k in q_lower for k in (
                    "disparar workflow", "dispare o workflow", "acionar workflow", "acione o workflow",
                    "executar workflow", "execute o workflow", "rodar workflow", "rode o workflow",
                    "workflow n8n", "fluxo n8n", "fluxo no n8n", "automacao n8n", "automacao no n8n",
                    "webhook n8n", "briefing n8n", "briefing no n8n", "disparar n8n", "dispare no n8n",
                    "acionar n8n", "rodar no n8n", "chamar n8n",
                ))
                or (
                    any(k in q_lower for k in ("n8n", "workflow"))
                    and any(w in q_lower for w in ("dispar", "acion", "execut", "rodar", "rode", "chamar", "chame", "enviar", "envie", "briefing", "alerta", "webhook", "trigger"))
                )
                or (
                    "n8n" in q_lower
                    and not any(w in q_lower for w in ("o que e ", "quem criou", "como funciona"))
                )
            )
        )
        _is_n8n = _is_n8n_execucoes or _is_n8n_listar or _is_n8n_disparar
        if _is_n8n:
            if _is_n8n_execucoes:
                prim_n8n = "consultar_execucoes_n8n"
            elif _is_n8n_listar:
                prim_n8n = "listar_workflows_n8n"
            else:
                prim_n8n = "disparar_workflow_n8n"
            for n8n_skill in ("disparar_workflow_n8n", "listar_workflows_n8n", "consultar_execucoes_n8n"):
                if n8n_skill not in matched_names:
                    matched_names.append(n8n_skill)
            if prim_n8n in matched_names:
                matched_names.remove(prim_n8n)
            matched_names.insert(0, prim_n8n)
            for falso_pos in ("abrir_programa", "pesquisar_informacao_web", "pesquisar_google", "pesquisar_na_web"):
                if falso_pos in matched_names:
                    matched_names.remove(falso_pos)
            matched_schemas = [
                self._schemas_by_name[name]
                for name in matched_names
                if name in self._schemas_by_name
            ]
            return matched_schemas[:top_k]

        _is_hermes_cancelar = (
            any(k in q_lower for k in (
                "cancelar missao", "cancele a missao", "cancelar agente", "cancele o agente",
                "cancelar job", "cancele o job", "parar agente", "pare o agente",
                "parar agentes", "pare os agentes", "encerrar agentes", "encerre os agentes",
                "encerrar todos os agentes", "matar agentes", "kill switch", "kill-switch",
                "kill all", "abortar missao", "aborte a missao", "abortar agente",
            ))
            or (
                any(k in q_lower for k in ("hermes", "subagente", "agente"))
                and any(w in q_lower for w in ("cancel", "parar", "pare ", "encerr", "abort", "matar", "kill"))
            )
        )
        _is_hermes_perfis = (
            not _is_hermes_cancelar
            and (
                any(k in q_lower for k in (
                    "listar perfis hermes", "perfis hermes", "perfis do hermes",
                    "perfis de agentes", "perfis especialistas", "quais perfis",
                    "quais agentes", "quais subagentes", "listar agentes", "listar subagentes",
                    "agentes disponiveis", "subagentes disponiveis",
                ))
                or (
                    any(k in q_lower for k in ("hermes", "subagente"))
                    and any(w in q_lower for w in ("perfil", "perfis", "quais", "listar", "liste", "disponiveis"))
                )
            )
        )
        _is_hermes_status = (
            not _is_hermes_cancelar
            and not _is_hermes_perfis
            and (
                any(k in q_lower for k in (
                    "status dos agentes", "status de agentes", "status do hermes", "status hermes",
                    "consultar agentes", "consultar status dos agentes", "como estao os agentes",
                    "agentes ativos", "missoes ativas", "missoes em andamento",
                    "orcamento dos agentes", "budget guard", "budget dos agentes",
                    "aprovacoes pendentes", "aprovacoes tier 3",
                    "status da missao", "progresso do agente", "progresso da missao",
                ))
                or (
                    any(k in q_lower for k in ("hermes", "subagente"))
                    and any(w in q_lower for w in ("status", "progresso", "orcamento", "budget", "aprovac", "andamento", "como esta"))
                )
            )
        )
        _is_hermes_delegar = (
            not _is_hermes_cancelar
            and not _is_hermes_perfis
            and not _is_hermes_status
            and (
                any(k in q_lower for k in (
                    "delegar missao", "delegue a missao", "delegue uma missao",
                    "delegar tarefa", "delegue a tarefa", "delegar para o hermes", "delegar ao hermes",
                    "delegar para agente", "delegar ao agente", "mandar o hermes", "mande o hermes",
                    "pedir ao hermes", "acionar hermes", "acionar subagente",
                    "subagente pesquisador", "subagente engenheiro", "subagente analista", "subagente sentinela",
                    "agente pesquisador", "agente engenheiro", "agente analista", "agente sentinela",
                    "perfil pesquisador", "perfil engenheiro", "perfil analista", "perfil sentinela",
                    "missao hermes", "missao para o hermes",
                    "delegar para o pesquisador", "delegar para o engenheiro",
                    "delegar para o analista", "delegar para o sentinela",
                ))
                or "subagente" in q_lower
                or (
                    "hermes" in q_lower
                    and not any(w in q_lower for w in ("o que e ", "quem e ", "quem foi", "mitologia"))
                )
            )
        )
        _is_hermes = _is_hermes_cancelar or _is_hermes_perfis or _is_hermes_status or _is_hermes_delegar
        if _is_hermes:
            if _is_hermes_cancelar:
                prim_h = "cancelar_missao_agente"
            elif _is_hermes_perfis:
                prim_h = "listar_perfis_hermes"
            elif _is_hermes_status:
                prim_h = "consultar_status_agentes"
            else:
                prim_h = "delegar_missao_hermes"
            for hermes_skill in (
                "delegar_missao_hermes",
                "consultar_status_agentes",
                "cancelar_missao_agente",
                "listar_perfis_hermes",
            ):
                if hermes_skill not in matched_names:
                    matched_names.append(hermes_skill)
            if prim_h in matched_names:
                matched_names.remove(prim_h)
            matched_names.insert(0, prim_h)
            for falso_pos in ("abrir_programa", "pesquisar_informacao_web", "pesquisar_google", "pesquisar_na_web", "fechar_janela"):
                if falso_pos in matched_names:
                    matched_names.remove(falso_pos)
            matched_schemas = [
                self._schemas_by_name[name]
                for name in matched_names
                if name in self._schemas_by_name
            ]
            return matched_schemas[:top_k]

        _is_fechar_nav = any(k in q_lower for k in (
            "fechar navegador", "feche o navegador", "fecha o navegador",
            "fechar browser", "feche o browser", "fecha o browser", "encerrar navegador", "feche a internet",
            "fechar chrome", "feche o chrome", "fecha o chrome", "fechar edge", "feche o edge",
        ))
        _is_captura_web = any(k in q_lower for k in (
            "print da pagina", "print do site", "captura da pagina", "screenshot da pagina", "screenshot do site",
        ))
        _is_ler_web = (
            not any(r in q_lower for r in ("role ", "rola ", "rolar "))
            and any(k in f" {q_lower}" for k in (
                " ler pagina", " leia a pagina", " le a pagina", " conteudo do site", " conteudo da pagina",
                " leia o site", " ler o site", " o que esta no site", " o que diz na pagina", " resuma a pagina",
            ))
        )
        _is_nav_direta = any(k in q_lower for k in (
            "navegar para", "navegue para", "acesse o site", "abra o site", "abre o site", "entrar no site",
            "ir para o site", "va para o site", "acesse https", "acesse http", "entrar em www", "abra www",
            "acesse esse link", "acesse o link", "acessar o link", "acessar esse link",
            "acesse no chrome", "acesse no edge", "acessar no chrome", "acessar no edge",
        ))
        _is_selenium_search = any(k in q_lower for k in (
            "navegacao com selenium", "automacao web", "pesquisar na web", "pesquise na web com selenium",
            "modo copiloto", "copiloto no chrome", "copiloto web",
        ))
        _is_ocr_tela = any(k in q_lower for k in (
            "ler texto da tela", "escrito na tela", "leia a tela", "ler o que esta na tela", "ocr na tela", "texto da tela",
        ))
        _is_visao_clique = any(k in q_lower for k in (
            "busca visual", "clique no icone", "clicar no icone", "localizar botao", "achar botao na tela", ".png",
        ))
        _is_arquivos = any(k in q_lower for k in (
            "listar arquivos", "arquivos da pasta", "arquivos na pasta",
            "copiar arquivo", "mover arquivo", "deletar arquivo", "criar pasta",
        ))
        _is_agendar = any(k in q_lower for k in (
            "agendar tarefa", "agende para", "agendar para", "todo dia as", "a cada ", "agendar rotina",
        ))
        _is_listar_agend = any(k in q_lower for k in (
            "listar agendamentos", "tarefas agendadas", "quais agendamentos", "agendamentos estao programados",
        ))

        _browser_suffixes = (" no edge", " no chrome", " no microsoft edge", " no google chrome", " no navegador", " no google")
        _browser_search_triggers = (
            "pesquise no edge", "pesquise no chrome", "pesquisar no edge", "pesquisar no chrome",
            "pesquisa no edge", "pesquisa no chrome",
            "procure no edge", "procure no chrome",
            "abra o edge e pesquise", "abra o chrome e pesquise",
            "abre o edge e pesquisa", "abre o chrome e pesquisa",
            "abra o chrome e pesquisa", "abre o chrome e pesquise",
            "abra o edge e procure", "abra o chrome e procure",
            "abra o navegador e pesquise", "abra navegador e pesquise", "abre o navegador e pesquisa",
            "no edge pesquise", "no chrome pesquise", "no navegador pesquise",
            "usando o edge", "usando o chrome",
            "abrir no edge", "abrir no chrome",
            "pesquisa no google", "pesquisar no google", "busca no google", "pesquise no google", "procurar no google",
        )
        _is_browser_search = (
            not (_is_fechar_nav or _is_captura_web or _is_ler_web or _is_nav_direta or _is_selenium_search)
            and (
                any(k in q_lower for k in _browser_search_triggers)
                or (
                    any(sfx in q_lower for sfx in _browser_suffixes)
                    and any(v in q_lower for v in ("pesquis", "busca", "busque", "procure", "procur"))
                )
            )
        )
        if _is_browser_search:
            for ws_extra in ("clicar_elemento_web", "interagir_pagina_web", "navegar_para"):
                if ws_extra not in matched_names:
                    matched_names.append(ws_extra)
            if "pesquisar_google" in matched_names:
                matched_names.remove("pesquisar_google")
            matched_names.insert(0, "pesquisar_google")
            if "abrir_programa" in matched_names:
                matched_names.remove("abrir_programa")
            if "pesquisar_na_web" in matched_names:
                matched_names.remove("pesquisar_na_web")
            if "pesquisar_informacao_web" in matched_names:
                matched_names.remove("pesquisar_informacao_web")

        _web_info_triggers = (
            "pesquise sobre", "pesquisar sobre", "pesquisa sobre", "busque sobre", "buscar sobre",
            "procure sobre", "procurar sobre", "o que e ", "quem e ", "quem foi",
            "qual a cotacao", "qual o valor", "noticias sobre",
            "noticias de hoje", "ultimas noticias",
            "pesquise na internet", "pesquisar na internet", "busca na internet", "buscar na internet",
            "pesquise informacoes", "pesquisar informacoes", "pesquisa informacoes",
            "como funciona", "fatos sobre", "resumo sobre",
            "clima", "previsao do tempo", "como esta o tempo", "temperatura em", "temperatura hoje", "vai chover"
        )
        _active_web_triggers = (
            tuple(t for t in _web_info_triggers if t.strip() not in _weak_question_starters)
            if threshold <= 0.35 else _web_info_triggers
        )
        _is_web_info = (
            not _is_browser_search
            and not (_is_fechar_nav or _is_captura_web or _is_ler_web or _is_nav_direta or _is_selenium_search or _is_ocr_tela or _is_arquivos)
            and "planilha" not in q_lower
            and "youtube" not in q_lower
            and not any(v in q_lower for v in ("busca video", "busque video", "buscar video", "procure video", "procurar video"))
            and (
                any(k in q_lower for k in _active_web_triggers)
                or (
                    any(v in q_lower for v in ("pesquis", "busque", "procure"))
                    and not any(b in q_lower for b in ("chrome", "edge", "navegador", "browser", "youtube", "google", "selenium"))
                )
            )
        )
        if _is_web_info:
            if "pesquisar_informacao_web" in matched_names:
                matched_names.remove("pesquisar_informacao_web")
            matched_names.insert(0, "pesquisar_informacao_web")
            for falso_pos in ("pesquisar_google", "pesquisar_na_web", "abrir_programa", "obter_hora_data"):
                if falso_pos in matched_names:
                    matched_names.remove(falso_pos)

        _is_youtube = any(k in q_lower for k in (
            "youtube", "tocar musica", "toca musica", "ouvir musica",
            "busca video", "busque video", "buscar video", "procure video", "procurar video"
        ))
        if _is_youtube and not _is_browser_search and not _is_nav_direta:
            if "pesquisar_youtube" not in matched_names:
                matched_names.insert(0, "pesquisar_youtube")
            if "pesquisar_na_web" in matched_names and not _is_browser_search:
                matched_names.remove("pesquisar_na_web")

        _click_triggers = (
            "primeiro link", "segundo link", "terceiro link", "quarto link", "quinto link", "ultimo link",
            "primeiro resultado", "segundo resultado", "terceiro resultado",
            "primeiro video", "segundo video", "terceiro video",
            "abra o primeiro", "abra o segundo", "abra o terceiro", "abre o primeiro", "abre o segundo", "abre o terceiro",
            "abra o link", "abrir o link", "abra esse link", "abre esse link", "abre o link",
            "entre no primeiro", "entre no segundo", "entra no primeiro", "entra no segundo", "entre no link",
            "clique no", "clique na", "clique em", "clicar no", "clicar na", "clicar em",
            "clica no", "clica na", "clica em", "aperte o botao", "aperta o botao", "aperta em",
        )
        _page_nav_triggers = (
            "role para", "rolar para", "role a pagina", "rola a pagina",
            "desca a", "suba a", "ir para o topo", "va para o topo",
            "ir para o final", "fim da pagina",
            "voltar pagina", "volte a pagina", "volta a pagina",
            "pagina anterior", "avancar pagina", "avance a pagina",
            "atualize a pagina", "atualizar pagina", "recarregue a pagina", "recarrega a pagina",
            "fechar aba", "feche a aba", "fecha a aba", "listar links", "liste os links",
        )
        if _is_fechar_nav:
            if "fechar_navegador" in matched_names:
                matched_names.remove("fechar_navegador")
            matched_names.insert(0, "fechar_navegador")
        elif _is_captura_web:
            if "capturar_tela_web" in matched_names:
                matched_names.remove("capturar_tela_web")
            matched_names.insert(0, "capturar_tela_web")
        elif _is_ler_web:
            if "ler_conteudo_pagina" in matched_names:
                matched_names.remove("ler_conteudo_pagina")
            matched_names.insert(0, "ler_conteudo_pagina")
        elif _is_nav_direta:
            for ws in ("pesquisar_google", "clicar_elemento_web", "navegar_para"):
                if ws in matched_names:
                    matched_names.remove(ws)
                matched_names.insert(0, ws)
            for remover in ("abrir_programa", "pesquisar_informacao_web"):
                if remover in matched_names:
                    matched_names.remove(remover)
        elif _is_selenium_search:
            if "pesquisar_na_web" in matched_names:
                matched_names.remove("pesquisar_na_web")
            matched_names.insert(0, "pesquisar_na_web")
        elif _is_visao_clique:
            if "localizar_e_clicar_imagem" in matched_names:
                matched_names.remove("localizar_e_clicar_imagem")
            matched_names.insert(0, "localizar_e_clicar_imagem")
        elif _is_ocr_tela:
            if "ler_texto_da_tela" in matched_names:
                matched_names.remove("ler_texto_da_tela")
            matched_names.insert(0, "ler_texto_da_tela")
        elif _is_agendar:
            if "agendar_execucao" in matched_names:
                matched_names.remove("agendar_execucao")
            matched_names.insert(0, "agendar_execucao")
        elif _is_listar_agend:
            if "listar_agendamentos" in matched_names:
                matched_names.remove("listar_agendamentos")
            matched_names.insert(0, "listar_agendamentos")
        elif any(k in q_lower for k in _page_nav_triggers):
            for ws in ("clicar_elemento_web", "interagir_pagina_web"):
                if ws in matched_names:
                    matched_names.remove(ws)
                matched_names.insert(0, ws)
            for remover in ("abrir_programa", "pesquisar_informacao_web", "fechar_janela"):
                if remover in matched_names:
                    matched_names.remove(remover)
        elif any(k in q_lower for k in _click_triggers):
            for ws in ("navegar_para", "interagir_pagina_web", "clicar_elemento_web"):
                if ws in matched_names:
                    matched_names.remove(ws)
                matched_names.insert(0, ws)
            for remover in ("abrir_programa", "pesquisar_informacao_web"):
                if remover in matched_names:
                    matched_names.remove(remover)

        if _is_arquivos:
            if "gerenciar_arquivos" in matched_names:
                matched_names.remove("gerenciar_arquivos")
            matched_names.insert(0, "gerenciar_arquivos")
        _is_planilha = (
            not _is_arquivos
            and any(k in q_lower for k in ("planilha", "excel", "tabela", ".csv", "arquivo csv", "criar excel", "abrir excel", "abrir planilha"))
        )
        if _is_planilha:
            _criacao_triggers = (
                "criar planilha", "crie uma planilha", "crie planilha", "cria planilha", "cria uma planilha",
                "gerar planilha", "gere uma planilha", "fazer planilha", "faca uma planilha", "faz uma planilha",
                "monte uma planilha", "montar planilha", "monta uma planilha", "monta uma tabela", "desenvolva uma planilha",
                "nova planilha", "criar excel", "crie um excel", "cria um excel", "gerar excel", "gere um excel"
            )
            _verbos_edicao = (
                "adicion", "acrescent", "insir", "inser", "inclua", "incluir", "bota ", "coloca ", "coloque ",
                "remov", "apag", "exclu", "delet", "tire ", "tirar ",
                "edit", "alter", "atualiz", "mude", "mudar", "troque", "trocar", "substitu"
            )
            _criacao_explicita = any(k in q_lower for k in _criacao_triggers)
            _edicao = any(v in q_lower for v in _verbos_edicao)
            if not _criacao_explicita and _edicao:
                if "editar_planilha" in matched_names:
                    matched_names.remove("editar_planilha")
                matched_names.insert(0, "editar_planilha")
                for outra in ("criar_planilha", "abrir_planilha", "gerenciar_arquivos"):
                    if outra in matched_names:
                        matched_names.remove(outra)
            elif _criacao_explicita or (("planilha" in q_lower or "excel" in q_lower or "tabela" in q_lower) and any(v in q_lower for v in ("crie", "criar", "cria", "gere", "gerar", "gera", "monte", "monta", "faca", "faz", "desenvolva"))):
                if "criar_planilha" in matched_names:
                    matched_names.remove("criar_planilha")
                matched_names.insert(0, "criar_planilha")
                if "abrir_planilha" in matched_names:
                    matched_names.remove("abrir_planilha")
            elif any(k in q_lower for k in ("abrir planilha", "abrir excel", "abra o excel", "abre o excel", "abra a planilha", "abre a planilha", "ver excel", "mostrar excel", "iniciar excel")):
                if "abrir_planilha" in matched_names:
                    matched_names.remove("abrir_planilha")
                matched_names.insert(0, "abrir_planilha")
            elif any(k in q_lower for k in ("ler", "leia", "le ", "consultar", "consulte", "analisar", "analise", "analisa", "filtrar", "filtre", "filtra", "ver dados", "dados da planilha", "busca na planilha", "buscar na planilha", "quantas linhas", "resumo")):
                if "consultar_planilha" in matched_names:
                    matched_names.remove("consultar_planilha")
                matched_names.insert(0, "consultar_planilha")
            else:
                if "abrir_planilha" not in matched_names:
                    matched_names.insert(0, "abrir_planilha")
            if "abrir_programa" in matched_names:
                matched_names.remove("abrir_programa")

        _is_word = any(k in q_lower for k in ("word", ".docx", "documento word", "arquivo docx"))
        if _is_word and not _is_planilha:
            _word_criacao = any(v in q_lower for v in ("crie", "criar", "cria", "gere", "gerar", "gera", "monte", "monta", "faca", "faz", "novo documento", "escreva um documento", "escreve um documento"))
            _word_edicao = any(v in q_lower for v in ("adicion", "acrescent", "insir", "inser", "escrev", "paragrafo", "secao", "substitu", "remov", "apag", "edit", "alter"))
            _word_leitura = any(v in q_lower for v in ("ler ", "leia ", "le ", "conteudo", "o que diz", "o que esta escrito"))
            if _word_criacao and not any(k in q_lower for k in ("adicione", "adiciona", "substitua", "remova")):
                if "criar_documento_word" in matched_names:
                    matched_names.remove("criar_documento_word")
                matched_names.insert(0, "criar_documento_word")
            elif _word_edicao:
                if "editar_documento_word" in matched_names:
                    matched_names.remove("editar_documento_word")
                matched_names.insert(0, "editar_documento_word")
            elif _word_leitura:
                if "ler_documento_word" in matched_names:
                    matched_names.remove("ler_documento_word")
                matched_names.insert(0, "ler_documento_word")
            else:
                if "abrir_documento_word" in matched_names:
                    matched_names.remove("abrir_documento_word")
                matched_names.insert(0, "abrir_documento_word")
            if "abrir_programa" in matched_names:
                matched_names.remove("abrir_programa")

        if threshold > 0.35:
            try:
                from core.session_state import obter_artefato
                ativo = obter_artefato()
            except Exception:
                ativo = None
            if ativo:
                tipo_ativo = ativo.get("tipo")
                _verbos_cont = (
                    "adicion", "acrescent", "insir", "inser", "inclua", "incluir",
                    "remov", "apag", "exclu", "delet", "edit", "alter", "atualiz",
                    "mude", "mudar", "troque", "trocar", "substitu", "coloque", "colocar", "bota ",
                    "escrev", "linha", "coluna", "celula", "paragrafo", "secao", "titulo",
                )
                if tipo_ativo == "excel" and any(v in q_lower for v in _verbos_cont):
                    if "editar_planilha" in matched_names:
                        matched_names.remove("editar_planilha")
                    matched_names.insert(0, "editar_planilha")
                    if "consultar_planilha" not in matched_names:
                        matched_names.append("consultar_planilha")
                elif tipo_ativo == "word" and any(v in q_lower for v in _verbos_cont):
                    if "editar_documento_word" in matched_names:
                        matched_names.remove("editar_documento_word")
                    matched_names.insert(0, "editar_documento_word")
                    if "ler_documento_word" not in matched_names:
                        matched_names.append("ler_documento_word")
                elif (
                    tipo_ativo == "web"
                    and not _is_browser_search
                    and not _is_web_info
                    and not (_is_fechar_nav or _is_captura_web or _is_ler_web or _is_nav_direta or _is_selenium_search or _is_visao_clique or _is_ocr_tela)
                    and "abrir_programa" not in matched_names
                    and any(
                        v in q_lower for v in (
                            "cliqu", "clic", "leia", "ler ", "campo", "preench", "resultado",
                            "link", "primeiro", "segundo", "terceiro", "video",
                            "site", "pagina",
                            "role", "rolar", "rola", "desca", "descer", "suba", "subir",
                            "volta", "volte", "voltar", "avanc", "atualiz", "recarreg", "aba", "digite"
                        )
                    )
                ):
                    if any(w in q_lower for w in ("volta", "volte", "voltar", "avanc", "role", "rolar", "rola", "desca", "suba", "atualiz", "recarreg", "aba", "listar links")):
                        primaria_web = "interagir_pagina_web"
                    elif any(w in q_lower for w in ("leia", "ler ", "conteudo do site", "conteudo da pagina")):
                        primaria_web = "ler_conteudo_pagina"
                    elif any(w in q_lower for w in ("campo", "preench", "digite")):
                        primaria_web = "digitar_campo_web"
                    else:
                        primaria_web = "clicar_elemento_web"

                    for ws in ("ler_conteudo_pagina", "digitar_campo_web", "navegar_para", "interagir_pagina_web", "clicar_elemento_web"):
                        if ws not in matched_names:
                            matched_names.append(ws)
                    if primaria_web in matched_names:
                        matched_names.remove(primaria_web)
                    matched_names.insert(0, primaria_web)
                    if "abrir_programa" in matched_names and not any(
                        app in q_lower for app in ("bloco de notas", "notepad", "calculadora", "calc", "vscode", "cmd", "terminal", "spotify")
                    ):
                        matched_names.remove("abrir_programa")

        try:
            total = self.collection.count()
            if total > 0:
                n = min(max(top_k, 5), total)
                results = self.collection.query(
                    query_texts=[query],
                    n_results=n,
                    include=["metadatas", "distances"]
                )

                distances_list = results.get("distances", [[]])[0]
                metadatas_list = results.get("metadatas", [[]])[0]

                for dist, meta in zip(distances_list, metadatas_list):
                    if dist <= threshold:
                        skill_name = meta.get("name")
                        if not skill_name:
                            continue
                        if _is_browser_search and skill_name in ("pesquisar_informacao_web", "abrir_programa", "pesquisar_na_web"):
                            continue
                        if _is_web_info and skill_name in ("pesquisar_google", "pesquisar_na_web", "abrir_programa"):
                            continue
                        if skill_name not in matched_names:
                            matched_names.append(skill_name)
        except Exception as e:
            print(f"[SkillRouter] Erro na busca semântica de skills: {e}")

        matched_schemas = [
            self._schemas_by_name[name]
            for name in matched_names
            if name in self._schemas_by_name
        ]

        return matched_schemas[:top_k]

    def get_all_skills(self) -> list[dict[str, Any]]:
        """Retorna todos os esquemas cadastrados."""
        return list(ALL_SKILL_SCHEMAS)


_ROUTER_INSTANCE: SkillRouter | None = None


def get_skill_router() -> SkillRouter:
    """Retorna a instância singleton do SkillRouter."""
    global _ROUTER_INSTANCE
    if _ROUTER_INSTANCE is None:
        _ROUTER_INSTANCE = SkillRouter()
    return _ROUTER_INSTANCE
