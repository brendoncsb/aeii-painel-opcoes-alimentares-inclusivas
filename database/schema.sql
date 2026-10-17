-- TABLE: categorias_busca
CREATE TABLE categorias_busca (
    id_categoria INTEGER PRIMARY KEY,
    categoria_busca TEXT NOT NULL UNIQUE,
    tipo_classificacao TEXT NOT NULL
);

-- TABLE: coletas
CREATE TABLE coletas (
    id_coleta INTEGER PRIMARY KEY,
    municipio_busca TEXT NOT NULL,
    categoria_busca TEXT NOT NULL,
    termo_busca TEXT NOT NULL,
    quantidade_registros_brutos INTEGER NOT NULL
        CHECK (quantidade_registros_brutos >= 0)
);

-- TABLE: estabelecimento_categoria_busca
CREATE TABLE estabelecimento_categoria_busca (
    place_id TEXT NOT NULL,
    id_categoria INTEGER NOT NULL,

    PRIMARY KEY (
        place_id,
        id_categoria
    ),

    FOREIGN KEY (place_id)
        REFERENCES estabelecimentos(place_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,

    FOREIGN KEY (id_categoria)
        REFERENCES categorias_busca(id_categoria)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

-- TABLE: estabelecimentos
CREATE TABLE estabelecimentos (
    place_id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    idioma_nome TEXT,
    endereco_completo TEXT NOT NULL,
    cidade TEXT NOT NULL
        CHECK (
            cidade IN (
                'Curitiba',
                'São José dos Pinhais'
            )
        ),
    latitude REAL NOT NULL
        CHECK (latitude BETWEEN -90 AND 90),
    longitude REAL NOT NULL
        CHECK (longitude BETWEEN -180 AND 180),
    nota_media REAL
        CHECK (
            nota_media IS NULL
            OR nota_media BETWEEN 0 AND 5
        ),
    total_avaliacoes INTEGER
        CHECK (
            total_avaliacoes IS NULL
            OR total_avaliacoes >= 0
        ),
    nivel_preco TEXT,
    tipos_google TEXT,
    tipo_vegano_google INTEGER
        CHECK (
            tipo_vegano_google IS NULL
            OR tipo_vegano_google IN (0, 1)
        ),
    tipo_vegetariano_google INTEGER
        CHECK (
            tipo_vegetariano_google IS NULL
            OR tipo_vegetariano_google IN (0, 1)
        ),
    fonte TEXT NOT NULL,
    data_atualizacao TEXT NOT NULL
);

-- VIEW: vw_estabelecimentos_categorias
CREATE VIEW vw_estabelecimentos_categorias AS
SELECT
    e.place_id,
    e.nome,
    e.endereco_completo,
    e.cidade,
    e.latitude,
    e.longitude,
    e.nota_media,
    e.total_avaliacoes,
    e.nivel_preco,
    e.tipo_vegano_google,
    e.tipo_vegetariano_google,
    c.id_categoria,
    c.categoria_busca
FROM estabelecimentos AS e
INNER JOIN estabelecimento_categoria_busca AS ec
    ON ec.place_id = e.place_id
INNER JOIN categorias_busca AS c
    ON c.id_categoria = ec.id_categoria;

-- VIEW: vw_powerbi_estabelecimentos
CREATE VIEW vw_powerbi_estabelecimentos AS
SELECT
    e.place_id,
    e.nome,
    e.endereco_completo,
    e.cidade,
    e.latitude,
    e.longitude,
    e.nota_media,
    e.total_avaliacoes,
    e.nivel_preco,
    e.tipo_vegano_google,
    e.tipo_vegetariano_google,
    GROUP_CONCAT(
        c.categoria_busca,
        ' | '
    ) AS categorias_busca
FROM estabelecimentos AS e
LEFT JOIN estabelecimento_categoria_busca AS ec
    ON ec.place_id = e.place_id
LEFT JOIN categorias_busca AS c
    ON c.id_categoria = ec.id_categoria
GROUP BY
    e.place_id,
    e.nome,
    e.endereco_completo,
    e.cidade,
    e.latitude,
    e.longitude,
    e.nota_media,
    e.total_avaliacoes,
    e.nivel_preco,
    e.tipo_vegano_google,
    e.tipo_vegetariano_google;

-- VIEW: vw_resumo_categoria
CREATE VIEW vw_resumo_categoria AS
SELECT
    c.id_categoria,
    c.categoria_busca,
    COUNT(DISTINCT ec.place_id) AS quantidade_estabelecimentos,
    ROUND(AVG(e.nota_media), 2) AS nota_media_geral,
    SUM(e.total_avaliacoes) AS total_avaliacoes
FROM categorias_busca AS c
LEFT JOIN estabelecimento_categoria_busca AS ec
    ON ec.id_categoria = c.id_categoria
LEFT JOIN estabelecimentos AS e
    ON e.place_id = ec.place_id
GROUP BY
    c.id_categoria,
    c.categoria_busca;

-- VIEW: vw_resumo_cidade
CREATE VIEW vw_resumo_cidade AS
SELECT
    cidade,
    COUNT(*) AS quantidade_estabelecimentos,
    ROUND(AVG(nota_media), 2) AS nota_media_geral,
    SUM(total_avaliacoes) AS total_avaliacoes
FROM estabelecimentos
GROUP BY cidade;

-- INDEX: idx_estabelecimentos_avaliacoes
CREATE INDEX idx_estabelecimentos_avaliacoes
    ON estabelecimentos(total_avaliacoes);

-- INDEX: idx_estabelecimentos_cidade
CREATE INDEX idx_estabelecimentos_cidade
    ON estabelecimentos(cidade);

-- INDEX: idx_estabelecimentos_nota
CREATE INDEX idx_estabelecimentos_nota
    ON estabelecimentos(nota_media);

-- INDEX: idx_relacionamento_categoria
CREATE INDEX idx_relacionamento_categoria
    ON estabelecimento_categoria_busca(id_categoria);

-- INDEX: idx_relacionamento_place
CREATE INDEX idx_relacionamento_place
    ON estabelecimento_categoria_busca(place_id);