# NeuroMCP — Crawler & Ontologia de Neurodivergência (Neo4j & UV)

Este repositório contém uma solução completa para buscar, extrair, classificar e armazenar informações sobre neurodivergência (artigos científicos, artigos em blogs, fóruns e websites) em um banco de dados em grafo **Neo4j** local utilizando **Docker Compose** e **`uv`** (gerenciador moderno de pacotes Python).

---

## 🎯 Arquitetura da Solução

1. **Ontologia JSON (`ontologia/ontologia_neurodivergencia.json`)**:
   - Serve de schema mestre para a classificação semântica de conceitos (ex.: TDAH, TEA, Dislexia, Discalculia, Tourette, etc.), categorias taxonômicas, domínios cognitivos afetados (funções executivas, atenção, processamento sensorial) e relacionamentos (comorbidades, diagnósticos diferenciais).
   - Define as regras exatas de pontuação ponderada de match (`crawler.estrategiaDeMatch`) e sinais de contexto (clínico, educacional, identidade).

2. **Google Dorks e Pesquisa Otimizada (`crawler/search.py`)**:
   - Constrói dorks de busca avançados otimizados para cada tipo de fonte:
     - **Artigos Científicos**: `site:ncbi.nlm.nih.gov/pmc`, `site:scielo.br`, `site:pubmed.ncbi.nlm.nih.gov`, `site:arxiv.org`, `filetype:pdf`.
     - **Blogs**: `site:medium.com`, `site:wordpress.com`, `inurl:blog`.
     - **Fóruns**: `site:reddit.com/r/autism`, `site:reddit.com/r/ADHD`, `site:quora.com`, `inurl:forum`.
     - **Websites**: `site:abda.org.br`, `site:org.br`, `site:gov.br`.

3. **Raspador e Extrator de Páginas Web (`crawler/fetcher.py`)**:
   - Leitor HTTP assíncrono com extração limpa de conteúdo via `Trafilatura` (`bare_extraction`) e `BeautifulSoup4`.
   - Limpeza automática de scripts, navegações e propagandas, preservando títulos, autores, texto completo e resumos.

4. **Classificador Ponderado de Ontologia (`crawler/classifier.py`)**:
   - Normaliza o texto (remoção de acentos via `unidecode`, caixas baixas, colapso de espaços).
   - Avalia siglas (1.0), rótulo em português (0.9), sinônimos (0.8), palavras-chave (0.7), hashtags (0.6) e grafias comuns (0.5).
   - Aplica o limite de confiança mínima ($\ge 0.6$) e extrai trechos de evidência textual.

5. **Armazenamento no Neo4j (`crawler/database.py`)**:
   - Semeia todos os nódulos da ontologia (`:Conceito`, `:Categoria`, `:DominioCognitivo`, `:Codigo`) e relacionamentos (`:IS_A`, `:SUBTYPE_OF`, `:IN_CATEGORY`, `:AFFECTS_DOMAIN`, `:COMORBID_WITH`, `:DIFFERENTIAL_DX`, `:CODED_AS`).
   - Insere páginas e artigos como nós `(:Artigo)` vinculados à `(:Fonte)` via `:PUBLICADO_EM` e conectados aos nós da ontologia via `:MENCIONA` (com propriedades de confiança e trechos de evidência) e `:RELACIONADO_A_DOMINIO`.

---

## 🚀 Como Executar

### 1. Iniciar o Banco de Dados Neo4j via Docker Compose

```bash
docker compose up -d
```

- **Interface Web do Neo4j Browser**: `http://localhost:7474`
- **Protocolo Bolt**: `bolt://localhost:7687`
- **Usuário Padrão**: `neo4j`
- **Senha Padrão**: `neurodivergencia123`

### 2. Sincronizar Dependências com `uv`

```bash
uv sync
```

### 3. Executar o Crawler

#### Semear a Ontologia JSON no Neo4j:
```bash
uv run crawler --seed-ontology
```

#### Executar Crawling Completo (Pesquisa Otimizada + Raspagem + Gravação Neo4j):
```bash
uv run crawler --crawl --max-results 5
```

#### Executar Processo Completo (Semeadura + Crawling):
```bash
uv run crawler --full
```

#### Fazer uma Busca Específica por Termo/Dork:
```bash
uv run crawler --query "autismo feminino diagnostico" --sources artigo_cientifico blog
```

---

## 🔍 Consultas de Exemplo no Neo4j (Cypher)

Acesse `http://localhost:7474` e execute no Cypher Console:

