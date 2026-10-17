from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


# ============================================================
# CONFIGURAÇÕES
# ============================================================

PASTA_PROJETO = Path(__file__).resolve().parent.parent
PASTA_RAW = PASTA_PROJETO / "data" / "raw"

ARQUIVO_ENV = PASTA_PROJETO / ".env"

URL_TEXT_SEARCH = (
    "https://places.googleapis.com/v1/places:searchText"
)

FONTE = "Google Places API (New)"

PAGE_SIZE = 20
MAX_PAGINAS_POR_CONSULTA = 3

TIMEOUT_SEGUNDOS = 30
INTERVALO_ENTRE_REQUISICOES = 1.0


CONSULTAS = [
    {
        "municipio": "Curitiba",
        "categoria": "Vegetariano",
        "termo": "restaurantes vegetarianos em Curitiba PR",
    },
    {
        "municipio": "Curitiba",
        "categoria": "Vegano",
        "termo": "restaurantes veganos em Curitiba PR",
    },
    {
        "municipio": "Curitiba",
        "categoria": "Sem glúten",
        "termo": "restaurantes sem glúten em Curitiba PR",
    },
    {
        "municipio": "Curitiba",
        "categoria": "Sem lactose",
        "termo": "restaurantes sem lactose em Curitiba PR",
    },
    {
        "municipio": "São José dos Pinhais",
        "categoria": "Vegetariano",
        "termo": (
            "restaurantes vegetarianos "
            "em São José dos Pinhais PR"
        ),
    },
    {
        "municipio": "São José dos Pinhais",
        "categoria": "Vegano",
        "termo": (
            "restaurantes veganos "
            "em São José dos Pinhais PR"
        ),
    },
    {
        "municipio": "São José dos Pinhais",
        "categoria": "Sem glúten",
        "termo": (
            "restaurantes sem glúten "
            "em São José dos Pinhais PR"
        ),
    },
    {
        "municipio": "São José dos Pinhais",
        "categoria": "Sem lactose",
        "termo": (
            "restaurantes sem lactose "
            "em São José dos Pinhais PR"
        ),
    },
]


FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.priceLevel",
        "places.types",
        "nextPageToken",
    ]
)


# ============================================================
# CONFIGURAÇÃO E SEGURANÇA
# ============================================================

def carregar_chave_api() -> str:
    """
    Carrega a chave da API a partir do arquivo .env.
    """

    load_dotenv(ARQUIVO_ENV)

    chave = os.getenv("GOOGLE_PLACES_API_KEY")

    if not chave:
        raise RuntimeError(
            "A variável GOOGLE_PLACES_API_KEY "
            "não foi encontrada no arquivo .env."
        )

    return chave


# ============================================================
# REQUISIÇÃO
# ============================================================

def executar_requisicao(
    api_key: str,
    termo: str,
    page_token: str | None = None,
) -> dict[str, Any]:
    """
    Executa uma consulta no Google Places Text Search (New).
    """

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    payload: dict[str, Any] = {
        "textQuery": termo,
        "languageCode": "pt-BR",
        "regionCode": "BR",
        "pageSize": PAGE_SIZE,
    }

    if page_token:
        payload["pageToken"] = page_token

    resposta = requests.post(
        URL_TEXT_SEARCH,
        headers=headers,
        json=payload,
        timeout=TIMEOUT_SEGUNDOS,
    )

    if not resposta.ok:
        print("\n  DETALHES DO ERRO DA API:")

        try:
            dados_erro = resposta.json()
            erro = dados_erro.get("error", {})

            codigo = erro.get("code")
            status = erro.get("status")
            mensagem = erro.get("message")

            if codigo is not None:
                print(f"    Código: {codigo}")

            if status:
                print(f"    Status: {status}")

            if mensagem:
                print(f"    Mensagem: {mensagem}")

            if not erro:
                print(f"    {resposta.text}")

        except ValueError:
            print(f"    {resposta.text}")

    resposta.raise_for_status()

    return resposta.json()


# ============================================================
# COLETA DE UMA CONSULTA
# ============================================================

def coletar_consulta(
    api_key: str,
    municipio: str,
    categoria: str,
    termo: str,
) -> dict[str, Any]:
    """
    Executa todas as páginas disponíveis para uma consulta.
    """

    registros: list[dict[str, Any]] = []

    token: str | None = None
    numero_pagina = 1

    while numero_pagina <= MAX_PAGINAS_POR_CONSULTA:

        dados = executar_requisicao(
            api_key=api_key,
            termo=termo,
            page_token=token,
        )

        lugares = dados.get("places", [])

        momento_coleta = datetime.now(
            timezone.utc
        ).isoformat()

        for lugar in lugares:
            registro = {
                "municipio_busca": municipio,
                "categoria_busca": categoria,
                "termo_busca": termo,
                "fonte": FONTE,
                "data_coleta": momento_coleta,
                "pagina": numero_pagina,
                "dados_api": lugar,
            }

            registros.append(registro)

        print(
            f"  Página {numero_pagina}: "
            f"{len(lugares)} registros"
        )

        token = dados.get("nextPageToken")

        if not token:
            break

        numero_pagina += 1

        time.sleep(INTERVALO_ENTRE_REQUISICOES)

    return {
        "municipio": municipio,
        "categoria": categoria,
        "termo": termo,
        "quantidade_registros": len(registros),
        "registros": registros,
    }


