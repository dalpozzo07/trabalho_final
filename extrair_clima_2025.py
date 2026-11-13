
import os
import time
import calendar
import requests
import psycopg

from datetime import datetime
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

VARIAVEIS = [
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
    "shortwave_radiation"
]

# Correção documentada com base no SQL original.
# Não altera os cadastros da professora.
COORDENADAS_CORRIGIDAS = {
    "CRE-UFV-004": (-15.803000, -43.308000)
}


def registrar_log(conexao, inicio, lidas,
                  gravadas, status, erro=None):

    with conexao.cursor() as cursor:
        cursor.execute("""
            INSERT INTO raw_campo_real.log_extracao
            (fonte, inicio, fim, linhas_lidas,
             linhas_gravadas, status, erro)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            "Open-Meteo",
            inicio,
            datetime.now().astimezone(),
            lidas,
            gravadas,
            status,
            erro
        ))

    conexao.commit()


def buscar_usinas(conexao):
    with conexao.cursor() as cursor:
        cursor.execute("""
            SELECT cod_usina, latitude, longitude
            FROM campo_real_energia.usina
            WHERE cod_usina ~ '^CRE-[A-Z]{3}-[0-9]{3}$'
            ORDER BY cod_usina
        """)

        return cursor.fetchall()


def ja_existe(conexao, codigo, inicio, fim):
    with conexao.cursor() as cursor:
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM raw_campo_real.clima_raw
                WHERE cod_usina = %s
                  AND data_inicio = %s
                  AND data_fim = %s
            )
        """, (codigo, inicio, fim))

        return cursor.fetchone()[0]


def criar_sessao():
    sessao = requests.Session()

    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True
    )

    sessao.mount(
        "https://",
        HTTPAdapter(max_retries=retry)
    )

    return sessao


def executar():
    with psycopg.connect(**DB) as conexao:
        usinas = buscar_usinas(conexao)

        print("Usinas encontradas:", len(usinas))

        if len(usinas) != 9:
            raise ValueError(
                "Esperadas 9 usinas originais. "
                "Confira o cadastro antes de continuar."
            )

        total_gravado = 0
        falhas = 0

        with criar_sessao() as sessao:

            for codigo, latitude, longitude in usinas:

                if codigo in COORDENADAS_CORRIGIDAS:
                    print(
                        f"AVISO: coordenada corrigida "
                        f"para {codigo}"
                    )
                    latitude, longitude = (
                        COORDENADAS_CORRIGIDAS[codigo]
                    )

                print(f"\n===== {codigo} =====")

                for mes in range(1, 13):

                    inicio = f"2025-{mes:02d}-01"

                    ultimo_dia = calendar.monthrange(
                        2025, mes
                    )[1]

                    fim = (
                        f"2025-{mes:02d}-{ultimo_dia:02d}"
                    )

                    inicio_execucao = (
                        datetime.now().astimezone()
                    )

                    if ja_existe(
                        conexao, codigo, inicio, fim
                    ):
                        print(
                            f"{inicio}: já armazenado"
                        )

                        registrar_log(
                            conexao, inicio_execucao,
                            0, 0, "IGNORADO"
                        )
                        continue

                    parametros = {
                        "latitude": float(latitude),
                        "longitude": float(longitude),
                        "start_date": inicio,
                        "end_date": fim,
                        "hourly": ",".join(VARIAVEIS),
                        "timezone": "America/Sao_Paulo"
                    }

                    try:
                        resposta = sessao.get(
                            URL,
                            params=parametros,
                            timeout=(15, 90)
                        )

                        resposta.raise_for_status()

                        dados = resposta.json()
                        horarios = dados["hourly"]["time"]

                        quantidade = len(horarios)
                        esperado = ultimo_dia * 24

                        if quantidade != esperado:
                            raise ValueError(
                                f"Esperadas {esperado} horas, "
                                f"recebidas {quantidade}"
                            )

                        for variavel in VARIAVEIS:
                            if len(
                                dados["hourly"][variavel]
                            ) != quantidade:
                                raise ValueError(
                                    f"Campo incompleto: {variavel}"
                                )

                        with conexao.cursor() as cursor:
                            cursor.execute("""
                                INSERT INTO
                                raw_campo_real.clima_raw
                                (
                                    cod_usina,
                                    latitude,
                                    longitude,
                                    data_inicio,
                                    data_fim,
                                    origem,
                                    resposta_original
                                )
                                VALUES (
                                    %s, %s, %s, %s,
                                    %s, %s, %s
                                )
                                ON CONFLICT (
                                    cod_usina,
                                    data_inicio,
                                    data_fim
                                ) DO NOTHING
                                RETURNING id_raw
                            """, (
                                codigo,
                                latitude,
                                longitude,
                                inicio,
                                fim,
                                resposta.url,
                                resposta.text
                            ))

                            inserido = cursor.fetchone()

                        conexao.commit()

                        gravadas = (
                            quantidade if inserido else 0
                        )

                        registrar_log(
                            conexao,
                            inicio_execucao,
                            quantidade,
                            gravadas,
                            "OK"
                        )

                        total_gravado += gravadas

                        print(
                            f"{inicio}: {quantidade} "
                            "horas recebidas"
                        )

                    except Exception as erro:
                        conexao.rollback()
                        falhas += 1

                        print(
                            f"ERRO em {codigo} "
                            f"{inicio}: {erro}"
                        )

                        registrar_log(
                            conexao,
                            inicio_execucao,
                            0, 0, "ERRO",
                            str(erro)
                        )

                        # Não insistir em bloqueios de acesso
                        if isinstance(
                            erro, requests.HTTPError
                        ):
                            status = erro.response.status_code

                            if status in (401, 403):
                                print(
                                    "Acesso recusado. "
                                    "Extração interrompida."
                                )
                                return

                    time.sleep(1)

        print("\n====== RESULTADO ======")
        print("Novas horas armazenadas:", total_gravado)
        print("Consultas com falha:", falhas)


if __name__ == "__main__":
    executar()
