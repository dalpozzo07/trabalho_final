
import requests

RECURSOS = {
    2025: "https://pda-download.ccee.org.br/korJMXwpSLGyVlpRMQWduA/content",
    2026: "https://pda-download.ccee.org.br/6A5wq97KTCWv_bvs3CqsQQ/content"
}

def testar_download(ano, url):
    print(f"\nTestando PLD {ano}...")

    try:
        with requests.get(
            url,
            stream=True,
            timeout=(15, 60)
        ) as resposta:

            print("Status HTTP:", resposta.status_code)
            print(
                "Tipo:",
                resposta.headers.get("Content-Type")
            )

            resposta.raise_for_status()

            primeiro_bloco = next(
                resposta.iter_content(chunk_size=1024),
                b""
            )

            print("Primeiros bytes recebidos:")
            print(primeiro_bloco[:200])

            if not primeiro_bloco:
                print("Resposta vazia.")
                return

            print(f"PLD {ano}: ACESSO FUNCIONANDO!")

    except requests.RequestException as erro:
        print(f"Erro no PLD {ano}: {erro}")


for ano, url in RECURSOS.items():
    testar_download(ano, url)
