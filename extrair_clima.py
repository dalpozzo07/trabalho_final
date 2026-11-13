
import os
import requests
import psycopg

from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

URL = "https://archive-api.open-meteo.com/v1/archive"

DB = {
    "host": os.getenv("PGHOST"),
    "port": os.getenv("PGPORT", "5432"),
    "dbname": os.getenv("PGDATABASE"),
    "user": os.getenv("PGUSER"),
    "password": os.getenv("PGPASSWORD"),
    "sslmode": "require"
}


def preparar_banco(conexao):
    with conexao.cursor() as cursor:

        cursor.execute("""
            CREATE SCHEMA IF NOT EXISTS raw_campo_real;
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_campo_real.clima_raw (
                id_raw BIGINT GENERATED ALWAYS AS IDENTITY
                    PRIMARY KEY,
                cod_usina VARCHAR(12) NOT NULL,
                latitude NUMERIC(9,6) NOT NULL,
                longitude NUMERIC(9,6) NOT NULL,
                data_inicio DATE NOT NULL,
                data_fim DATE NOT NULL,
                origem TEXT NOT NULL,
                resposta_original TEXT NOT NULL,
                extraido_em TIMESTAMPTZ NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (cod_usina, data_inicio, data_fim)
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_campo_real.log_extracao (
                id_log BIGINT GENERATED ALWAYS AS IDENTITY
                    PRIMARY KEY,
                fonte VARCHAR(50) NOT NULL,
                inicio TIMESTAMPTZ NOT NULL,
                fim TIMESTAMPTZ,
                linhas_lidas INTEGER DEFAULT 0,
                linhas_gravadas INTEGER DEFAULT 0,
                status VARCHAR(20) NOT NULL,
                erro TEXT
            );
        """)


def extrair_clima():
    inicio_execucao = datetime.now().astimezone()
    linhas_lidas = 0
    linhas_gravadas = 0
    status = "ERRO"
    erro = None

    try:
        with psycopg.connect(**DB) as conexao:

            preparar_banco(conexao)

            with conexao.cursor() as cursor:
                cursor.execute("""
                    SELECT cod_usina, latitude, longitude
                    FROM campo_real_energia.usina
                    WHERE cod_usina = 'CRE-EOL-007';
                """)

                usina = cursor.fetchone()

                if usina is None:
                    raise ValueError("Usina não encontrada.")

                codigo, latitude, longitude = usina

                parametros = {
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "start_date": "2025-01-01",
                    "end_date": "2025-01-02",
                    "hourly": (
                        "temperature_2m,"
                        "precipitation,"
                        "wind_speed_10m,"
                        "shortwave_radiation"
                    ),
                    "timezone": "America/Sao_Paulo"
                }

                print("Consultando Open-Meteo...")
                print("Usina:", codigo)

                resposta = requests.get(
                    URL,
                    params=parametros,
                    timeout=(15, 60)
                )

                print("Status HTTP:", resposta.status_code)

                resposta.raise_for_status()
                dados = resposta.json()

                horarios = dados["hourly"]["time"]
                linhas_lidas = len(horarios)

                variaveis = [
                    "temperature_2m",
                    "precipitation",
                    "wind_speed_10m",
                    "shortwave_radiation"
                ]

                for variavel in variaveis:
                    if len(dados["hourly"][variavel]) != linhas_lidas:
                        raise ValueError(
                            f"Tamanho inválido: {variavel}"
                        )

                print("Horas recebidas:", linhas_lidas)

                cursor.execute("""
                    INSERT INTO raw_campo_real.clima_raw (
                        cod_usina,
                        latitude,
                        longitude,
                        data_inicio,
                        data_fim,
                        origem,
                        resposta_original
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (
                        cod_usina, data_inicio, data_fim
                    ) DO NOTHING
                    RETURNING id_raw;
                """, (
                    codigo,
                    latitude,
                    longitude,
                    "2025-01-01",
                    "2025-01-02",
                    URL,
                    resposta.text
                ))

                inserido = cursor.fetchone()
                linhas_gravadas = linhas_lidas if inserido else 0
                status = "OK"

                print("Dados armazenados no Neon!")
                print("Primeira hora:", horarios[0])
                print(
                    "Primeira temperatura:",
                    dados["hourly"]["temperature_2m"][0]
                )

                print("Linhas novas gravadas:", linhas_gravadas)

    except Exception as excecao:
        erro = str(excecao)
        print("Erro na extração:", erro)

    # Registra a execução no banco
    try:
        with psycopg.connect(**DB) as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO raw_campo_real.log_extracao (
                        fonte, inicio, fim,
                        linhas_lidas, linhas_gravadas,
                        status, erro
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                """, (
                    "Open-Meteo",
                    inicio_execucao,
                    datetime.now().astimezone(),
                    linhas_lidas,
                    linhas_gravadas,
                    status,
                    erro
                ))
    except Exception as excecao:
        print("Não foi possível gravar o log:", excecao)


if __name__ == "__main__":
    extrair_clima()
