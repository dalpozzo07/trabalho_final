
import json
from urllib.parse import urlencode

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError
)

URL = "https://dadosabertos.ccee.org.br/api/3/action/datastore_search"

RECURSOS = {
    2025: "2a180a6b-f092-43eb-9f82-a48798b803dc",
    2026: "3f279d6b-1069-42f7-9b0a-217b084729c4"
}


def extrair_pld(pagina, ano, resource_id):

    parametros = {
        "resource_id": resource_id,
        "limit": 5,
        "offset": 0
    }

    url_completa = f"{URL}?{urlencode(parametros)}"

    print(f"\nConsultando PLD de {ano}...")

    try:
        resposta = pagina.goto(
            url_completa,
            wait_until="domcontentloaded",
            timeout=60000
        )

        if resposta is None:
            print("Nenhuma resposta recebida.")
            return False

        print("Status HTTP:", resposta.status)

        if resposta.status != 200:
            print("A consulta foi recusada pelo servidor.")
            print(resposta.text()[:300])
            return False

        dados = json.loads(resposta.text())

        if not dados.get("success"):
            print("Erro da API:", dados.get("error"))
            return False

        resultado = dados["result"]
        registros = resultado.get("records", [])

        print("Total disponível:", resultado.get("total"))
        print("Registros recebidos:", len(registros))

        if registros:
            print("\nPrimeiro registro:")
            print(json.dumps(
                registros[0],
                indent=4,
                ensure_ascii=False
            ))

        print(f"\nPLD {ano}: SUCESSO!")
        return True

    except PlaywrightTimeoutError:
        print("Tempo limite excedido.")
        return False

    except (ValueError, json.JSONDecodeError) as erro:
        print("Resposta JSON inválida:", erro)
        return False

    except Exception as erro:
        print("Erro:", erro)
        return False


def main():

    with sync_playwright() as playwright:

        # Navegador automatizado sem interface visual
        navegador = playwright.chromium.launch(
            headless=True
        )

        pagina = navegador.new_page()

        resultados = {}

        for ano, resource_id in RECURSOS.items():

            resultados[ano] = extrair_pld(
                pagina,
                ano,
                resource_id
            )

        navegador.close()

        print("\n====== RESULTADO FINAL ======")

        for ano, sucesso in resultados.items():
            status = "SUCESSO" if sucesso else "FALHOU"
            print(f"{ano}: {status}")


if __name__ == "__main__":
    main()
