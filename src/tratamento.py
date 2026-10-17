from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================
# CONFIGURAÇÕES
# ============================================================

PASTA_PROJETO = Path(__file__).resolve().parent.parent
PASTA_RAW = PASTA_PROJETO / "data" / "raw"
PASTA_PROCESSED = PASTA_PROJETO / "data" / "processed"

PADRAO_RAW = "google_places_raw_*.json"

CIDADES_ESCOPO = {
    "Curitiba",
    "São José dos Pinhais",
}

CATEGORIAS = {
    "Vegetariano": 1,
    "Vegano": 2,
    "Sem glúten": 3,
    "Sem lactose": 4,
}

ARQUIVO_ESTABELECIMENTOS = (
    PASTA_PROCESSED / "estabelecimentos.csv"
)
ARQUIVO_CATEGORIAS = (
    PASTA_PROCESSED / "categorias_busca.csv"
)
ARQUIVO_RELACIONAMENTO = (
    PASTA_PROCESSED
    / "estabelecimento_categoria_busca.csv"
)
ARQUIVO_COLETAS = (
    PASTA_PROCESSED / "coletas.csv"
)
ARQUIVO_QUALIDADE = (
    PASTA_PROCESSED / "relatorio_qualidade.json"
)
ARQUIVO_EXCEL = (
    PASTA_PROCESSED / "base_tratada_aeii.xlsx"
)


# ============================================================
# LOCALIZAÇÃO DO RAW
# ============================================================

def localizar_raw_mais_recente() -> Path:
    """
    Localiza o arquivo RAW mais recente da coleta.
    """

    arquivos = sorted(
        PASTA_RAW.glob(PADRAO_RAW),
        key=lambda caminho: caminho.stat().st_mtime,
        reverse=True,
    )

    if not arquivos:
        raise FileNotFoundError(
            "Nenhum arquivo RAW foi encontrado em:\n"
            f"{PASTA_RAW}\n\n"
            f"Padrão esperado: {PADRAO_RAW}"
        )

    return arquivos[0]


def carregar_json(caminho: Path) -> dict[str, Any]:
    """
    Carrega o JSON RAW sem alterar seu conteúdo.
    """

    with caminho.open(
        "r",
        encoding="utf-8",
    ) as arquivo:
        dados = json.load(arquivo)

    if dados.get("quantidade_registros_brutos", 0) <= 0:
        raise ValueError(
            "O arquivo RAW informado não possui registros válidos."
        )

    consultas = dados.get("consultas")

    if not isinstance(consultas, list) or not consultas:
        raise ValueError(
            "O JSON RAW não possui consultas válidas."
        )

    return dados


# ============================================================
# EXTRAÇÃO E NORMALIZAÇÃO
# ============================================================

def extrair_nome(
    display_name: Any,
) -> tuple[str | None, str | None]:
    """
    Extrai texto e idioma do campo displayName.
    """

    if isinstance(display_name, dict):
        return (
            display_name.get("text"),
            display_name.get("languageCode"),
        )

    if isinstance(display_name, str):
        return display_name, None

    return None, None


def extrair_cidade_endereco(
    endereco: Any,
) -> str | None:
    """
    Extrai a cidade a partir do endereço formatado retornado
    pela API.

    Exemplo:
    "... Curitiba - PR, 80000-000" -> "Curitiba"
    """

    if not isinstance(endereco, str):
        return None

    padrao = (
        r",\s*([^,]+?)\s*-\s*PR"
        r"(?:,\s*\d{5}-?\d{3})?\s*$"
    )

    correspondencia = re.search(
        padrao,
        endereco.strip(),
        flags=re.IGNORECASE,
    )

    if not correspondencia:
        return None

    return correspondencia.group(1).strip()


def normalizar_texto(
    valor: Any,
) -> str | None:
    """
    Remove espaços excedentes de campos textuais.
    """

    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    return re.sub(r"\s+", " ", texto)


