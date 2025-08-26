# MENSEGER (Automa��o de Cobran�a)

Automatiza cobran�as via WhatsApp Desktop a partir de relat�rios (PDF/CSV/TXT).
- Consolida saldos e contatos
- Abre WhatsApp Desktop, cola ou digita a mensagem (com Enter opcional)
- Mant�m log e base de telefones
- Pronto para integrar com Power BI / Excel / SQL

## Como rodar
pip install -r requirements.txt
python .\cobranca.py   # ajuste para o nome do seu arquivo principal

## Estrutura
data/raw        # fontes brutas (N�O versionar)
data/processed  # sa�das tratadas / CSVs p/ BI
bi/             # .pbix (use Git LFS se necess�rio)
sql/            # scripts .sql de apoio
notebooks/      # an�lises explorat�rias
docs/           # prints para README/portf�lio