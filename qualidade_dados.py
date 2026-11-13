
import os
import uuid
import psycopg
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

REGRAS = [
    (
        "Completude",
        "Campos obrigatorios ausentes",
        "campo_real_energia.medicao_geracao",
        """
        SELECT COUNT(*),
               COUNT(*) FILTER (
                   WHERE energia_mwh IS NULL
                      OR id_usina IS NULL
                      OR data_hora IS NULL
               )
        FROM campo_real_energia.medicao_geracao
        """
    ),
    (
        "Unicidade",
        "Medicoes repetidas por usina e hora",
        "campo_real_energia.medicao_geracao",
        """
        WITH dados AS (
            SELECT COUNT(*) OVER (
                PARTITION BY id_usina, data_hora
            ) AS ocorrencias
            FROM campo_real_energia.medicao_geracao
        )
        SELECT COUNT(*),
               COUNT(*) FILTER (
                   WHERE ocorrencias > 1
               )
        FROM dados
        """
    ),
    (
        "Validade",
        "Energia negativa ou data fora de 2025",
        "campo_real_energia.medicao_geracao",
        """
        SELECT COUNT(*),
               COUNT(*) FILTER (
                   WHERE energia_mwh < 0
                      OR data_hora < '2025-01-01'
                      OR data_hora >= '2026-01-01'
               )
        FROM campo_real_energia.medicao_geracao
        """
    ),
    (
        "Consistencia",
        "Geracao positiva durante parada",
        "campo_real_energia.medicao_geracao",
        """
        SELECT COUNT(*),
               COUNT(*) FILTER (
                   WHERE m.energia_mwh > 0
                   AND EXISTS (
                       SELECT 1
                       FROM campo_real_energia.parada_usina p
                       WHERE p.id_usina = m.id_usina
                         AND p.fim >= p.inicio
                         AND m.data_hora
                             BETWEEN p.inicio AND p.fim
                   )
               )
        FROM campo_real_energia.medicao_geracao m
        """
    ),
    (
        "Acuracia",
        "Geracao superior a potencia instalada",
        "campo_real_energia.medicao_geracao",
        """
        SELECT COUNT(*),
               COUNT(*) FILTER (
                   WHERE m.energia_mwh > u.potencia_mw
               )
        FROM campo_real_energia.medicao_geracao m
        JOIN campo_real_energia.usina u
          ON u.id_usina = m.id_usina
        """
    ),
    (
        "Integridade referencial",
        "Medicao sem usina valida",
        "campo_real_energia.medicao_geracao",
        """
        SELECT COUNT(*),
               COUNT(*) FILTER (
                   WHERE m.id_usina IS NULL
                      OR u.id_usina IS NULL
               )
        FROM campo_real_energia.medicao_geracao m
        LEFT JOIN campo_real_energia.usina u
          ON u.id_usina = m.id_usina
        """
    ),
    (
        "Atualidade",
        "Medicao recebida antes ou muito depois",
        "campo_real_energia.medicao_geracao",
        """
        SELECT COUNT(*),
               COUNT(*) FILTER (
                   WHERE recebido_em IS NULL
                      OR recebido_em < data_hora
                      OR recebido_em >
                         data_hora + INTERVAL '24 hours'
               )
        FROM campo_real_energia.medicao_geracao
        """
    )
]


def executar_qualidade():
    id_execucao = uuid.uuid4()

    with psycopg.connect(**DB) as conexao:
        with conexao.cursor() as cursor:

            for dimensao, regra, tabela, consulta in REGRAS:
                cursor.execute(consulta)

                total, falhas = cursor.fetchone()

                percentual = (
                    round(falhas * 100 / total, 2)
                    if total > 0 else 0
                )

                cursor.execute("""
                    INSERT INTO qualidade_campo_real.metricas_qualidade (
                        id_execucao,
                        dimensao,
                        regra,
                        tabela_origem,
                        registros_avaliados,
                        registros_com_falha,
                        percentual_falha
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    id_execucao,
                    dimensao,
                    regra,
                    tabela,
                    total,
                    falhas,
                    percentual
                ))

                print(
                    f"{dimensao}: {falhas} falhas "
                    f"em {total} registros ({percentual}%)"
                )

        conexao.commit()

    print("\nMetricas gravadas no Neon!")
    print("Execucao:", id_execucao)


if __name__ == "__main__":
    executar_qualidade()
