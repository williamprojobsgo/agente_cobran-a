# MENSEGER (Automação de Cobrança)

Automatiza cobranças via WhatsApp Desktop a partir de relatórios (PDF/CSV/TXT).
- Consolida saldos e contatos
- Abre WhatsApp Desktop, cola ou digita a mensagem (com Enter opcional)
- Mantém log e base de telefones
- Pronto para integrar com Power BI / Excel / SQL

## Como rodar
pip install -r requirements.txt
python .\cobranca.py   # ajuste para o nome do seu arquivo principal

## Estrutura
data/raw        # fontes brutas (NÃO versionar)
data/processed  # saídas tratadas / CSVs p/ BI
bi/             # .pbix (use Git LFS se necessário)
sql/            # scripts .sql de apoio
notebooks/      # análises exploratórias
docs/           # prints para README/portfólio