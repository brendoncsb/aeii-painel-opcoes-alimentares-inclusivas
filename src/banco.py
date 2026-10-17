from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
import tempfile
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURAÇÕES
# ============================================================

PASTA_PROJETO = Path(__file__).resolve().parent.parent
PASTA_PROCESSED = PASTA_PROJETO / "data" / "processed"
PASTA_DATABASE = PASTA_PROJETO / "data" / "database"

ARQUIVO_ESTABELECIMENTOS = (
    PASTA_PROCESSED / "estabelecimentos.csv"
)
ARQUIVO_CATEGORIAS = (
    PASTA_PROCESSED / "categorias_busca.csv"
)
ARQUIVO_RELACIONAMENTO = (
    PASTA_PROCESSED / "estabelecimento_categoria_busca.csv"
)
ARQUIVO_COLETAS = (
    PASTA_PROCESSED / "coletas.csv"
)
ARQUIVO_RELATORIO = (
    PASTA_PROCESSED / "relatorio_qualidade.json"
)

ARQUIVO_BANCO = (
    PASTA_DATABASE / "base_extensao_aeii.db"
)
# O banco temporário fica fora do OneDrive para evitar bloqueios
# de sincronização durante a criação e validação.
ARQUIVO_BANCO_TEMP = (
    Path(tempfile.gettempdir())
    / f"base_extensao_aeii_{uuid.uuid4().hex}.tmp.db"
)

# Exportações SQL úteis como evidência e apoio ao Power BI.
PASTA_EXPORTACOES_SQL = (
    PASTA_PROCESSED / "sql_exports"
)


# ============================================================
# COLUNAS ESPERADAS
# ============================================================

COLUNAS_ESTABELECIMENTOS = [
    "place_id",
    "nome",
    "idioma_nome",
    "endereco_completo",
    "cidade",
    "latitude",
    "longitude",
    "nota_media",
    "total_avaliacoes",
    "nivel_preco",
    "tipos_google",
    "tipo_vegano_google",
    "tipo_vegetariano_google",
    "fonte",
    "data_atualizacao",
]

COLUNAS_CATEGORIAS = [
    "id_categoria",
    "categoria_busca",
    "tipo_classificacao",
]

COLUNAS_RELACIONAMENTO = [
    "place_id",
    "id_categoria",
]

COLUNAS_COLETAS = [
    "id_coleta",
    "municipio_busca",
    "categoria_busca",
    "termo_busca",
    "quantidade_registros_brutos",
]


# ============================================================
# UTILITÁRIOS
# ============================================================

def verificar_arquivo(
    caminho: Path,
) -> None:
    """Interrompe a execução caso um arquivo obrigatório não exista."""

    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo obrigatório não encontrado:\n{caminho}"
        )


def validar_colunas(
    df: pd.DataFrame,
    colunas_esperadas: list[str],
    nome_arquivo: str,
) -> None:
    """Valida se todas as colunas esperadas estão presentes."""

    ausentes = [
        coluna
        for coluna in colunas_esperadas
        if coluna not in df.columns
    ]

    if ausentes:
        raise ValueError(
            f"O arquivo {nome_arquivo} não possui estas colunas: "
            + ", ".join(ausentes)
        )


def converter_booleano_sql(
    valor,
) -> int | None:
    """
    Converte valores booleanos provenientes do CSV em 0/1.
    """

    if pd.isna(valor):
        return None

    if isinstance(valor, bool):
        return int(valor)

    texto = str(valor).strip().lower()

    if texto in {
        "true",
        "1",
        "sim",
        "yes",
    }:
        return 1

    if texto in {
        "false",
        "0",
        "não",
        "nao",
        "no",
    }:
        return 0

    return None


def valor_sql(
    valor,
):
    """Converte NaN/NA do Pandas para NULL no SQLite."""

    if pd.isna(valor):
        return None

    # Converte tipos escalares do numpy/pandas para Python.
    if hasattr(valor, "item"):
        try:
            return valor.item()
        except ValueError:
            pass

    return valor


# ============================================================
# LEITURA E VALIDAÇÃO DOS ARQUIVOS
# ============================================================

