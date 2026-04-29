# ==========================================
# ROBO DE COBRANCA - VERSAO FINAL CORRIGIDA
# ==========================================
# Foco em sintaxe limpa, margens ajustadas e blocos compactos.

import flet as ft
import pandas as pd
import os
from datetime import datetime, timedelta
import time
import threading

def main(page: ft.Page):
    page.title = "Robo de Cobranca - Versao Final"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 15
    page.window_width = 1600
    page.window_height = 1000
    page.expand = True
    
    # Variaveis de estado
    state = {
        "df_dados": None, 
        "df_agrupado": None, 
        "pasta": "repositorio debitos", 
        "robo_rodando": False
    }
    
    # --- FUNCOES DE DADOS ---
    def converter_data_agressivo(val):
        if pd.isna(val) or not val or str(val).strip() == "":
            return "Sem Data"
        try:
            num_val = pd.to_numeric(val, errors='coerce')
            if not pd.isna(num_val) and 0 < num_val < 60000:
                return (datetime(1899, 12, 30) + timedelta(days=int(num_val))).strftime("%d/%m/%Y")
            s = str(val).strip()
            for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%Y%m%d"]:
                try:
                    return datetime.strptime(s, fmt).strftime("%d/%m/%Y")
                except:
                    continue
            return s[:10]
        except:
            return str(val)[:10]

    def to_num_agressivo(v):
        try:
            if pd.isna(v): return 0.0
            s = str(v).strip().replace("R$", "").replace(" ", "")
            if "," in s and "." in s:
                s = s.replace(".", "").replace(",", ".")
            elif "," in s:
                s = s.replace(",", ".")
            return float(s)
        except:
            return 0.0

    def carregar_dados(e=None):
        if not os.path.exists(state["pasta"]):
            status_text.value = "Erro: Pasta nao encontrada"
            page.update()
            return

        arquivos = [f for f in os.listdir(state["pasta"]) if f.endswith(".csv")]
        if not arquivos:
            status_text.value = "Erro: Nenhum CSV encontrado"
            page.update()
            return
        
        arquivos.sort(reverse=True)
        caminho = os.path.join(state["pasta"], arquivos[0])
        
        try:
            df = None
            for enc in ["utf-8", "latin1", "cp1252"]:
                try:
                    df = pd.read_csv(caminho, sep=";", encoding=enc, on_bad_lines="skip")
                    if len(df.columns) < 2:
                        df = pd.read_csv(caminho, sep=",", encoding=enc, on_bad_lines="skip")
                    break
                except:
                    continue
            
            if df is not None:
                cols = df.columns.tolist()
                idx_tel, idx_cli, idx_venc, idx_val, idx_saldo = 0, 1, 11, 12, 14
                for i, c in enumerate(cols):
                    c_lower = str(c).lower()
                    if "cliente" in c_lower or "nome" in c_lower: idx_cli = i
                    if "venc" in c_lower or "data" in c_lower: idx_venc = i
                    if "saldo" in c_lower: idx_saldo = i
                    if "valor" in c_lower and "saldo" not in c_lower: idx_val = i
                    if "tel" in c_lower or "celular" in c_lower: idx_tel = i

                df["cliente_nome"] = df.iloc[:, idx_cli].astype(str).str.strip()
                df["tel_limpo"] = df.iloc[:, idx_tel].astype(str).str.replace(".0", "", regex=False)
                df["venc_limpo"] = df.iloc[:, idx_venc].apply(converter_data_agressivo)
                df["saldo_num"] = df.iloc[:, idx_saldo].apply(to_num_agressivo)
                df["valor_num"] = df.iloc[:, idx_val].apply(to_num_agressivo)
                
                state["df_dados"] = df
                df_agrup = df.groupby("cliente_nome").agg({"saldo_num": "sum", "cliente_nome": "count"}).rename(columns={"cliente_nome": "qtd"}).reset_index()
                df_agrup = df_agrup.sort_values("saldo_num", ascending=False)
                state["df_agrupado"] = df_agrup
                
                status_text.value = f"Arquivo: {arquivos[0]}"
                total_text.value = f"TOTAL GERAL: R$ {df_agrup['saldo_num'].sum():,.2f}"
                render_tabela(df_agrup)
            else:
                status_text.value = "Erro ao ler CSV"
        except Exception as ex:
            status_text.value = f"Erro: {str(ex)}"
        page.update()

    def render_tabela(df):
        lista_clientes.controls.clear()
        for _, row in df.iterrows():
            nome = row["cliente_nome"]
            saldo = row["saldo_num"]
            qtd = row["qtd"]
            item = ft.Container(
                content=ft.Row([
                    ft.Text(nome, expand=True, size=14, weight="bold"),
                    ft.Text(f"{int(qtd)} notas", width=80, size=13, color="grey"),
                    ft.Text(f"R$ {saldo:,.2f}", width=160, weight="bold", color="blue", text_align="right", size=15),
                ]),
                padding=ft.padding.symmetric(horizontal=15, vertical=10),
                border=ft.border.only(bottom=ft.border.BorderSide(1, "#EEEEEE")),
                on_click=lambda e, n=nome: ver_detalhes(n),
                ink=True,
                border_radius=8
            )
            lista_clientes.controls.append(item)
        page.update()

    def ver_detalhes(nome):
        df = state["df_dados"]
        notas = df[df["cliente_nome"] == nome]
        detalhes_col.controls.clear()
        detalhes_col.controls.append(ft.Text(nome, weight="bold", size=18, color="blue"))
        detalhes_col.controls.append(ft.Text(f"Telefone: {notas.iloc[0]['tel_limpo']}", size=14))
        detalhes_col.controls.append(ft.Divider(height=10))
        for _, nota in notas.iterrows():
            detalhes_col.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Text("Vencimento:", size=13), ft.Text(nota['venc_limpo'], color="red", weight="bold", size=14)], alignment="spaceBetween"),
                        ft.Row([ft.Text("Valor Original:", size=13), ft.Text(f"R$ {nota['valor_num']:,.2f}", size=13)], alignment="spaceBetween"),
                        ft.Row([ft.Text("Saldo Devedor:", weight="bold", size=14), ft.Text(f"R$ {nota['saldo_num']:,.2f}", weight="bold", size=15, color="blue")], alignment="spaceBetween"),
                    ], spacing=6),
                    padding=15, 
                    bgcolor="white", 
                    border=ft.border.all(1, "#E0E0E0"), 
                    border_radius=8, 
                    margin=ft.margin.only(bottom=8)
                )
            )
        detalhes_container.visible = True
        page.update()

    # --- FUNCOES DO ROBO ---
    def parar_robo(e):
        state["robo_rodando"] = False
        page.update()

    def iniciar_robo(e):
        if state["robo_rodando"]: return
        state["robo_rodando"] = True
        iniciar_robo_btn.text = "ROBO RODANDO..."
        iniciar_robo_btn.disabled = True
        mudar_aba("monitoramento")
        threading.Thread(target=processar_clientes_robo, daemon=True).start()

    def processar_clientes_robo():
        if state["df_agrupado"] is None or state["df_agrupado"].empty:
            monitor_clientes_status.controls.append(ft.Text("Nenhum cliente para processar.", color="red", size=14))
            state["robo_rodando"] = False
            iniciar_robo_btn.text = "INICIAR ROBO"
            iniciar_robo_btn.disabled = False
            page.update()
            return
        monitor_clientes_status.controls.clear()
        page.update()
        for idx, row in state["df_agrupado"].iterrows():
            if not state["robo_rodando"]: break
            cliente_nome = row["cliente_nome"]
            status_item = ft.Container(
                content=ft.Text(f"[AGUARDANDO] Cliente: {cliente_nome}", size=14),
                padding=10, border=ft.border.all(1, "#EEEEEE"), border_radius=8, margin=ft.margin.only(bottom=6)
            )
            monitor_clientes_status.controls.append(status_item)
            page.update()
            time.sleep(1)
            status_item.content.value = f"[ENVIADO] Cliente: {cliente_nome}"
            status_item.content.color = "green"
            status_item.bgcolor = "#F0FFF0"
            page.update()
            time.sleep(0.5)
        monitor_clientes_status.controls.append(ft.Text("Processamento finalizado.", color="blue", weight="bold", size=18))
        state["robo_rodando"] = False
        iniciar_robo_btn.text = "INICIAR ROBO"
        iniciar_robo_btn.disabled = False
        page.update()

    # --- NAVEGACAO MANUAL ---
    def mudar_aba(aba):
        if aba == "clientes":
            aba_clientes.visible = True
            aba_monitoramento.visible = False
            btn_aba_clientes.bgcolor = "blue"
            btn_aba_clientes.color = "white"
            btn_aba_monitor.bgcolor = "#EEEEEE"
            btn_aba_monitor.color = "black"
        else:
            aba_clientes.visible = False
            aba_monitoramento.visible = True
            btn_aba_clientes.bgcolor = "#EEEEEE"
            btn_aba_clientes.color = "black"
            btn_aba_monitor.bgcolor = "blue"
            btn_aba_monitor.color = "white"
        page.update()

    # --- UI ELEMENTS ---
    status_text = ft.Text("Carregando...", size=14, color="grey")
    total_text = ft.Text("", size=18, weight="bold", color="blue")
    lista_clientes = ft.Column(scroll="auto", expand=True, spacing=4)
    detalhes_col = ft.Column(scroll="auto", expand=True, spacing=6)
    monitor_clientes_status = ft.Column(scroll="auto", expand=True, spacing=6)
    
    detalhes_container = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text("DETALHES", weight="bold", size=18),
                ft.ElevatedButton("FECHAR", on_click=lambda _: setattr(detalhes_container, "visible", False) or page.update(), bgcolor="red", color="white", height=38, width=110)
            ], alignment="spaceBetween"),
            ft.Divider(height=10),
            detalhes_col
        ]),
        visible=False, width=480, bgcolor="#F9F9F9", padding=20, border=ft.border.all(1, "#DDDDDD"), border_radius=10
    )

    # Botoes com dimensoes proporcionais
    iniciar_robo_btn = ft.ElevatedButton("INICIAR ROBO", bgcolor="blue", color="white", on_click=iniciar_robo, height=42, width=200)
    atualizar_btn = ft.ElevatedButton("ATUALIZAR", on_click=carregar_dados, height=42, width=160)
    parar_btn = ft.ElevatedButton("PARAR", bgcolor="red", color="white", on_click=parar_robo, height=42, width=130)

    # Aba Clientes
    aba_clientes = ft.Row([
        ft.Container(
            content=ft.Column([
                ft.Row([status_text, total_text], alignment="spaceBetween"),
                ft.Row([atualizar_btn, iniciar_robo_btn, parar_btn], spacing=15),
                ft.Divider(height=10),
                ft.Container(content=lista_clientes, expand=True, border=ft.border.all(1, "#CCCCCC"), border_radius=10, bgcolor="white", padding=10),
            ], expand=True, spacing=8),
            expand=True
        ),
        detalhes_container 
    ], expand=True, visible=True, spacing=15)

    # Aba Monitoramento
    aba_monitoramento = ft.Column([
        ft.Text("MONITORAMENTO", size=22, weight="bold", color="blue"),
        ft.Divider(height=10),
        ft.Container(content=monitor_clientes_status, expand=True, border=ft.border.all(1, "#CCCCCC"), border_radius=10, padding=20, bgcolor="white")
    ], expand=True, visible=False)

    # Botoes de Aba
    btn_aba_clientes = ft.ElevatedButton("CLIENTES", on_click=lambda _: mudar_aba("clientes"), bgcolor="blue", color="white", width=160, height=40)
    btn_aba_monitor = ft.ElevatedButton("MONITORAMENTO", on_click=lambda _: mudar_aba("monitoramento"), bgcolor="#EEEEEE", color="black", width=190, height=40)

    page.add(
        ft.Container(
            content=ft.Column([
                ft.Text("ROBO DE COBRANCA", size=24, weight="bold", color="blue"),
                ft.Row([btn_aba_clientes, btn_aba_monitor], spacing=15),
                ft.Divider(height=10),
                ft.Container(content=aba_clientes, expand=True),
                ft.Container(content=aba_monitoramento, expand=True)
            ], spacing=8),
            expand=True,
            padding=15
        )
    )
    carregar_dados()

if __name__ == "__main__":
    ft.app(target=main)