### 1. Ver todos os Artigos Científicos que mencionam TDAH ou TEA e suas evidências
```cypher
MATCH (a:Artigo)-[r:MENCIONA]->(c:Conceito)
WHERE c.id IN ['nd:tdah', 'nd:tea']
RETURN a.titulo, a.url, c.rotuloPt, r.confianca, r.trechosEvidencia
ORDER BY r.confianca DESC
```

### 2. Navegar no Grafo Completo de Artigos, Fontes e Conceitos
```cypher
MATCH p=(a:Artigo)-[:MENCIONA]->(c:Conceito)-[:AFFECTS_DOMAIN]->(d:DominioCognitivo)
RETURN p LIMIT 25
```

### 3. Listar Fontes Mais Frequentes por Categoria de Conceito
```cypher
MATCH (a:Artigo)-[:PUBLICADO_EM]->(f:Fonte), (a)-[:MENCIONA]->(c:Conceito)-[:IN_CATEGORY]->(cat:Categoria)
RETURN cat.rotuloPt AS Categoria, f.dominio AS Fonte, count(a) AS QtdArtigos
ORDER BY QtdArtigos DESC
```

---

## 🛠️ Detalhamento Tecnológico do Crawler

Abaixo encontra-se a explicação detalhada da arquitetura, das escolhas tecnológicas e dos módulos que compõem este crawler de nível sênior:

### 🛠️ Stack de Tecnologias

- **`uv` (Astral)**: Gerenciador de pacotes e ambientes Python de altíssima performance construído em Rust. Substitui `pip`, `virtualenv` e `poetry` garantindo instalações ultra-rápidas e reprodutibilidade perfeita através do `pyproject.toml`.
- **`httpx`**: Cliente HTTP assíncrono moderno com suporte a HTTP/2, pooling de conexões, retentativas e tratamento resiliente de SSL para raspagem web em massa.
- **`trafilatura` & `beautifulsoup4`**: Combinado de ponta para extração estruturada de conteúdo web (`trafilatura.bare_extraction`). Remove ruídos de navegação, sidebars, footers e propagandas, extraindo apenas o artigo limpo, título e metadados. Fallback em `lxml`/BeautifulSoup4.
- **`pydantic` v2**: Validação rigorosa de schemas de dados Python, garantindo tipagem forte em toda a esteira do crawler.
- **`duckduckgo-search`**: Motor de busca automatizado responsável por resolver as pesquisas dork sem necessidade de chaves de API pagas ou bloqueios de IP agressivos.
- **`unidecode`**: Algoritmo de normalização textual para remoção de acentos diacríticos e alinhamento com a estratégia de correspondência da ontologia.
- **`neo4j` (Python Driver 5.x)**: Driver oficial Bolt para manipulação transacional e persistência no banco de dados em grafo Neo4j.
- **`rich`**: Interface em linha de comando (CLI) elegante com tabelas coloridas, relatórios detalhados de progresso e métricas de execução.

---

### 🧩 Estrutura dos Módulos do Crawler

| Módulo | Função & Responsabilidade |
| :--- | :--- |
| **`crawler/config.py`** | Centraliza configurações de ambiente (URLs do Neo4j, timeouts, User-Agent, limites de concorrência). |
| **`crawler/models.py`** | Define as classes Pydantic (`Concept`, `Category`, `CognitiveDomain`, `CrawledArticle`, `MatchEvidence`, `SourceType`). |
| **`crawler/ontology.py`** | Parser que lê e indexa o arquivo `ontologia_neurodivergencia.json`, oferecendo métodos de busca por palavras-chave e normalização. |
| **`crawler/search.py`** | Motor gerador de **Dorks do Google** (`SearchDorkBuilder`) que constrói operadores como `site:`, `inurl:`, `filetype:pdf` e termos booleanos para cada tipo de fonte. |
| **`crawler/fetcher.py`** | Cliente assíncrono que realiza requisições HTTP, extrai o texto principal com Trafilatura/BS4 e constrói o objeto `CrawledArticle`. |
| **`crawler/classifier.py`** | Classificador que calcula a pontuação ponderada de correspondência com a ontologia ($\text{score} \ge 0.6$), identifica sinais de contexto e captura trechos de evidência. |
| **`crawler/database.py`** | Repositório Neo4j responsável pelas restrições de unicidade, importação da ontologia JSON (nós e arestas) e gravação dos artigos coletados. |
| **`crawler/pipeline.py`** | Pipeline orquestrador que conecta a descoberta de URLs, raspagem, classificação e persistência assíncrona. |
| **`crawler/cli.py`** | Ponto de entrada CLI (`uv run crawler`), permitindo parâmetros como `--seed-ontology`, `--crawl`, `--full`, `--query` e `--sources`. |