def carregar_dados() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """Carrega e valida os quatro CSVs gerados pelo tratamento."""

    arquivos = [
        ARQUIVO_ESTABELECIMENTOS,
        ARQUIVO_CATEGORIAS,
        ARQUIVO_RELACIONAMENTO,
        ARQUIVO_COLETAS,
    ]

    for arquivo in arquivos:
        verificar_arquivo(arquivo)

    estabelecimentos = pd.read_csv(
        ARQUIVO_ESTABELECIMENTOS,
        encoding="utf-8-sig",
    )

    categorias = pd.read_csv(
        ARQUIVO_CATEGORIAS,
        encoding="utf-8-sig",
    )

    relacionamento = pd.read_csv(
        ARQUIVO_RELACIONAMENTO,
        encoding="utf-8-sig",
    )

    coletas = pd.read_csv(
        ARQUIVO_COLETAS,
        encoding="utf-8-sig",
    )

    validar_colunas(
        estabelecimentos,
        COLUNAS_ESTABELECIMENTOS,
        ARQUIVO_ESTABELECIMENTOS.name,
    )
    validar_colunas(
        categorias,
        COLUNAS_CATEGORIAS,
        ARQUIVO_CATEGORIAS.name,
    )
    validar_colunas(
        relacionamento,
        COLUNAS_RELACIONAMENTO,
        ARQUIVO_RELACIONAMENTO.name,
    )
    validar_colunas(
        coletas,
        COLUNAS_COLETAS,
        ARQUIVO_COLETAS.name,
    )

    # Mantém somente as colunas oficiais e na ordem definida.
    estabelecimentos = estabelecimentos[
        COLUNAS_ESTABELECIMENTOS
    ].copy()

    categorias = categorias[
        COLUNAS_CATEGORIAS
    ].copy()

    relacionamento = relacionamento[
        COLUNAS_RELACIONAMENTO
    ].copy()

    coletas = coletas[
        COLUNAS_COLETAS
    ].copy()

    return (
        estabelecimentos,
        categorias,
        relacionamento,
        coletas,
    )


# ============================================================
# ESTRUTURA DO BANCO
# ============================================================

SQL_ESTRUTURA = """
PRAGMA foreign_keys = ON;

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

CREATE TABLE categorias_busca (
    id_categoria INTEGER PRIMARY KEY,
    categoria_busca TEXT NOT NULL UNIQUE,
    tipo_classificacao TEXT NOT NULL
);

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

CREATE TABLE coletas (
    id_coleta INTEGER PRIMARY KEY,
    municipio_busca TEXT NOT NULL,
    categoria_busca TEXT NOT NULL,
    termo_busca TEXT NOT NULL,
    quantidade_registros_brutos INTEGER NOT NULL
        CHECK (quantidade_registros_brutos >= 0)
);

CREATE INDEX idx_estabelecimentos_cidade
    ON estabelecimentos(cidade);

CREATE INDEX idx_estabelecimentos_nota
    ON estabelecimentos(nota_media);

CREATE INDEX idx_estabelecimentos_avaliacoes
    ON estabelecimentos(total_avaliacoes);

CREATE INDEX idx_relacionamento_categoria
    ON estabelecimento_categoria_busca(id_categoria);

CREATE INDEX idx_relacionamento_place
    ON estabelecimento_categoria_busca(place_id);
"""


SQL_VIEWS = """
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


CREATE VIEW vw_resumo_cidade AS
SELECT
    cidade,
    COUNT(*) AS quantidade_estabelecimentos,
    ROUND(AVG(nota_media), 2) AS nota_media_geral,
    SUM(total_avaliacoes) AS total_avaliacoes
FROM estabelecimentos
GROUP BY cidade;


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
"""


# ============================================================
# CARGA DOS DADOS
# ============================================================

def inserir_estabelecimentos(
    conexao: sqlite3.Connection,
    df: pd.DataFrame,
) -> None:
    """Insere a dimensão de estabelecimentos."""

    sql = """
        INSERT INTO estabelecimentos (
            place_id,
            nome,
            idioma_nome,
            endereco_completo,
            cidade,
            latitude,
            longitude,
            nota_media,
            total_avaliacoes,
            nivel_preco,
            tipos_google,
            tipo_vegano_google,
            tipo_vegetariano_google,
            fonte,
            data_atualizacao
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """

    linhas = []

    for _, linha in df.iterrows():
        linhas.append(
            (
                valor_sql(linha["place_id"]),
                valor_sql(linha["nome"]),
                valor_sql(linha["idioma_nome"]),
                valor_sql(linha["endereco_completo"]),
                valor_sql(linha["cidade"]),
                valor_sql(linha["latitude"]),
                valor_sql(linha["longitude"]),
                valor_sql(linha["nota_media"]),
                valor_sql(linha["total_avaliacoes"]),
                valor_sql(linha["nivel_preco"]),
                valor_sql(linha["tipos_google"]),
                converter_booleano_sql(
                    linha["tipo_vegano_google"]
                ),
                converter_booleano_sql(
                    linha["tipo_vegetariano_google"]
                ),
                valor_sql(linha["fonte"]),
                valor_sql(linha["data_atualizacao"]),
            )
        )

    conexao.executemany(
        sql,
        linhas,
    )