# ============================================================
# COLETA COMPLETA
# ============================================================

def executar_coleta() -> dict[str, Any]:
    """
    Executa todas as consultas definidas no projeto.
    """

    api_key = carregar_chave_api()

    PASTA_RAW.mkdir(
        parents=True,
        exist_ok=True,
    )

    inicio = datetime.now(
        timezone.utc
    )

    resultados_consultas = []
    consultas_com_erro = []

    print("=" * 70)
    print("COLETA DE DADOS — ATIVIDADE EXTENSIONISTA II")
    print("=" * 70)

    for numero, consulta in enumerate(
        CONSULTAS,
        start=1,
    ):
        print(
            f"\n[{numero}/{len(CONSULTAS)}] "
            f"{consulta['categoria']} — "
            f"{consulta['municipio']}"
        )

        try:
            resultado = coletar_consulta(
                api_key=api_key,
                municipio=consulta["municipio"],
                categoria=consulta["categoria"],
                termo=consulta["termo"],
            )

            resultados_consultas.append(resultado)

            print(
                "  Total da consulta: "
                f"{resultado['quantidade_registros']}"
            )

        except requests.HTTPError as erro:
            status_code = (
                erro.response.status_code
                if erro.response is not None
                else None
            )

            consultas_com_erro.append(
                {
                    "municipio": consulta["municipio"],
                    "categoria": consulta["categoria"],
                    "termo": consulta["termo"],
                    "tipo_erro": "HTTPError",
                    "status_http": status_code,
                }
            )

            print(
                "  ERRO HTTP: "
                f"{erro}"
            )

            if status_code in (401, 403):
                print(
                    "\n  COLETA INTERROMPIDA: "
                    "erro de autenticação/permissão."
                )
                print(
                    "  Verifique a Places API (New), "
                    "o faturamento e as restrições da chave."
                )
                break

        except requests.RequestException as erro:
            consultas_com_erro.append(
                {
                    "municipio": consulta["municipio"],
                    "categoria": consulta["categoria"],
                    "termo": consulta["termo"],
                    "tipo_erro": type(erro).__name__,
                    "status_http": None,
                }
            )

            print(
                "  ERRO DE CONEXÃO: "
                f"{erro}"
            )

        time.sleep(INTERVALO_ENTRE_REQUISICOES)

    fim = datetime.now(
        timezone.utc
    )

    total_registros = sum(
        item["quantidade_registros"]
        for item in resultados_consultas
    )

    resultado_final = {
        "projeto": (
            "Atividade Extensionista II - "
            "Tecnologia Aplicada à Inclusão Digital"
        ),
        "fonte": FONTE,
        "inicio_coleta": inicio.isoformat(),
        "fim_coleta": fim.isoformat(),
        "quantidade_consultas_planejadas": len(CONSULTAS),
        "quantidade_consultas_concluidas": len(
            resultados_consultas
        ),
        "quantidade_consultas_com_erro": len(
            consultas_com_erro
        ),
        "quantidade_registros_brutos": total_registros,
        "consultas": resultados_consultas,
        "erros": consultas_com_erro,
    }

    return resultado_final


# ============================================================
# SALVAMENTO RAW
# ============================================================

def salvar_json_raw(
    dados: dict[str, Any],
) -> Path:
    """
    Salva os dados exatamente como coletados e enriquecidos
    apenas com metadados de rastreabilidade.
    """

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    caminho = (
        PASTA_RAW
        / f"google_places_raw_{timestamp}.json"
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

    return caminho


# ============================================================
# EXECUÇÃO
# ============================================================

def main() -> None:

    try:
        dados = executar_coleta()

        consultas_concluidas = dados[
            "quantidade_consultas_concluidas"
        ]
        registros_brutos = dados[
            "quantidade_registros_brutos"
        ]

        print("\n" + "=" * 70)

        if consultas_concluidas == 0 or registros_brutos == 0:
            print("COLETA NÃO CONCLUÍDA")
            print("=" * 70)

            print(
                "Consultas concluídas com sucesso: "
                f"{consultas_concluidas}"
            )
            print(
                "Consultas com erro: "
                f"{dados['quantidade_consultas_com_erro']}"
            )
            print(
                "Registros brutos: "
                f"{registros_brutos}"
            )
            print(
                "\nNenhum arquivo RAW válido foi gerado, "
                "pois não houve dados coletados com sucesso."
            )
            return

        caminho = salvar_json_raw(
            dados
        )

        print("COLETA FINALIZADA")
        print("=" * 70)

        print(
            "Consultas planejadas: "
            f"{dados['quantidade_consultas_planejadas']}"
        )
        print(
            "Consultas concluídas: "
            f"{consultas_concluidas}"
        )
        print(
            "Consultas com erro: "
            f"{dados['quantidade_consultas_com_erro']}"
        )
        print(
            "Registros brutos: "
            f"{registros_brutos}"
        )
        print(
            "\nArquivo RAW salvo em:\n"
            f"{caminho}"
        )

    except RuntimeError as erro:
        print("\nERRO DE CONFIGURAÇÃO")
        print(erro)

    except Exception as erro:
        print("\nERRO INESPERADO")
        print(
            f"{type(erro).__name__}: {erro}"
        )


if __name__ == "__main__":
    main()
