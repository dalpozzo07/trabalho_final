import requests
import json
from pathlib import Path
from datetime import datetime

URL = "https://dadosabertos.ccee.org.br/api/3/action/datastore_search"

RECURSOS = {
    "2025": "2a180a6b-f092-43eb-9f82-a48798b803dc",
    "2026": "3f279d6b-1069-42f7-9b0a-217b084729c4"
}

session = requests.Session()

session.headers.update({
    "Accept": "application/json",
    "User-Agent": "CampoRealDW/1.0"
})

relatorio = []

relatorio.append(
    f"DIAGNOSTICO CCEE - {datetime.now().isoformat()}"
)

for ano, resource_id in RECURSOS.items():

    print(f"\n{'=' * 50}")
    print(f"CONSULTANDO PLD {ano}")
    print("=" * 50)

    try:
        resposta = session.get(
            URL,
            params={
                "resource_id": resource_id,
                "limit": 3,
                "offset": 0
            },
            timeout=60
        )

        print("Status HTTP:", resposta.status_code)
        print("URL:", resposta.url)

        relatorio.append(f"\nANO: {ano}")
        relatorio.append(f"STATUS: {resposta.status_code}")
        relatorio.append(f"URL: {resposta.url}")

        if resposta.status_code != 200:

            print("RESPOSTA DE ERRO:")
            print(resposta.text[:2000])

            relatorio.append(resposta.text[:5000])
            continue

        dados = resposta.json()

        if not dados.get("success"):
            print("A API retornou success=false")
            relatorio.append(
                json.dumps(dados, ensure_ascii=False)
            )
            continue

        resultado = dados["result"]

        print("Total disponível:", resultado.get("total"))

        print("\nCAMPOS DA API:")

        for campo in resultado.get("fields", []):
            print("-", campo["id"])

        registros = resultado.get("records", [])

        print("\nPRIMEIROS REGISTROS:")

        print(json.dumps(
            registros,
            indent=4,
            ensure_ascii=False
        ))

        relatorio.append(
            json.dumps(
                dados,
                indent=4,
                ensure_ascii=False
            )
        )

    except requests.RequestException as erro:

        print("ERRO DE CONEXAO:", erro)
        relatorio.append(f"ERRO: {erro}")

    except (ValueError, KeyError, TypeError) as erro:

        print("ERRO NO FORMATO DA RESPOSTA:", erro)
        relatorio.append(f"ERRO DE ESTRUTURA: {erro}")

Path("relatorios").mkdir(exist_ok=True)

Path("relatorios/diagnostico_ccee.txt").write_text(
    "\n".join(relatorio),
    encoding="utf-8"
)

print("\nDiagnostico finalizado!")
print("Arquivo salvo em relatorios/diagnostico_ccee.txt")