def inserir_categorias(
    conexao: sqlite3.Connection,
    df: pd.DataFrame,
) -> None:
    """Insere as categorias de busca."""

    sql = """
        INSERT INTO categorias_busca (
            id_categoria,
            categoria_busca,
            tipo_classificacao
        )
        VALUES (?, ?, ?);
    """

    linhas = [
        (
            int(linha["id_categoria"]),
            valor_sql(linha["categoria_busca"]),
            valor_sql(linha["tipo_classificacao"]),
        )
        for _, linha in df.iterrows()
    ]

    conexao.executemany(
        sql,
        linhas,
    )


def inserir_relacionamento(
    conexao: sqlite3.Connection,
    df: pd.DataFrame,
) -> None:
    """Insere a relação N:N estabelecimento x categoria."""

    sql = """
        INSERT INTO estabelecimento_categoria_busca (
            place_id,
            id_categoria
        )
        VALUES (?, ?);
    """

    linhas = [
        (
            valor_sql(linha["place_id"]),
            int(linha["id_categoria"]),
        )
        for _, linha in df.iterrows()
    ]

    conexao.executemany(
        sql,
        linhas,
    )


def inserir_coletas(
    conexao: sqlite3.Connection,
    df: pd.DataFrame,
) -> None:
    """Insere o resumo das consultas realizadas."""

    sql = """
        INSERT INTO coletas (
            id_coleta,
            municipio_busca,
            categoria_busca,
            termo_busca,
            quantidade_registros_brutos
        )
        VALUES (?, ?, ?, ?, ?);
    """

    linhas = [
        (
            int(linha["id_coleta"]),
            valor_sql(linha["municipio_busca"]),
            valor_sql(linha["categoria_busca"]),
            valor_sql(linha["termo_busca"]),
            int(linha["quantidade_registros_brutos"]),
        )
        for _, linha in df.iterrows()
    ]

    conexao.executemany(
        sql,
        linhas,
    )


# ============================================================
# CRIAÇÃO ATÔMICA DO BANCO
# ============================================================

def criar_banco(
    estabelecimentos: pd.DataFrame,
    categorias: pd.DataFrame,
    relacionamento: pd.DataFrame,
    coletas: pd.DataFrame,
) -> None:
    """
    Cria o banco em arquivo temporário e substitui o banco final
    somente após todas as validações passarem.
    """

    PASTA_DATABASE.mkdir(
        parents=True,
        exist_ok=True,
    )

    if ARQUIVO_BANCO_TEMP.exists():
        ARQUIVO_BANCO_TEMP.unlink()

    try:
        with closing(
            sqlite3.connect(
                ARQUIVO_BANCO_TEMP
            )
        ) as conexao:

            conexao.execute(
                "PRAGMA foreign_keys = ON;"
            )

            conexao.executescript(
                SQL_ESTRUTURA
            )

            inserir_estabelecimentos(
                conexao,
                estabelecimentos,
            )

            inserir_categorias(
                conexao,
                categorias,
            )

            inserir_relacionamento(
                conexao,
                relacionamento,
            )

            inserir_coletas(
                conexao,
                coletas,
            )

            conexao.executescript(
                SQL_VIEWS
            )

            conexao.commit()

            validar_banco(
                conexao=conexao,
                estabelecimentos=estabelecimentos,
                categorias=categorias,
                relacionamento=relacionamento,
                coletas=coletas,
            )

        # Aguarda o fechamento completo do handle do SQLite.
        time.sleep(0.5)

        if ARQUIVO_BANCO.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = (
                PASTA_DATABASE
                / f"base_extensao_aeii_backup_{timestamp}.db"
            )

            shutil.copy2(
                ARQUIVO_BANCO,
                backup,
            )

        # Copia o banco validado do diretório temporário do Windows
        # para a pasta final do projeto. Isso evita tentar renomear
        # um arquivo que o OneDrive acabou de detectar.
        ultimo_erro = None

        for tentativa in range(1, 11):
            try:
                shutil.copy2(
                    ARQUIVO_BANCO_TEMP,
                    ARQUIVO_BANCO,
                )

                ultimo_erro = None
                break

            except PermissionError as erro:
                ultimo_erro = erro

                print(
                    "\nDestino temporariamente bloqueado. "
                    f"Tentativa {tentativa}/10..."
                )

                time.sleep(1.0)

        if ultimo_erro is not None:
            raise PermissionError(
                "Não foi possível copiar o banco validado para "
                "a pasta final após 10 tentativas. "
                f"Origem: {ARQUIVO_BANCO_TEMP} | "
                f"Destino: {ARQUIVO_BANCO} | "
                f"Erro original: {ultimo_erro}"
            )

        # Remove o temporário somente depois da cópia bem-sucedida.
        if ARQUIVO_BANCO_TEMP.exists():
            ARQUIVO_BANCO_TEMP.unlink()

    except Exception:
        if ARQUIVO_BANCO_TEMP.exists():
            ARQUIVO_BANCO_TEMP.unlink()

        raise


