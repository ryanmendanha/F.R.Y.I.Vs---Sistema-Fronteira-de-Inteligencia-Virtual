---
titulo: Mapa Arquitetural Completo e Grafo de Conhecimento da F.R.Y.I.Vs
categoria: arquitetura_sistema
tags: [arquitetura, mapa_mental, graphify, core, skills, server, dependencias]
---

# Mapa Arquitetural e Grafo de Conhecimento da F.R.Y.I.Vs (Graphify)

Este documento registra a anatomia completa, mapa de conexões e relações de dependência de todos os componentes da assistente F.R.Y.I.Vs, gerados e mantidos pela ferramenta de mapeamento estrutural Graphify.

## Visão Geral da Arquitetura

A F.R.Y.I.Vs é estruturada em 5 camadas modulares e desacopladas:

1. **Camada de Apresentação e Servidor (`server.py` + `ui/`):**
   - Servidor FastAPI com Uvicorn escutando na porta 8000.
   - Comunicação full-duplex em tempo real via WebSockets (`/ws`) para streaming de estados (idle, listening, thinking, speaking) e telemetria.
   - Rotas REST para execução direta de skills (`/api/skills/execute`), envio de mensagens (`/api/chat`), consulta de memórias (`/api/memory`), status dos provedores (`/api/status`), visualização do grafo (`/graph`) e árvore D3 (`/graph/tree`).

2. **Núcleo de Inteligência e Roteamento Semântico (`core/`):**
   - `core/llm.py`: Motor central de raciocínio. Orquestra Gemini Flash e Ollama (Llama 3.2), aplica roteamento semântico de skills e gerencia limites de contexto.
   - `core/gemini_client.py`: Integração direta com Google AI Studio via API v1beta com failover resiliente.
   - `core/skill_router.py`: Roteador semântico baseado em ChromaDB com métrica de cosseno HNSW e sistema híbrido com impulsão por palavras-chave (BM25-like).
   - `core/memory.py`: Memória de longo prazo episódica e conversacional com ChromaDB e Sentence-Transformers (`all-MiniLM-L6-v2`).
   - `core/knowledge_base.py`: Mecanismo RAG de base de conhecimento com chunking semântico e busca vetorial.
   - `core/vector_db.py`: Ponto único de persistência e ciclo de vida das coleções vetoriais em `./fryvis_memory`.
   - `core/stt.py`: Transcrição de fala local de alta fidelidade com Faster-Whisper.
   - `core/tts.py`: Síntese neural ultra-rápida via Edge-TTS (`pt-BR-FranciscaNeural`).

3. **Subsistema de Habilidades e Ações no Computador (`skills/`):**
   - `skills/open_app.py`: Resolução inteligente de apelidos em português e abertura de executáveis no Windows.
   - `skills/system_controls.py`: Controle de janelas, minimização, maximização, foco, volume, digitação, atalhos, printscreen e pesquisa web silenciosa.
   - `skills/web_automation.py`: Automação com Selenium em Chrome e Edge para navegação, scraping e preenchimento de formulários.
   - `skills/visual_ocr.py`: Reconhecimento visual de elementos via OpenCV e OCR via PyTesseract.
   - `skills/file_data_ops.py`: Gestão de arquivos, planilhas Excel (OpenPyXL + Pandas) e relatórios Word (python-docx).
   - `skills/scheduler_ops.py`: Agendamento de rotinas e alertas externos via webhooks.
   - `skills/code_graph_ops.py`: Consulta, navegação e explicação do próprio grafo arquitetural gerado pelo Graphify.

4. **Grafo de Conhecimento e Mapa Mental (`graphify-out/`):**
   - Mais de 2.200 nós representando funções, classes, métodos e variáveis mapeados cirurgicamente.
   - Mais de 4.200 arestas que conectam quem chama quem, herança de classes e imports de módulos.
   - Relatório de integridade e auditoria em `graphify-out/GRAPH_REPORT.md`.
   - Visualizador interativo holográfico em `graphify-out/graph.html`.

## Núcleos Centrais do Sistema (God Nodes)

Os nós de maior centralidade e gravidade estrutural na F.R.Y.I.Vs são:
- `server.py`: Ponto de entrada do backend e despachante assíncrono.
- `skills_init_execute_skill`: Despachante resiliente e seguro de ferramentas.
- `skills_init`: Barramento de registro e esquemas OpenAPI.
- `core_llm_ask_fryvis`: Decisor de inferência e acionamento de function calls.
- `core_skill_router_skillrouter`: Filtro vetorial que impede estouro de tokens no LLM.

## Como a FRYIVS Lembra de Cada Parte

Através da skill `consultar_mapa_codigo`, a FRYIVS pode a qualquer momento consultar em memória:
- O arquivo exato e número da linha de qualquer função ou classe.
- Quais componentes dependem dessa função.
- O caminho de execução entre qualquer par de módulos com `caminho_entre_componentes`.
- A reindexação incremental com `atualizar_mapa_codigo`.