def montar_ocorrencias(
    dados: dict[str, Any],
) -> pd.DataFrame:
    """
    Transforma as ocorrências do JSON em uma tabela tabular.

    Cada linha representa a ocorrência de um estabelecimento
    em uma consulta/categoria de busca.
    """

    linhas: list[dict[str, Any]] = []

    for consulta in dados.get("consultas", []):
        for registro in consulta.get("registros", []):
            api = registro.get("dados_api", {})

            nome, idioma_nome = extrair_nome(
                api.get("displayName")
            )

            localizacao = api.get("location") or {}
            tipos = api.get("types") or []

            endereco = normalizar_texto(
                api.get("formattedAddress")
            )

            linha = {
                "place_id": normalizar_texto(
                    api.get("id")
                ),
                "nome": normalizar_texto(nome),
                "idioma_nome": normalizar_texto(
                    idioma_nome
                ),
                "endereco_completo": endereco,
                "cidade_endereco": extrair_cidade_endereco(
                    endereco
                ),
                "latitude": localizacao.get("latitude"),
                "longitude": localizacao.get("longitude"),
                "nota_media": api.get("rating"),
                "total_avaliacoes": api.get(
                    "userRatingCount"
                ),
                "nivel_preco": normalizar_texto(
                    api.get("priceLevel")
                ),
                "tipos_google": "|".join(
                    sorted(
                        str(tipo)
                        for tipo in tipos
                    )
                ),
                "tipo_vegano_google": int(
                    "vegan_restaurant" in tipos
                ),
                "tipo_vegetariano_google": int(
                    "vegetarian_restaurant" in tipos
                ),
                "municipio_busca": normalizar_texto(
                    registro.get("municipio_busca")
                ),
                "categoria_busca": normalizar_texto(
                    registro.get("categoria_busca")
                ),
                "termo_busca": normalizar_texto(
                    registro.get("termo_busca")
                ),
                "fonte": normalizar_texto(
                    registro.get("fonte")
                ),
                "data_coleta": registro.get("data_coleta"),
                "pagina": registro.get("pagina"),
            }

            linhas.append(linha)

    df = pd.DataFrame(linhas)

    if df.empty:
        raise ValueError(
            "Nenhuma ocorrência pôde ser extraída do RAW."
        )

    return df


# ============================================================
# CONVERSÃO DE TIPOS E VALIDAÇÕES
# ============================================================