# ============================================================
# VALIDAÇÕES DO BANCO
# ============================================================

def consultar_escalar(
    conexao: sqlite3.Connection,
    sql: str,
):
    """Executa consulta que retorna somente um valor."""

    return conexao.execute(
        sql
    ).fetchone()[0]


def validar_banco(
    conexao: sqlite3.Connection,
    estabelecimentos: pd.DataFrame,
    categorias: pd.DataFrame,
    relacionamento: pd.DataFrame,
    coletas: pd.DataFrame,
) -> None:
    """Valida integridade estrutural e quantitativa do SQLite."""

    integridade = consultar_escalar(
        conexao,
        "PRAGMA integrity_check;",
    )

    if integridade != "ok":
        raise RuntimeError(
            "Falha no PRAGMA integrity_check: "
            f"{integridade}"
        )

    erros_fk = conexao.execute(
        "PRAGMA foreign_key_check;"
    ).fetchall()

    if erros_fk:
        raise RuntimeError(
            "Foram encontradas violações de chave estrangeira: "
            f"{erros_fk}"
        )

    contagens = {
        "estabelecimentos": consultar_escalar(
            conexao,
            "SELECT COUNT(*) FROM estabelecimentos;",
        ),
        "categorias": consultar_escalar(
            conexao,
            "SELECT COUNT(*) FROM categorias_busca;",
        ),
        "relacionamentos": consultar_escalar(
            conexao,
            """
            SELECT COUNT(*)
            FROM estabelecimento_categoria_busca;
            """,
        ),
        "coletas": consultar_escalar(
            conexao,
            "SELECT COUNT(*) FROM coletas;",
        ),
    }

    esperados = {
        "estabelecimentos": len(estabelecimentos),
        "categorias": len(categorias),
        "relacionamentos": len(relacionamento),
        "coletas": len(coletas),
    }

    for chave in esperados:
        if contagens[chave] != esperados[chave]:
            raise RuntimeError(
                f"Contagem divergente em {chave}: "
                f"SQLite={contagens[chave]} | "
                f"CSV={esperados[chave]}"
            )

    # Regras de negócio essenciais.
    cidades_invalidas = consultar_escalar(
        conexao,
        """
        SELECT COUNT(*)
        FROM estabelecimentos
        WHERE cidade NOT IN (
            'Curitiba',
            'São José dos Pinhais'
        );
        """,
    )

    if cidades_invalidas != 0:
        raise RuntimeError(
            "Foram encontrados estabelecimentos "
            "fora do escopo territorial."
        )

    ids_nulos = consultar_escalar(
        conexao,
        """
        SELECT COUNT(*)
        FROM estabelecimentos
        WHERE place_id IS NULL
           OR TRIM(place_id) = '';
        """,
    )

    if ids_nulos != 0:
        raise RuntimeError(
            "Foram encontrados place_id nulos/vazios."
        )


# ============================================================
# CONSULTAS DE VALIDAÇÃO E EVIDÊNCIA
# ============================================================

