
import json
import time
from datetime import datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# API oficial da CCEE
URL = "https://dadosabertos.ccee.org.br/api/3/action/datastore_search"

RECURSOS = {
    2025: "2a180a6b-f092-43eb-9f82-a48798b803dc",
    2026: "3f279d6b-1069-42f7-9b0a-217b084729c4"
}

# Primeiro teste: 5 registros por ano.
# Depois alteraremos para 5000.
LIMITE = 5

# Pasta para registrar erros
Path("logs").mkdir(exist_ok=True)

# Configuração da conexão HTTP
sessao = requests.Session()

sessao.headers.update({
    "User-Agent": "CampoRealEnergiaDW/1.0 (projeto academico)",
    "Accept": "application/json"
})

# Repetir somente em erros temporários
tentativas = Retry(
    total=3,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)

adaptador = HTTPAdapter(max_retries=tentativas)

sessao.mount("https://", adaptador)


def registrar_erro(ano, mensagem):
    with open("logs/erros_ccee.log", "a", encoding="utf-8") as arquivo:
        arquivo.write(
            f"{datetime.now().isoformat()} | "
            f"Ano: {ano} | {mensagem}\n"
        )


def extrair_pld(ano, resource_id):
    print(f"\nConsultando PLD de {ano}...")

    parametros = {
        "resource_id": resource_id,
        "limit": LIMITE,
        "offset": 0
    }

    try:
        resposta = sessao.get(
            URL,
            params=parametros,
            timeout=60
        )

        print("Status HTTP:", resposta.status_code)

        if resposta.status_code == 403:
            mensagem = (
                "Acesso bloqueado pela CCEE (HTTP 403). "
                "O servidor recusou o cliente Python."
            )
            print(mensagem)
            registrar_erro(ano, mensagem)
            return False

        resposta.raise_for_status()

        tipo = resposta.headers.get("Content-Type", "")

        if "json" not in tipo.lower():
            raise ValueError(
                f"Resposta inesperada: {tipo}"
            )

        dados = resposta.json()

        if not dados.get("success"):
            raise ValueError(
                f"Erro retornado pela API: {dados.get('error')}"
            )

        resultado = dados["result"]
        registros = resultado.get("records", [])

        print("Total disponível:", resultado.get("total"))
        print("Registros recebidos:", len(registros))

        if not registros:
            print("A API não retornou registros.")
            return False

        print("\nColunas:")
        print(list(registros[0].keys()))

        print("\nPrimeiro registro:")
        print(json.dumps(
            registros[0],
            indent=4,
            ensure_ascii=False
        ))

        print(f"\nExtração de {ano} funcionando!")
        return True

    except (requests.RequestException, ValueError, KeyError) as erro:
        print(f"Erro ao consultar {ano}: {erro}")
        registrar_erro(ano, str(erro))
        return False


def main():
    resultados = {}

    for ano, resource_id in RECURSOS.items():
        resultados[ano] = extrair_pld(
            ano,
            resource_id
        )

        time.sleep(1)

    print("\n====== RESUMO ======")

    for ano, sucesso in resultados.items():
        status = "SUCESSO" if sucesso else "FALHOU"
        print(f"{ano}: {status}")

    sessao.close()


if __name__ == "__main__":
    main()
