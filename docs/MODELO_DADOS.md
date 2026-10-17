# Modelo de dados

O projeto adota uma estrutura relacional simples para evitar duplicação de estabelecimentos e representar corretamente a relação muitos-para-muitos entre estabelecimentos e categorias de busca.

## Tabelas

### `estabelecimentos`

Uma linha por `place_id`, com nome, endereço, município, latitude, longitude, nota média, total de avaliações, faixa de preço, tipos retornados pela API, fonte e data de atualização.

### `categorias_busca`

Tabela de domínio com quatro categorias utilizadas na coleta:

1. Vegetariano
2. Vegano
3. Sem glúten
4. Sem lactose

### `estabelecimento_categoria_busca`

Tabela associativa que conecta `place_id` a `id_categoria`. Um estabelecimento pode ser encontrado por mais de um termo de busca.

### `coletas`

Registra as oito consultas planejadas e executadas, preservando município, categoria, termo pesquisado e quantidade de registros brutos.

## Views SQLite

O script `src/banco.py` cria as seguintes views analíticas:

- `vw_estabelecimentos_categorias`
- `vw_powerbi_estabelecimentos`
- `vw_resumo_categoria`
- `vw_resumo_cidade`

O DDL completo está disponível em [`../database/schema.sql`](../database/schema.sql).

## Qualidade

A consolidação final resultou em 200 estabelecimentos únicos dentro do escopo territorial. Não foram identificadas notas fora do intervalo 0–5, avaliações negativas, latitudes inválidas ou longitudes inválidas. O campo `nivel_preco` apresentou ausência em parte dos registros e foi tratado como informação opcional.