def imprimir_validacoes() -> None:
    """Executa consultas SQL e exibe os principais resultados."""

    with closing(
        sqlite3.connect(
            ARQUIVO_BANCO
        )
    ) as conexao:

        print("\n" + "=" * 70)
        print("VALIDAÇÃO DO BANCO SQLITE")
        print("=" * 70)

        resumo = conexao.execute(
            """
            SELECT
                COUNT(*) AS estabelecimentos,
                ROUND(AVG(nota_media), 2) AS nota_media,
                SUM(total_avaliacoes) AS total_avaliacoes
            FROM estabelecimentos;
            """
        ).fetchone()

        print(
            "\nEstabelecimentos únicos: "
            f"{resumo[0]}"
        )
        print(
            "Nota média geral: "
            f"{resumo[1]}"
        )
        print(
            "Total de avaliações: "
            f"{resumo[2]}"
        )

        print("\nEstabelecimentos por cidade:")

        for linha in conexao.execute(
            """
            SELECT
                cidade,
                COUNT(*) AS quantidade
            FROM estabelecimentos
            GROUP BY cidade
            ORDER BY cidade;
            """
        ):
            print(
                f"  {linha[0]}: {linha[1]}"
            )

        print("\nEstabelecimentos por categoria de busca:")

        for linha in conexao.execute(
            """
            SELECT
                c.categoria_busca,
                COUNT(DISTINCT ec.place_id) AS quantidade
            FROM categorias_busca AS c
            LEFT JOIN estabelecimento_categoria_busca AS ec
                ON ec.id_categoria = c.id_categoria
            GROUP BY
                c.id_categoria,
                c.categoria_busca
            ORDER BY quantidade DESC;
            """
        ):
            print(
                f"  {linha[0]}: {linha[1]}"
            )

        print("\nQuantidade de relacionamentos N:N:")

        quantidade_rel = consultar_escalar(
            conexao,
            """
            SELECT COUNT(*)
            FROM estabelecimento_categoria_busca;
            """,
        )

        print(
            f"  {quantidade_rel}"
        )

        print(
            "\nTop 5 estabelecimentos por total de avaliações:"
        )

        for numero, linha in enumerate(
            conexao.execute(
                """
                SELECT
                    nome,
                    cidade,
                    nota_media,
                    total_avaliacoes
                FROM estabelecimentos
                ORDER BY
                    total_avaliacoes DESC,
                    nota_media DESC
                LIMIT 5;
                """
            ),
            start=1,
        ):
            print(
                f"  {numero}. {linha[0]} "
                f"| {linha[1]} "
                f"| nota {linha[2]} "
                f"| {linha[3]} avaliações"
            )

        print("\nIntegridade SQLite:")

        integridade = consultar_escalar(
            conexao,
            "PRAGMA integrity_check;",
        )

        print(
            f"  integrity_check: {integridade}"
        )

        fk = conexao.execute(
            "PRAGMA foreign_key_check;"
        ).fetchall()

        print(
            "  foreign_key_check: "
            + (
                "ok"
                if not fk
                else str(fk)
            )
        )


# ============================================================
# EXPORTAÇÕES DE CONSULTAS SQL
# ============================================================

def exportar_consultas_sql() -> None:
    """
    Exporta algumas visões derivadas do SQLite para comprovação
    e eventual apoio à construção do painel.
    """

    PASTA_EXPORTACOES_SQL.mkdir(
        parents=True,
        exist_ok=True,
    )

    with closing(
        sqlite3.connect(
            ARQUIVO_BANCO
        )
    ) as conexao:

        consultas = {
            "vw_estabelecimentos_categorias.csv": (
                """
                SELECT *
                FROM vw_estabelecimentos_categorias
                ORDER BY cidade, nome, categoria_busca;
                """
            ),
            "vw_resumo_cidade.csv": (
                """
                SELECT *
                FROM vw_resumo_cidade
                ORDER BY cidade;
                """
            ),
            "vw_resumo_categoria.csv": (
                """
                SELECT *
                FROM vw_resumo_categoria
                ORDER BY quantidade_estabelecimentos DESC;
                """
            ),
            "vw_powerbi_estabelecimentos.csv": (
                """
                SELECT *
                FROM vw_powerbi_estabelecimentos
                ORDER BY cidade, nome;
                """
            ),
        }

        for nome_arquivo, sql in consultas.items():

            df = pd.read_sql_query(
                sql,
                conexao,
            )

            df.to_csv(
                PASTA_EXPORTACOES_SQL / nome_arquivo,
                index=False,
                encoding="utf-8-sig",
            )


