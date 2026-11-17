# Base de Conhecimento da F.R.Y.I.Vs

Organização (cada pasta = um tipo de recurso):

```
base_conhecimento/
├── habilidades/          # Skills: "como fazer" (procedimentos, boas práticas)
│   └── excel_avancado/   # Habilidade 01 — 11 arquivos, 72 chunks indexados
├── informacoes/          # Fatos, dados, documentos de domínio
├── templates/            # Modelos reutilizáveis (estruturas, prompts, planilhas)
├── referencias/          # Glossários, tabelas de consulta rápida
└── ferramentas/          # Scripts de ingestão standalone (uso avançado)
```

## Integração nativa com a FRYIVS

A base de conhecimento está integrada diretamente ao `core/knowledge_base.py`.
**A indexação acontece automaticamente** quando a FRYIVS inicia — sem precisar
rodar scripts separados ou ter o Ollama instalado para embeddings.

Durante o chat (texto e voz), a FRYIVS busca automaticamente trechos relevantes
da base e os injeta no contexto do LLM antes de responder.

### APIs disponíveis no servidor:
| Endpoint | Descrição |
|---|---|
| `GET /api/knowledge/status` | Estado da coleção (chunks indexados) |
| `POST /api/knowledge/reindex` | Re-indexa a base (parâmetro `reset=true` para apagar tudo) |
| `GET /api/knowledge/search?q=...` | Busca manual na base |

## Padrão de cada arquivo .md
- Bloco de metadados YAML `---` no topo (opcional).
- Cada seção `## Título` é **autossuficiente** (vira um chunk no ChromaDB).
- Nomes numerados (`00_`, `01_`...) mantêm a ordem lógica.

## Como adicionar uma nova habilidade
1. Crie `habilidades/nome_da_habilidade/`.
2. Crie `00_visao_geral.md` + arquivos numerados por tema.
3. Reinicie a FRYIVS — a indexação é automática.
   Ou chame `POST /api/knowledge/reindex` sem reiniciar.


## Uso rápido
```bash
pip install -r ferramentas/requirements.txt
ollama pull llama3.2
ollama pull nomic-embed-text
python ferramentas/ingestao_chroma.py
python ferramentas/consultar.py "Como criar um dashboard profissional no Excel?"
```