def converter_tipos(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Converte campos numéricos e temporais para tipos adequados.
    """

    df = df.copy()

    df["nota_media"] = pd.to_numeric(
        df["nota_media"],
        errors="coerce",
    )

    df["total_avaliacoes"] = pd.to_numeric(
        df["total_avaliacoes"],
        errors="coerce",
    ).astype("Int64")

    df["latitude"] = pd.to_numeric(
        df["latitude"],
        errors="coerce",
    )

    df["longitude"] = pd.to_numeric(
        df["longitude"],
        errors="coerce",
    )

    df["pagina"] = pd.to_numeric(
        df["pagina"],
        errors="coerce",
    ).astype("Int64")

    df["data_coleta"] = pd.to_datetime(
        df["data_coleta"],
        errors="coerce",
        utc=True,
    )

    return df


def validar_ocorrencias(
    df: pd.DataFrame,
) -> list[str]:
    """
    Executa validações estruturais e retorna avisos.
    """

    avisos: list[str] = []

    if df["place_id"].isna().any():
        avisos.append(
            "Há ocorrências sem place_id."
        )

    if df["nome"].isna().any():
        avisos.append(
            "Há ocorrências sem nome."
        )

    notas_invalidas = df[
        df["nota_media"].notna()
        & ~df["nota_media"].between(0, 5)
    ]

    if not notas_invalidas.empty:
        avisos.append(
            "Há notas fora da faixa de 0 a 5."
        )

    avaliacoes_invalidas = df[
        df["total_avaliacoes"].notna()
        & (df["total_avaliacoes"] < 0)
    ]

    if not avaliacoes_invalidas.empty:
        avisos.append(
            "Há totais de avaliações negativos."
        )

    latitudes_invalidas = df[
        df["latitude"].notna()
        & ~df["latitude"].between(-90, 90)
    ]

    if not latitudes_invalidas.empty:
        avisos.append(
            "Há latitudes fora da faixa válida."
        )

    longitudes_invalidas = df[
        df["longitude"].notna()
        & ~df["longitude"].between(-180, 180)
    ]

    if not longitudes_invalidas.empty:
        avisos.append(
            "Há longitudes fora da faixa válida."
        )

    return avisos


# ============================================================
# ESCOPO TERRITORIAL
# ============================================================

def separar_escopo(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Mantém no conjunto principal apenas Curitiba e
    São José dos Pinhais.

    A validação usa a cidade extraída do endereço retornado
    pela API, não apenas o município usado no termo de busca.
    """

    mascara = df["cidade_endereco"].isin(
        CIDADES_ESCOPO
    )

    dentro = df.loc[mascara].copy()
    fora = df.loc[~mascara].copy()

    return dentro, fora


# ============================================================
# TABELA DE ESTABELECIMENTOS
# ============================================================

def criar_estabelecimentos(
    ocorrencias_escopo: pd.DataFrame,
) -> pd.DataFrame:
    """
    Cria uma linha única por place_id.
    """

    # Confere se o mesmo place_id veio com metadados divergentes.
    campos_estaveis = [
        "nome",
        "endereco_completo",
        "cidade_endereco",
        "latitude",
        "longitude",
        "nota_media",
        "total_avaliacoes",
        "nivel_preco",
        "tipos_google",
    ]

    divergencias: list[str] = []

    for campo in campos_estaveis:
        contagem = (
            ocorrencias_escopo
            .groupby("place_id")[campo]
            .nunique(dropna=False)
        )

        quantidade = int(
            (contagem > 1).sum()
        )

        if quantidade:
            divergencias.append(
                f"{campo}: {quantidade} place_id(s)"
            )

    if divergencias:
        print(
            "\nAVISO: foram encontradas divergências "
            "entre ocorrências repetidas:"
        )

        for item in divergencias:
            print(f"  - {item}")

    ordenado = ocorrencias_escopo.sort_values(
        by=[
            "place_id",
            "data_coleta",
            "pagina",
        ],
        ascending=[
            True,
            False,
            True,
        ],
    )

    estabelecimentos = (
        ordenado
        .drop_duplicates(
            subset=["place_id"],
            keep="first",
        )
        .copy()
    )

    colunas = [
        "place_id",
        "nome",
        "idioma_nome",
        "endereco_completo",
        "cidade_endereco",
        "latitude",
        "longitude",
        "nota_media",
        "total_avaliacoes",
        "nivel_preco",
        "tipos_google",
        "tipo_vegano_google",
        "tipo_vegetariano_google",
        "fonte",
        "data_coleta",
    ]

    estabelecimentos = estabelecimentos[
        colunas
    ].copy()

    estabelecimentos = estabelecimentos.rename(
        columns={
            "cidade_endereco": "cidade",
            "data_coleta": "data_atualizacao",
        }
    )

    estabelecimentos = estabelecimentos.sort_values(
        by=[
            "cidade",
            "nome",
        ],
        na_position="last",
    ).reset_index(drop=True)

    return estabelecimentos


# ============================================================
# CATEGORIAS E RELACIONAMENTO N:N
# ============================================================

def criar_categorias() -> pd.DataFrame:
    """
    Cria a dimensão das categorias de busca.

    Atenção:
    categoria de busca não equivale a certificação do
    estabelecimento. Ela registra em qual consulta da API o
    estabelecimento apareceu.
    """

    linhas = [
        {
            "id_categoria": id_categoria,
            "categoria_busca": nome,
            "tipo_classificacao": (
                "Categoria de busca"
            ),
        }
        for nome, id_categoria in CATEGORIAS.items()
    ]

    return pd.DataFrame(linhas).sort_values(
        "id_categoria"
    ).reset_index(drop=True)


def criar_relacionamento(
    ocorrencias_escopo: pd.DataFrame,
    categorias: pd.DataFrame,
) -> pd.DataFrame:
    """
    Cria o relacionamento N:N entre estabelecimento e
    categoria de busca.
    """

    rel = (
        ocorrencias_escopo[
            [
                "place_id",
                "categoria_busca",
            ]
        ]
        .dropna()
        .drop_duplicates()
        .copy()
    )

    rel = rel.merge(
        categorias[
            [
                "id_categoria",
                "categoria_busca",
            ]
        ],
        on="categoria_busca",
        how="left",
        validate="many_to_one",
    )

    categorias_sem_id = rel[
        rel["id_categoria"].isna()
    ]["categoria_busca"].unique()

    if len(categorias_sem_id):
        raise ValueError(
            "Foram encontradas categorias sem mapeamento: "
            + ", ".join(
                str(item)
                for item in categorias_sem_id
            )
        )

    rel["id_categoria"] = rel[
        "id_categoria"
    ].astype(int)

    rel = rel[
        [
            "place_id",
            "id_categoria",
        ]
    ].sort_values(
        [
            "place_id",
            "id_categoria",
        ]
    ).reset_index(drop=True)

    return rel


# ============================================================
# TABELA DE COLETAS
# ============================================================

def criar_coletas(
    dados: dict[str, Any],
) -> pd.DataFrame:
    """
    Resume cada consulta executada.
    """

    linhas = []

    for numero, consulta in enumerate(
        dados.get("consultas", []),
        start=1,
    ):
        linhas.append(
            {
                "id_coleta": numero,
                "municipio_busca": consulta.get(
                    "municipio"
                ),
                "categoria_busca": consulta.get(
                    "categoria"
                ),
                "termo_busca": consulta.get(
                    "termo"
                ),
                "quantidade_registros_brutos": (
                    consulta.get(
                        "quantidade_registros",
                        0,
                    )
                ),
            }
        )

    return pd.DataFrame(linhas)


# ============================================================
# RELATÓRIO DE QUALIDADE
# ============================================================

def contagem_dict(
    serie: pd.Series,
) -> dict[str, int]:
    """
    Converte value_counts em dict serializável.
    """

    contagem = serie.value_counts(
        dropna=False
    )

    resultado: dict[str, int] = {}

    for chave, valor in contagem.items():
        nome = (
            "NULL"
            if pd.isna(chave)
            else str(chave)
        )

        resultado[nome] = int(valor)

    return resultado


def gerar_relatorio_qualidade(
    dados: dict[str, Any],
    ocorrencias: pd.DataFrame,
    ocorrencias_escopo: pd.DataFrame,
    ocorrencias_fora: pd.DataFrame,
    estabelecimentos: pd.DataFrame,
    relacionamento: pd.DataFrame,
    categorias: pd.DataFrame,
    avisos: list[str],
    arquivo_raw: Path,
) -> dict[str, Any]:
    """
    Gera métricas de qualidade e rastreabilidade.
    """

    place_ids_unicos_raw = int(
        ocorrencias["place_id"].nunique(
            dropna=True
        )
    )

    place_ids_unicos_escopo = int(
        ocorrencias_escopo[
            "place_id"
        ].nunique(dropna=True)
    )

    duplicidades_ocorrencia = int(
        len(ocorrencias)
        - place_ids_unicos_raw
    )

    fora_unicos = int(
        ocorrencias_fora[
            "place_id"
        ].nunique(dropna=True)
    )

    # Quantas categorias cada estabelecimento possui.
    categoria_por_estabelecimento = (
        relacionamento
        .groupby("place_id")[
            "id_categoria"
        ]
        .nunique()
    )

    distribuicao_num_categorias = {
        str(int(numero_categorias)): int(
            quantidade
        )
        for numero_categorias, quantidade
        in categoria_por_estabelecimento
        .value_counts()
        .sort_index()
        .items()
    }

    rel_com_nome = relacionamento.merge(
        categorias,
        on="id_categoria",
        how="left",
    )

    relatorio = {
        "arquivo_raw": arquivo_raw.name,
        "fonte": dados.get("fonte"),
        "inicio_coleta": dados.get(
            "inicio_coleta"
        ),
        "fim_coleta": dados.get(
            "fim_coleta"
        ),
        "consultas_planejadas": dados.get(
            "quantidade_consultas_planejadas"
        ),
        "consultas_concluidas": dados.get(
            "quantidade_consultas_concluidas"
        ),
        "consultas_com_erro": dados.get(
            "quantidade_consultas_com_erro"
        ),
        "registros_brutos": int(
            len(ocorrencias)
        ),
        "place_ids_unicos_no_raw": (
            place_ids_unicos_raw
        ),
        "ocorrencias_repetidas_por_place_id": (
            duplicidades_ocorrencia
        ),
        "registros_brutos_dentro_escopo": int(
            len(ocorrencias_escopo)
        ),
        "estabelecimentos_unicos_dentro_escopo": (
            place_ids_unicos_escopo
        ),
        "registros_brutos_fora_escopo": int(
            len(ocorrencias_fora)
        ),
        "estabelecimentos_unicos_fora_escopo": (
            fora_unicos
        ),
        "cidades_fora_escopo": contagem_dict(
            ocorrencias_fora[
                "cidade_endereco"
            ]
        ) if not ocorrencias_fora.empty else {},
        "estabelecimentos_por_cidade": (
            contagem_dict(
                estabelecimentos["cidade"]
            )
        ),
        "relacionamentos_categoria": int(
            len(relacionamento)
        ),
        "relacionamentos_por_categoria": (
            contagem_dict(
                rel_com_nome[
                    "categoria_busca"
                ]
            )
        ),
        "quantidade_de_categorias_por_estabelecimento": (
            distribuicao_num_categorias
        ),
        "campos_ausentes_estabelecimentos": {
            coluna: int(
                estabelecimentos[
                    coluna
                ].isna().sum()
            )
            for coluna in [
                "place_id",
                "nome",
                "endereco_completo",
                "cidade",
                "latitude",
                "longitude",
                "nota_media",
                "total_avaliacoes",
                "nivel_preco",
            ]
        },
        "validacoes": {
            "notas_fora_de_0_a_5": int(
                (
                    estabelecimentos[
                        "nota_media"
                    ].notna()
                    & ~estabelecimentos[
                        "nota_media"
                    ].between(0, 5)
                ).sum()
            ),
            "avaliacoes_negativas": int(
                (
                    estabelecimentos[
                        "total_avaliacoes"
                    ].notna()
                    & (
                        estabelecimentos[
                            "total_avaliacoes"
                        ] < 0
                    )
                ).sum()
            ),
            "latitudes_invalidas": int(
                (
                    estabelecimentos[
                        "latitude"
                    ].notna()
                    & ~estabelecimentos[
                        "latitude"
                    ].between(-90, 90)
                ).sum()
            ),
            "longitudes_invalidas": int(
                (
                    estabelecimentos[
                        "longitude"
                    ].notna()
                    & ~estabelecimentos[
                        "longitude"
                    ].between(-180, 180)
                ).sum()
            ),
        },
        "avisos": avisos,
        "observacao_categoria": (
            "As categorias representam os termos de busca "
            "nos quais cada estabelecimento apareceu. "
            "Não devem ser interpretadas isoladamente como "
            "certificação de que o estabelecimento atende "
            "integralmente à característica alimentar."
        ),
    }

    return relatorio


# ============================================================
# EXPORTAÇÃO
# ============================================================

def exportar_csv(
    estabelecimentos: pd.DataFrame,
    categorias: pd.DataFrame,
    relacionamento: pd.DataFrame,
    coletas: pd.DataFrame,
) -> None:
    """
    Exporta as tabelas processadas em CSV.
    """

    PASTA_PROCESSED.mkdir(
        parents=True,
        exist_ok=True,
    )

    estabelecimentos.to_csv(
        ARQUIVO_ESTABELECIMENTOS,
        index=False,
        encoding="utf-8-sig",
    )

    categorias.to_csv(
        ARQUIVO_CATEGORIAS,
        index=False,
        encoding="utf-8-sig",
    )

    relacionamento.to_csv(
        ARQUIVO_RELACIONAMENTO,
        index=False,
        encoding="utf-8-sig",
    )

    coletas.to_csv(
        ARQUIVO_COLETAS,
        index=False,
        encoding="utf-8-sig",
    )


def exportar_excel(
    estabelecimentos: pd.DataFrame,
    categorias: pd.DataFrame,
    relacionamento: pd.DataFrame,
    coletas: pd.DataFrame,
) -> None:
    """
    Gera um Excel apenas para inspeção e documentação.
    A fonte de verdade continua sendo o RAW + pipeline.
    """

    try:
        estabelecimentos_excel = estabelecimentos.copy()

        if pd.api.types.is_datetime64tz_dtype(
            estabelecimentos_excel["data_atualizacao"]
        ):
            estabelecimentos_excel[
                "data_atualizacao"
            ] = (
                estabelecimentos_excel[
                    "data_atualizacao"
                ]
                .dt.tz_convert(None)
            )

        with pd.ExcelWriter(
            ARQUIVO_EXCEL,
            engine="openpyxl",
        ) as writer:
            estabelecimentos_excel.to_excel(
                writer,
                sheet_name="Estabelecimentos",
                index=False,
            )

            categorias.to_excel(
                writer,
                sheet_name="Categorias_Busca",
                index=False,
            )

            relacionamento.to_excel(
                writer,
                sheet_name="Estab_Categoria",
                index=False,
            )

            coletas.to_excel(
                writer,
                sheet_name="Coletas",
                index=False,
            )

    except ImportError:
        print(
            "\nAVISO: openpyxl não está instalado. "
            "O Excel não foi gerado."
        )


def salvar_relatorio(
    relatorio: dict[str, Any],
) -> None:
    """
    Salva o relatório de qualidade em JSON.
    """

    with ARQUIVO_QUALIDADE.open(
        "w",
        encoding="utf-8",
    ) as arquivo:
        json.dump(
            relatorio,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# RESUMO NO TERMINAL
# ============================================================

def imprimir_resumo(
    relatorio: dict[str, Any],
) -> None:
    """
    Exibe as principais métricas no terminal.
    """

    print("\n" + "=" * 70)
    print("TRATAMENTO E QUALIDADE — ATIVIDADE EXTENSIONISTA II")
    print("=" * 70)

    print(
        "\nRegistros brutos: "
        f"{relatorio['registros_brutos']}"
    )

    print(
        "Place IDs únicos no RAW: "
        f"{relatorio['place_ids_unicos_no_raw']}"
    )

    print(
        "Ocorrências repetidas por place_id: "
        f"{relatorio['ocorrencias_repetidas_por_place_id']}"
    )

    print(
        "Registros fora do escopo territorial: "
        f"{relatorio['registros_brutos_fora_escopo']}"
    )

    print(
        "Estabelecimentos únicos no escopo: "
        f"{relatorio['estabelecimentos_unicos_dentro_escopo']}"
    )

    print("\nEstabelecimentos por cidade:")

    for cidade, quantidade in (
        relatorio[
            "estabelecimentos_por_cidade"
        ].items()
    ):
        print(
            f"  {cidade}: {quantidade}"
        )

    print("\nRelacionamentos por categoria de busca:")

    for categoria, quantidade in (
        relatorio[
            "relacionamentos_por_categoria"
        ].items()
    ):
        print(
            f"  {categoria}: {quantidade}"
        )

    ausentes = relatorio[
        "campos_ausentes_estabelecimentos"
    ]

    print("\nCampos ausentes nos estabelecimentos:")

    for campo, quantidade in ausentes.items():
        print(
            f"  {campo}: {quantidade}"
        )

    print("\nArquivos gerados:")
    print(f"  {ARQUIVO_ESTABELECIMENTOS}")
    print(f"  {ARQUIVO_CATEGORIAS}")
    print(f"  {ARQUIVO_RELACIONAMENTO}")
    print(f"  {ARQUIVO_COLETAS}")
    print(f"  {ARQUIVO_QUALIDADE}")
    print(f"  {ARQUIVO_EXCEL}")

    print("\n" + "=" * 70)
    print("PROCESSO CONCLUÍDO COM SUCESSO")
    print("=" * 70)


# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

def main() -> None:
    """
    Executa o tratamento completo.
    """

    try:
        arquivo_raw = localizar_raw_mais_recente()

        print(
            "Arquivo RAW selecionado:\n"
            f"{arquivo_raw}"
        )

        dados = carregar_json(
            arquivo_raw
        )

        ocorrencias = montar_ocorrencias(
            dados
        )

        ocorrencias = converter_tipos(
            ocorrencias
        )

        avisos = validar_ocorrencias(
            ocorrencias
        )

        ocorrencias_escopo, ocorrencias_fora = (
            separar_escopo(
                ocorrencias
            )
        )

        estabelecimentos = criar_estabelecimentos(
            ocorrencias_escopo
        )

        categorias = criar_categorias()

        relacionamento = criar_relacionamento(
            ocorrencias_escopo,
            categorias,
        )

        coletas = criar_coletas(
            dados
        )

        relatorio = gerar_relatorio_qualidade(
            dados=dados,
            ocorrencias=ocorrencias,
            ocorrencias_escopo=ocorrencias_escopo,
            ocorrencias_fora=ocorrencias_fora,
            estabelecimentos=estabelecimentos,
            relacionamento=relacionamento,
            categorias=categorias,
            avisos=avisos,
            arquivo_raw=arquivo_raw,
        )

        exportar_csv(
            estabelecimentos,
            categorias,
            relacionamento,
            coletas,
        )

        exportar_excel(
            estabelecimentos,
            categorias,
            relacionamento,
            coletas,
        )

        salvar_relatorio(
            relatorio
        )

        imprimir_resumo(
            relatorio
        )

    except (
        FileNotFoundError,
        ValueError,
    ) as erro:
        print("\nERRO NO TRATAMENTO")
        print(erro)

    except PermissionError:
        print(
            "\nERRO DE PERMISSÃO.\n"
            "Feche arquivos Excel/CSV abertos e "
            "execute novamente."
        )

    except Exception as erro:
        print("\nERRO INESPERADO")
        print(
            f"{type(erro).__name__}: {erro}"
        )


if __name__ == "__main__":
    main()