# ============================================================
# REGISTRO DA EXECUÇÃO
# ============================================================

def salvar_relatorio_banco() -> None:
    """Salva metadados e contagens do banco em JSON."""

    with closing(
        sqlite3.connect(
            ARQUIVO_BANCO
        )
    ) as conexao:

        dados = {
            "arquivo_banco": str(
                ARQUIVO_BANCO
            ),
            "data_criacao_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "integrity_check": consultar_escalar(
                conexao,
                "PRAGMA integrity_check;",
            ),
            "quantidades": {
                "estabelecimentos": consultar_escalar(
                    conexao,
                    """
                    SELECT COUNT(*)
                    FROM estabelecimentos;
                    """,
                ),
                "categorias_busca": consultar_escalar(
                    conexao,
                    """
                    SELECT COUNT(*)
                    FROM categorias_busca;
                    """,
                ),
                "relacionamentos": consultar_escalar(
                    conexao,
                    """
                    SELECT COUNT(*)
                    FROM estabelecimento_categoria_busca;
                    """,
                ),
                "coletas": consultar_escalar(
                    conexao,
                    """
                    SELECT COUNT(*)
                    FROM coletas;
                    """,
                ),
            },
            "cidades": {
                linha[0]: linha[1]
                for linha in conexao.execute(
                    """
                    SELECT
                        cidade,
                        COUNT(*)
                    FROM estabelecimentos
                    GROUP BY cidade;
                    """
                )
            },
            "categorias": {
                linha[0]: linha[1]
                for linha in conexao.execute(
                    """
                    SELECT
                        c.categoria_busca,
                        COUNT(DISTINCT ec.place_id)
                    FROM categorias_busca AS c
                    LEFT JOIN estabelecimento_categoria_busca AS ec
                        ON ec.id_categoria = c.id_categoria
                    GROUP BY
                        c.id_categoria,
                        c.categoria_busca;
                    """
                )
            },
        }

    caminho = (
        PASTA_DATABASE
        / "relatorio_banco_sqlite.json"
    )

    with caminho.open(
        "w",
        encoding="utf-8",
    ) as arquivo:
        json.dump(
            dados,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

def main() -> None:
    """Executa criação, validação e exportação do SQLite."""

    print("=" * 70)
    print("BANCO SQLITE — ATIVIDADE EXTENSIONISTA II")
    print("=" * 70)

    try:
        (
            estabelecimentos,
            categorias,
            relacionamento,
            coletas,
        ) = carregar_dados()

        print("\nArquivos processados carregados:")
        print(
            f"  Estabelecimentos: {len(estabelecimentos)}"
        )
        print(
            f"  Categorias: {len(categorias)}"
        )
        print(
            f"  Relacionamentos: {len(relacionamento)}"
        )
        print(
            f"  Coletas: {len(coletas)}"
        )

        criar_banco(
            estabelecimentos=estabelecimentos,
            categorias=categorias,
            relacionamento=relacionamento,
            coletas=coletas,
        )

        imprimir_validacoes()

        exportar_consultas_sql()

        salvar_relatorio_banco()

        print("\n" + "=" * 70)
        print("PROCESSO CONCLUÍDO COM SUCESSO")
        print("=" * 70)

        print(
            "\nBanco criado em:\n"
            f"{ARQUIVO_BANCO}"
        )

        print(
            "\nExportações SQL em:\n"
            f"{PASTA_EXPORTACOES_SQL}"
        )

        print(
            "\nRelatório do banco em:\n"
            f"{PASTA_DATABASE / 'relatorio_banco_sqlite.json'}"
        )

    except (
        FileNotFoundError,
        ValueError,
        RuntimeError,
        sqlite3.Error,
    ) as erro:
        print("\nERRO")
        print(
            f"{type(erro).__name__}: {erro}"
        )

    except PermissionError as erro:
        print(
            "\nERRO DE PERMISSÃO.\n"
            "O arquivo final continua bloqueado pelo Windows/OneDrive.\n"
            "Feche DB Browser/Power BI e pause temporariamente a "
            "sincronização do OneDrive antes de tentar novamente.\n\n"
            f"Detalhes: {erro}"
        )

    except Exception as erro:
        print("\nERRO INESPERADO")
        print(
            f"{type(erro).__name__}: {erro}"
        )


if __name__ == "__main__":
    main()
