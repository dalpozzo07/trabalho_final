
import os
import json
import psycopg

from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB = {
    "host": os.getenv("PGHOST"),
    "port": os.getenv("PGPORT", "5432"),
    "dbname": os.getenv("PGDATABASE"),
    "user": os.getenv("PGUSER"),
    "password": os.getenv("PGPASSWORD"),
    "sslmode": "require"
}

VARIAVEIS = {
    "temperature_2m": "temperatura_c",
    "precipitation": "precipitacao_mm",
    "wind_speed_10m": "vento_kmh",
    "shortwave_radiation": "radiacao_w_m2"
}


def tratar_clima():
    total_inserido = 0
    falhas = 0

    with psycopg.connect(**DB) as conexao:

        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id_raw, cod_usina,
                    data_inicio, data_fim,
                    resposta_original
                FROM raw_campo_real.clima_raw
                WHERE data_inicio >= DATE '2025-01-01'
                  AND data_inicio < DATE '2026-01-01'
                  AND data_inicio =
                      date_trunc('month', data_inicio)::date
                  AND data_fim =
                      (
                        date_trunc('month', data_inicio)
                        + INTERVAL '1 month - 1 day'
                      )::date
                ORDER BY cod_usina, data_inicio
            """)

            registros_raw = cursor.fetchall()

        print("Lotes RAW encontrados:", len(registros_raw))

        for id_raw, codigo, inicio, fim, resposta in registros_raw:

            inicio_execucao = datetime.now().astimezone()
            lidas = 0
            gravadas = 0

            try:
                dados = json.loads(resposta)
                hourly = dados["hourly"]
                horarios = hourly["time"]

                lidas = len(horarios)
                esperado = ((fim - inicio).days + 1) * 24

                if lidas != esperado:
                    raise ValueError(
                        f"Esperadas {esperado} horas; "
                        f"recebidas {lidas}"
                    )

                if len(set(horarios)) != lidas:
                    raise ValueError("Horas duplicadas no JSON")

                for campo in VARIAVEIS:
                    if len(hourly[campo]) != lidas:
                        raise ValueError(
                            f"Quantidade incorreta em {campo}"
                        )

                registros = []

                for i, horario in enumerate(horarios):
                    registros.append({
                        "data_hora": horario,
                        "temperatura_c":
                            hourly["temperature_2m"][i],
                        "precipitacao_mm":
                            hourly["precipitation"][i],
                        "vento_kmh":
                            hourly["wind_speed_10m"][i],
                        "radiacao_w_m2":
                            hourly["shortwave_radiation"][i]
                    })

                # Envia as horas de um mês em uma única
                # operação SQL, evitando milhares de INSERTs.
                with conexao.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO tratado_campo_real.clima_horario (
                            cod_usina,
                            data_hora,
                            temperatura_c,
                            precipitacao_mm,
                            vento_kmh,
                            radiacao_w_m2,
                            id_raw
                        )
                        SELECT
                            %s,
                            d.data_hora,
                            d.temperatura_c,
                            d.precipitacao_mm,
                            d.vento_kmh,
                            d.radiacao_w_m2,
                            %s
                        FROM jsonb_to_recordset(%s::jsonb)
                        AS d (
                            data_hora TIMESTAMP,
                            temperatura_c NUMERIC,
                            precipitacao_mm NUMERIC,
                            vento_kmh NUMERIC,
                            radiacao_w_m2 NUMERIC
                        )
                        ON CONFLICT (cod_usina, data_hora)
                        DO NOTHING
                    """, (
                        codigo,
                        id_raw,
                        json.dumps(registros, allow_nan=False)
                    ))

                    gravadas = cursor.rowcount

                    cursor.execute("""
                        INSERT INTO raw_campo_real.log_extracao (
                            fonte, inicio, fim,
                            linhas_lidas, linhas_gravadas,
                            status, erro
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, NULL)
                    """, (
                        "Tratamento Open-Meteo",
                        inicio_execucao,
                        datetime.now().astimezone(),
                        lidas,
                        gravadas,
                        "OK"
                    ))

                conexao.commit()
                total_inserido += gravadas

                print(
                    f"{codigo} | {inicio} | "
                    f"{lidas} horas | "
                    f"{gravadas} inseridas"
                )

            except Exception as erro:
                conexao.rollback()
                falhas += 1

                print(
                    f"ERRO | {codigo} | {inicio}: {erro}"
                )

                with conexao.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO raw_campo_real.log_extracao (
                            fonte, inicio, fim,
                            linhas_lidas, linhas_gravadas,
                            status, erro
                        )
                        VALUES (%s, %s, %s, %s, 0, 'ERRO', %s)
                    """, (
                        "Tratamento Open-Meteo",
                        inicio_execucao,
                        datetime.now().astimezone(),
                        lidas,
                        str(erro)
                    ))

                conexao.commit()

        print("\n====== RESULTADO FINAL ======")
        print("Novas linhas inseridas:", total_inserido)
        print("Lotes com falha:", falhas)

        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*)
                FROM tratado_campo_real.clima_horario
                WHERE data_hora >= '2025-01-01'
                AND data_hora < '2026-01-01'
            """)

            print(
                "Total de linhas de 2025:",
                cursor.fetchone()[0]
            )


if __name__ == "__main__":
    tratar_clima()
