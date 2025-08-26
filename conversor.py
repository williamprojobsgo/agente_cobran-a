import pdfplumber
import os
import csv
from pathlib import Path

def extrair_dados_pdf(pdf_path):
    """Extrai código, cliente e saldo do PDF."""
    dados = []
    with pdfplumber.open(pdf_path) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text().split("\n")
            for linha in texto:
                partes = linha.split()
                if len(partes) >= 3 and partes[0].isdigit() and len(partes[0]) == 4:
                    try:
                        codigo = partes[0]
                        saldo = partes[-1].replace(".", "").replace(",", ".")
                        saldo = float(saldo)
                        cliente = " ".join(partes[1:-1])
                        dados.append((codigo, cliente, saldo))
                    except ValueError:
                        pass
    return dados

def salvar_csv(dados, csv_path):
    """Salva os dados no formato CSV."""
    with open(csv_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["codigo", "cliente", "saldo"])
        writer.writerows(dados)
    print(f"[✔] CSV salvo em: {csv_path}")

def processar_um_pdf():
    pdf_path = input("Digite o caminho do PDF: ").strip('"')
    if not os.path.exists(pdf_path):
        print("[ERRO] PDF não encontrado.")
        return
    dados = extrair_dados_pdf(pdf_path)
    if not dados:
        print("[AVISO] Nenhum dado encontrado no PDF.")
        return
    csv_path = Path(pdf_path).with_suffix(".csv")
    salvar_csv(dados, csv_path)

def processar_pasta():
    pasta = input("Digite o caminho da pasta com PDFs: ").strip('"')
    if not os.path.isdir(pasta):
        print("[ERRO] Pasta não encontrada.")
        return
    for arquivo in os.listdir(pasta):
        if arquivo.lower().endswith(".pdf"):
            pdf_path = os.path.join(pasta, arquivo)
            print(f"[PROCESSANDO] {arquivo}")
            dados = extrair_dados_pdf(pdf_path)
            if dados:
                csv_path = Path(pdf_path).with_suffix(".csv")
                salvar_csv(dados, csv_path)

def main():
    print("=== CONVERSOR DE PDF PARA CSV - COBRANÇAS ===")
    print("1 - Converter apenas 1 PDF")
    print("2 - Converter todos os PDFs de uma pasta")
    opcao = input("Escolha (1 ou 2): ").strip()

    if opcao == "1":
        processar_um_pdf()
    elif opcao == "2":
        processar_pasta()
    else:
        print("[ERRO] Opção inválida.")

if __name__ == "__main__":
    main()
