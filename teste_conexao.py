
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

try:
    with psycopg.connect(
        host=os.getenv("PGHOST"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        sslmode="require",
        connect_timeout=15
    ) as conexao:

        print("Conectado ao Neon com sucesso!")

        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*)
                FROM campo_real_energia.usina;
            """)

            total_usinas = cursor.fetchone()[0]
            print("Total de usinas:", total_usinas)

            cursor.execute("""
                SELECT COUNT(*)
                FROM campo_real_energia.medicao_geracao;
            """)

            total_medicoes = cursor.fetchone()[0]
            print("Total de medições:", total_medicoes)

except psycopg.Error as erro:
    print("Erro ao conectar ou consultar o banco:")
    print(erro)
