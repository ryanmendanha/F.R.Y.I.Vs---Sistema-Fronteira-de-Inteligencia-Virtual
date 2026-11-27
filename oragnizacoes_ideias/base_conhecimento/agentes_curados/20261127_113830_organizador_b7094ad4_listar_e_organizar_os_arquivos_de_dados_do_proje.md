---
titulo: Listar e organizar os arquivos de dados do projeto de forma estruturada.
habilidade: agente_organizador
tags: organizador, curado_usuario
agente: organizador
job_id: b7094ad4-8ccc-4f29-8dba-e890422b5d29
trust_level: verified_internal
curado_em: 2026-11-27T11:38:30.034336+00:00
---

# Listar e organizar os arquivos de dados do projeto de forma estruturada.

## Missao Original
Listar e organizar os arquivos de dados do projeto de forma estruturada.

## Sintese Curada
# Relatório de Organização e Estruturação de Dados do Projeto F.R.Y.I.Vs
Como **Agente Especialista Organizador de Dados** da F.R.Y.I.Vs, realizei o levantamento e a análise da estrutura de diretórios e arquivos do projeto, com foco especial na pasta de dados (`data`).
Abaixo apresento o relatório detalhado com a auditoria dos arquivos encontrados e as recomendações para a manutenção de uma arquitetura limpa, segura e escalável.
---
## 1. Visão Geral da Estrutura Raiz
O diretório principal do projeto contém uma mistura de arquivos de configuração do ambiente, pastas de controle de versão, módulos principais (`core`, `infra`, `models`), scripts de inicialização (`main.py`, `iniciar_fryivs.bat`) e diretórios dedicados a dados, documentação e testes.
### Principais Componentes Identificados:
* **Configuração e Ambiente:** `.env`, `.env.example`, `.gitignore`, `.gitattributes`, `.graphifyignore`.
* **Ambiente de Desenvolvimento & IDE:** `.vscode`, `.pytest_cache`, `.agents`.
* **Módulos do Sistema:** `core`, `infra`, `models`, `awesome_skills`, `bench`.
* **Armazenamento e Memória:** `data`, `fryvis_memory`, `GPTCache`, `audio_cache`.
* **Documentação e Organização:** `docs`, `oragnizacoes_ideias`, `FRYIVS_TESTES`, `graphify-out`.
---
## 2. Auditoria e Análise da Pasta `data`
A pasta `data` atua como o repositório central para logs de auditoria, bases de dados SQLite, cache de respostas e arquivos de estado do sistema. Abaixo está o mapeamento dos arquivos encontrados:
| Arquivo / Banco | Tipo | Função / Descrição Estimada | Status / Recomendação |
| :--- | :--- | :--- | :--- |
| `audit_log.jsonl` | Log (JSON Lines) | Registro de auditoria de eventos e ações do sistema. | **Monitorar tamanho** (pode crescer rapidamente). |
| `gptcache_fryivs.db` | SQLite Database | Banco de dados dedicado ao cache do GPTCache. | **Manter** em `data/` (essencial para performance). |
| `gptcache_map.txt` | Texto | Mapeamento ou índices auxiliares do cache. | **Manter** sincronizado com a base SQLite. |
| `kb_manifest.json` | JSON | Manifesto da Base de Conhecimento (*Knowledge Base*). | **Manter** (crítico para indexação). |
| `overlay_state.json` | JSON | Estado atual de camadas ou interfaces dinâmicas. | **Manter** (estado de sessão/UI). |
| `respostas_cache.json` | JSON | Cache local de respostas frequentes. | **Limpeza periódica** recomendada se houver obsolescência. |
| `scheduled_jobs.json` | JSON | Tarefas e rotinas agendadas no sistema. | **Manter** (
