# cobranca.py — Agente de Cobrança (GUI) • WhatsApp Desktop
# Versão: 2025-08-13

import os
import re
import csv
import time
import threading
import urllib.parse
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

import pandas as pd

# ====== GUI (Tkinter)
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ===================== CONFIG =====================
PAIS_DDI = "55"                   # Brasil
DEFAULT_DELAY = 7                 # segundos p/ abrir conversa
SAIDAS = Path("saidas"); SAIDAS.mkdir(exist_ok=True)
DEFAULT_TEL_CSV = SAIDAS / "telefones_salvos.csv"  # onde salvamos telefones (Codigo4d;Telefone)

MENSAGEM_BASE = (
    "Prezado(a),\n\n"
    "Identificamos que há valores pendentes com a Extra Carne.\n\n"
    "Cliente: {codigo4d} - {cliente}\n"
    "Saldo pendente: *R$ {saldo_brl}*\n\n"
    "Solicitamos, por gentileza, que realize o pagamento o quanto antes "
    "para evitar restrições comerciais.\n\n"
    "Pedimos que nos envie o comprovante de pagamento via WhatsApp para agilizar a baixa do título.\n\n"
    "Atenciosamente,\n"
    "Departamento Financeiro - Extra Carne"
)

# ===================== REGEX / HELPERS =====================
RE_CLIENTE = re.compile(r"^\s*(\d{4})\s+([A-Z0-9ÁÉÍÓÚÂÊÔÃÕÇ'()\-.,/& ]+?)\s*$", re.I)
RE_VALOR_BR = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})")

def br_to_float(s: str) -> float:
    return float(str(s).replace(".", "").replace(",", "."))

def formata_brl(valor: float) -> str:
    """1234.56 -> '1.234,56'"""
    s = f"{valor:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def _only_digits(s: str) -> str:
    return "".join(ch for ch in str(s) if ch.isdigit())

def _norm_code(s: str) -> str:
    d = _only_digits(s)
    return d.zfill(4) if d else ""

# ===================== LEITURA PDF =====================
def extrai_texto_pdf(pdf_path: Path) -> List[str]:
    import pdfplumber
    linhas: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text(layout=True) or page.extract_text() or ""
            for ln in txt.splitlines():
                ln = ln.strip()
                if ln:
                    linhas.append(ln)
    return linhas

# ===================== LEITURA CSV/TXT robusta =====================
import csv as _csv

def _read_csv_any(path: Path) -> pd.DataFrame:
    with open(path, 'rb') as fb:
        head = fb.read(4096)
    sep = ';'
    for enc in ('utf-8', 'cp1252', 'latin-1'):
        try:
            sample = head.decode(enc, errors="strict")
            try:
                dialect = _csv.Sniffer().sniff(sample, delimiters=',;|\t')
                sep = dialect.delimiter
            except Exception:
                sep = ';' if sample.count(';') >= sample.count(',') else ','
            return pd.read_csv(path, sep=sep, encoding=enc, engine='python')
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, sep=sep, encoding='latin-1', engine='python', errors='ignore')

def extrai_linhas_csv_txt(path: Path) -> List[str]:
    try:
        df = _read_csv_any(path)
    except Exception:
        for enc in ('utf-8', 'cp1252', 'latin-1'):
            try:
                txt = path.read_text(encoding=enc)
                return [ln.strip() for ln in txt.splitlines() if ln.strip()]
            except UnicodeDecodeError:
                continue
        txt = path.read_text(encoding='latin-1', errors='ignore')
        return [ln.strip() for ln in txt.splitlines() if ln.strip()]

    linhas: List[str] = []
    for _, row in df.iterrows():
        partes = [str(x).strip() for x in row.values if pd.notna(x) and str(x).strip() != ""]
        if partes:
            linhas.append(" ".join(partes))
    return linhas

# ===================== PARSER (linhas → clientes/saldos) =====================
def extrai_clientes_saldos_de_linhas(linhas: List[str]) -> pd.DataFrame:
    registros = []
    cliente_atual: Optional[Tuple[str, str]] = None
    ultimo_valor: Optional[float] = None

    for ln in linhas:
        m_cli = RE_CLIENTE.match(ln)
        if m_cli:
            if cliente_atual and ultimo_valor is not None:
                registros.append({"Codigo4d": cliente_atual[0], "Cliente": cliente_atual[1], "Saldo": ultimo_valor})
            cliente_atual = (m_cli.group(1).strip(), m_cli.group(2).strip())
            ultimo_valor = None
            continue

        if cliente_atual:
            vals = RE_VALOR_BR.findall(ln)
            if vals:
                ultimo_valor = br_to_float(vals[-1])
            if ("saldo" in ln.lower() or "total" in ln.lower()) and vals:
                ultimo_valor = br_to_float(vals[-1])

    if cliente_atual and ultimo_valor is not None:
        registros.append({"Codigo4d": cliente_atual[0], "Cliente": cliente_atual[1], "Saldo": ultimo_valor})

    df = pd.DataFrame(registros, columns=["Codigo4d", "Cliente", "Saldo"]).dropna()
    df = df.drop_duplicates(subset=["Codigo4d", "Cliente", "Saldo"]).reset_index(drop=True)
    # NORMALIZA Codigo4d
    if "Codigo4d" in df.columns:
        df["Codigo4d"] = df["Codigo4d"].astype(str).map(_norm_code)
    return df

def processa_arquivo(entrada: Path, vendedor_hint: Optional[str] = None) -> pd.DataFrame:
    ext = entrada.suffix.lower()
    if ext == ".pdf":
        linhas = extrai_texto_pdf(entrada)
    else:
        linhas = extrai_linhas_csv_txt(entrada)

    df = extrai_clientes_saldos_de_linhas(linhas)
    if df.empty:
        raise RuntimeError(
            f"Não consegui extrair do arquivo: {entrada.name}. "
            "Me envie 5–10 linhas do conteúdo para ajustar a regex."
        )
    df["VendedorArquivo"] = vendedor_hint or entrada.stem
    # NORMALIZA Codigo4d (garantia extra)
    if "Codigo4d" in df.columns:
        df["Codigo4d"] = df["Codigo4d"].astype(str).map(_norm_code)
    return df

# ===================== WHATSAPP DESKTOP (robusto) =====================
def abre_whatsapp_desktop(telefone: str, mensagem: str,
                          delay: int,
                          auto_paste: bool,
                          auto_press_enter: bool,
                          auto_type_fallback: bool,
                          focar_janela: bool) -> tuple[str, str]:
    """
    Abre WhatsApp Desktop e garante texto na caixa:
    - copia para o clipboard ANTES de abrir
    - tenta focar a janela (pygetwindow opcional)
    - cola (Ctrl+V); se falhar, digita (fallback)
    - envio manual por padrão (Enter), salvo auto_press_enter=True
    Retorna (canal, url_usada)
    """
    # 1) Copia ANTES (mais confiável)
    try:
        import pyperclip
        pyperclip.copy(mensagem)
    except Exception:
        pass

    texto = urllib.parse.quote(mensagem, safe='')
    url_app = f"whatsapp://send?phone={PAIS_DDI}{telefone}&text={texto}"
    url_web = f"https://wa.me/{PAIS_DDI}{telefone}?text={texto}"

    # 2) Abre Desktop
    try:
        os.startfile(url_app)
        canal, url = "DESKTOP", url_app
    except Exception:
        webbrowser.open(url_web)
        return "WEB_FALLBACK", url_web

    # 3) Aguardar abertura
    time.sleep(max(2, delay))

    # 4) Focar janela (opcional)
    if focar_janela:
        try:
            import pygetwindow as gw
            wins = [w for w in gw.getAllTitles() if "WhatsApp" in w]
            if wins:
                w = gw.getWindowsWithTitle(wins[0])[0]
                if w and not w.isActive:
                    w.activate()
                    time.sleep(0.5)
        except Exception:
            pass

    # 5) Tenta colar
    colou = False
    try:
        import pyautogui
        pyautogui.PAUSE = 0.05
        pyautogui.FAILSAFE = False
        pyautogui.click()
        time.sleep(0.1)
        if auto_paste:
            pyautogui.hotkey('ctrl', 'v')
            colou = True
    except Exception:
        colou = False

    # 6) Fallback: digitar
    if not colou and auto_type_fallback:
        try:
            import pyautogui
            pyautogui.typewrite(mensagem, interval=0.005)
            colou = True
        except Exception:
            pass

    # 7) Enviar automático (opcional)
    if colou and auto_press_enter:
        try:
            import pyautogui
            pyautogui.press('enter')
        except Exception:
            pass

    return canal, url

# ===================== GUI (Tkinter) =====================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Agente de Cobrança • Extra Carne")
        self.geometry("980x650")
        self.minsize(980, 650)

        # Estado
        self.modo = tk.StringVar(value="arquivo")
        self.caminho_arquivo = tk.StringVar(value="")
        self.caminho_pasta = tk.StringVar(value="")
        self.delay = tk.IntVar(value=DEFAULT_DELAY)
        self.auto_paste = tk.BooleanVar(value=True)
        self.auto_enter = tk.BooleanVar(value=False)
        self.auto_type_fallback = tk.BooleanVar(value=True)
        self.focus_wa = tk.BooleanVar(value=True)
        self.vendedor_hint = tk.StringVar(value="")
        self.msg_base = tk.StringVar(value=MENSAGEM_BASE)

        # Telefones
        self.telefones_path = tk.StringVar(value=str(DEFAULT_TEL_CSV if DEFAULT_TEL_CSV.exists() else ""))
        self.telefones_map: dict[str, str] = self._carrega_telefones(Path(self.telefones_path.get()) if self.telefones_path.get() else DEFAULT_TEL_CSV)

        self.df_consolidado: Optional[pd.DataFrame] = None
        self.origem_label: Optional[str] = None

        self._build_ui()

        if self.telefones_map:
            self.log(f"[Telefones] {len(self.telefones_map)} números carregados.")

    # ---------- UI ----------
    def _build_ui(self):
        frm_top = ttk.Frame(self); frm_top.pack(fill="x", padx=12, pady=8)

        ttk.Label(frm_top, text="Modo:").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(frm_top, text="1 arquivo (PDF/CSV/TXT)", variable=self.modo, value="arquivo").grid(row=0, column=1, sticky="w", padx=6)
        ttk.Radiobutton(frm_top, text="Pasta (vários arquivos)", variable=self.modo, value="pasta").grid(row=0, column=2, sticky="w", padx=6)

        ttk.Label(frm_top, text="Vendedor/Origem:").grid(row=1, column=0, sticky="w", pady=(6,0))
        ttk.Entry(frm_top, textvariable=self.vendedor_hint, width=40).grid(row=1, column=1, columnspan=2, sticky="we", pady=(6,0))

        # Seleção
        frm_sel = ttk.LabelFrame(self, text="Seleção de entrada"); frm_sel.pack(fill="x", padx=12, pady=8)
        self.entry_arquivo = ttk.Entry(frm_sel, textvariable=self.caminho_arquivo, width=80)
        self.entry_pasta = ttk.Entry(frm_sel, textvariable=self.caminho_pasta, width=80)
        ttk.Button(frm_sel, text="Escolher arquivo…", command=self.pick_arquivo).grid(row=0, column=0, padx=4, pady=6, sticky="w")
        self.entry_arquivo.grid(row=0, column=1, padx=4, pady=6, sticky="we")
        ttk.Button(frm_sel, text="Escolher pasta…", command=self.pick_pasta).grid(row=1, column=0, padx=4, pady=6, sticky="w")
        self.entry_pasta.grid(row=1, column=1, padx=4, pady=6, sticky="we")
        frm_sel.columnconfigure(1, weight=1)

        # Telefones
        frm_tel = ttk.LabelFrame(self, text="Telefones (opcional: CSV Codigo4d;Telefone)"); frm_tel.pack(fill="x", padx=12, pady=8)
        ttk.Button(frm_tel, text="Importar CSV de telefones…", command=self.pick_telefones).grid(row=0, column=0, padx=4, pady=6, sticky="w")
        ttk.Entry(frm_tel, textvariable=self.telefones_path, width=80).grid(row=0, column=1, padx=4, pady=6, sticky="we")
        frm_tel.columnconfigure(1, weight=1)

        # Opções
        frm_opts = ttk.LabelFrame(self, text="Envio (WhatsApp Desktop)"); frm_opts.pack(fill="x", padx=12, pady=8)
        ttk.Label(frm_opts, text="Aguardar (s):").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(frm_opts, from_=2, to=15, textvariable=self.delay, width=5).grid(row=0, column=1, sticky="w", padx=(4,10))
        ttk.Checkbutton(frm_opts, text="Colar automaticamente (Ctrl+V)", variable=self.auto_paste).grid(row=0, column=2, sticky="w", padx=10)
        ttk.Checkbutton(frm_opts, text="(Avançado) Enviar automático (Enter)", variable=self.auto_enter).grid(row=0, column=3, sticky="w", padx=10)
        ttk.Checkbutton(frm_opts, text="Fallback: digitar texto se não colar", variable=self.auto_type_fallback).grid(row=1, column=2, sticky="w", padx=10)
        ttk.Checkbutton(frm_opts, text="Tentar focar janela do WhatsApp", variable=self.focus_wa).grid(row=1, column=3, sticky="w", padx=10)

        # Mensagem
        frm_msg = ttk.LabelFrame(self, text="Mensagem base (usa {codigo4d}, {cliente}, {saldo_brl})")
        frm_msg.pack(fill="both", padx=12, pady=8, expand=True)
        self.txt_msg = tk.Text(frm_msg, height=8, wrap="word")
        self.txt_msg.insert("1.0", self.msg_base.get())
        self.txt_msg.pack(fill="both", expand=True, padx=6, pady=6)

        # Ações
        frm_btn = ttk.Frame(self); frm_btn.pack(fill="x", padx=12, pady=8)
        ttk.Button(frm_btn, text="1) Converter p/ Consolidado", command=self.run_converter).pack(side="left", padx=4)
        ttk.Button(frm_btn, text="2) Iniciar Cobrança", command=self.run_cobranca).pack(side="left", padx=4)

        # Log
        frm_log = ttk.LabelFrame(self, text="Log"); frm_log.pack(fill="both", padx=12, pady=8, expand=True)
        self.txt_log = tk.Text(frm_log, height=10, wrap="word")
        self.txt_log.pack(fill="both", expand=True, padx=6, pady=6)

    # ---------- UI helpers ----------
    def log(self, msg: str):
        self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end")
        self.update_idletasks()

    def pick_arquivo(self):
        f = filedialog.askopenfilename(title="Escolha um PDF/CSV/TXT",
                                       filetypes=[("Relatórios", "*.pdf;*.csv;*.txt"), ("Todos", "*.*")])
        if f:
            self.caminho_arquivo.set(f)

    def pick_pasta(self):
        d = filedialog.askdirectory(title="Escolha a pasta com relatórios")
        if d:
            self.caminho_pasta.set(d)

    def pick_telefones(self):
        f = filedialog.askopenfilename(title="CSV de Telefones (Codigo4d;Telefone)", filetypes=[("CSV", "*.csv")])
        if not f:
            return
        self.telefones_path.set(f)
        self.telefones_map = self._carrega_telefones(Path(f))
        self.log(f"[Telefones] Importados: {len(self.telefones_map)}")

    # ---------- Telefones persistentes ----------
    def _carrega_telefones(self, caminho: Path) -> dict[str, str]:
        mapa: dict[str, str] = {}
        if not caminho.exists():
            return mapa
        try:
            df = pd.read_csv(caminho, sep=";", encoding="utf-8")
        except Exception:
            df = pd.read_csv(caminho, sep=";", encoding="latin-1")

        if "Codigo4d" not in df.columns or "Telefone" not in df.columns:
            return mapa

        df["Codigo4d"] = df["Codigo4d"].astype(str).map(_norm_code)
        df["Telefone"] = df["Telefone"].astype(str).str.strip()
        df = df[(df["Codigo4d"] != "") & (df["Telefone"] != "")]
        for _, r in df.iterrows():
            mapa[r["Codigo4d"]] = r["Telefone"]
        return mapa

    def _salva_telefone_csv(self, codigo: str, telefone: str):
        """
        Atualiza/insere telefone no CSV em uso (self.telefones_path) ou no DEFAULT_TEL_CSV.
        Chave SEMPRE = Codigo4d normalizado (4 dígitos).
        """
        telefone = str(telefone).strip()
        codigo_n = _norm_code(codigo)
        if not telefone or not codigo_n:
            return

        csv_path = Path(self.telefones_path.get()) if self.telefones_path.get() else DEFAULT_TEL_CSV

        if csv_path.exists():
            try:
                df_tel = pd.read_csv(csv_path, sep=";", encoding="utf-8")
            except Exception:
                df_tel = pd.read_csv(csv_path, sep=";", encoding="latin-1")
        else:
            df_tel = pd.DataFrame(columns=["Codigo4d", "Telefone"])

        if "Codigo4d" in df_tel.columns:
            df_tel["Codigo4d"] = df_tel["Codigo4d"].astype(str).map(_norm_code)
        else:
            df_tel = pd.DataFrame(columns=["Codigo4d", "Telefone"])

        df_tel = df_tel[df_tel["Codigo4d"] != codigo_n]
        df_tel = pd.concat([df_tel, pd.DataFrame([{"Codigo4d": codigo_n, "Telefone": telefone}])], ignore_index=True)

        df_tel.to_csv(csv_path, sep=";", index=False, encoding="utf-8-sig")
        self.telefones_map[codigo_n] = telefone
        self.telefones_path.set(str(csv_path))
        self.log(f"[Telefone salvo] {codigo_n} → {telefone} ({csv_path.name})")

    # ---------- Conversão ----------
    def converter(self) -> tuple[Optional[pd.DataFrame], Optional[Path]]:
        modo = self.modo.get()
        vend = self.vendedor_hint.get().strip()
        if modo == "arquivo":
            p = Path(self.caminho_arquivo.get().strip().strip('"'))
            if not p.exists():
                messagebox.showerror("Erro", "Selecione um arquivo válido.")
                return None, None
            self.log(f"[LENDO] {p.name}")
            df = processa_arquivo(p, vendedor_hint=vend or p.stem)
            origem = p
        else:
            d = Path(self.caminho_pasta.get().strip().strip('"'))
            if not d.exists() or not d.is_dir():
                messagebox.showerror("Erro", "Selecione uma pasta válida.")
                return None, None
            frames = []
            for arq in d.iterdir():
                if arq.suffix.lower() in (".pdf", ".csv", ".txt"):
                    self.log(f"[PROCESSANDO] {arq.name}")
                    try:
                        frames.append(processa_arquivo(arq, vendedor_hint=vend or arq.stem))
                    except Exception as e:
                        self.log(f"   ⚠ {arq.name}: {e}")
            if not frames:
                messagebox.showwarning("Aviso", "Nenhum arquivo válido encontrado na pasta.")
                return None, None
            df = pd.concat(frames, ignore_index=True)
            origem = d

        # salvar consolidado
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = SAIDAS / f"consolidado_cobranca_{stamp}.csv"
        df.to_csv(out, index=False, sep=";", encoding="utf-8-sig")
        self.log(f"✅ Consolidado salvo: {out.resolve()}")

        # guarda para cobrança e normaliza código
        if "Codigo4d" in df.columns:
            df["Codigo4d"] = df["Codigo4d"].astype(str).map(_norm_code)

        return df, origem

    def run_converter(self):
        try:
            self.msg_base.set(self.txt_msg.get("1.0", "end").strip())
            df, origem = self.converter()
            if df is not None:
                self.df_consolidado = df
                self.origem_label = str(origem)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    # ---------- Cobrança ----------
    def cobrar(self, df: pd.DataFrame, origem: Path):
        df2 = df.copy()
        if "Codigo4d" in df2.columns:
            df2["Codigo4d"] = df2["Codigo4d"].astype(str).map(_norm_code)

        if not pd.api.types.is_numeric_dtype(df2["Saldo"]):
            df2["Saldo"] = pd.to_numeric(df2["Saldo"], errors="coerce").fillna(0.0)
        df2 = df2[df2["Saldo"] > 0].reset_index(drop=True)
        if df2.empty:
            self.log("Nenhum cliente com saldo > 0 para cobrar.")
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = SAIDAS / f"log_cobrancas_{stamp}.csv"
        headers = ["timestamp", "origem", "vendedor_arquivo", "codigo4d", "cliente",
                   "saldo", "telefone", "status", "canal", "url"]

        enviados = aberto = pulados = 0
        delay = max(2, int(self.delay.get()))
        auto_paste = bool(self.auto_paste.get())
        auto_enter = bool(self.auto_enter.get())
        auto_type_fallback = bool(self.auto_type_fallback.get())
        focar_janela = bool(self.focus_wa.get())
        msg_tpl = self.msg_base.get()

        with open(log_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(headers)

            self.log("=== ENVIO VIA WHATSAPP DESKTOP ===")
            self.log("Dica: se a mensagem não aparecer, pressione Ctrl+V (o texto já está no clipboard).")

            for _, r in df2.iterrows():
                codigo = _norm_code(r["Codigo4d"])
                cliente = str(r["Cliente"])
                saldo = float(r["Saldo"])
                vend = str(r.get("VendedorArquivo", ""))

                # telefone salvo?
                telefone = self.telefones_map.get(codigo, "").strip()
                if not telefone:
                    telefone = self.prompt_telefone(codigo, cliente)
                    if telefone:
                        self._salva_telefone_csv(codigo, telefone)

                if not telefone:
                    pulados += 1
                    w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(origem), vend, codigo, cliente,
                                f"{saldo:.2f}".replace(".", ","), "", "PULADO", "", ""])
                    self.log(f"[PULADO] {codigo} - {cliente}")
                    continue

                # Mensagem (blindada)
                valor_brl = formata_brl(saldo)
                tpl = msg_tpl.replace("{saldo:,.2f}", "{saldo_brl}").replace("{saldo: .2f}", "{saldo_brl}")
                try:
                    msg = tpl.format(codigo4d=codigo, cliente=cliente, saldo_brl=valor_brl, saldo=valor_brl)
                except Exception:
                    msg = f"Prezado(a),\n\nCliente: {codigo} - {cliente}\nSaldo pendente: R$ {valor_brl}\nPor gentileza, regularizar o quanto antes.\n"

                canal, url = abre_whatsapp_desktop(
                    telefone, msg, delay, auto_paste, auto_enter,
                    auto_type_fallback, focar_janela
                )
                self.log(f"Abrindo WhatsApp ({canal}) para {codigo} - {cliente} ...")

                # Confirmação manual
                ok = messagebox.askyesno("Confirmação", f"Mensagem enviada para {codigo} - {cliente}?")
                status = "ENVIADO" if ok else "ABERTO_NAO_ENVIADO"
                if ok: enviados += 1
                else:  aberto += 1

                w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(origem), vend, codigo, cliente,
                            f"{saldo:.2f}".replace(".", ","), telefone, status, canal, url])

        self.log("=== RESUMO ===")
        total = len(df2)
        self.log(f"Total para cobrar: {total}")
        self.log(f"Enviados: {enviados}")
        self.log(f"Abriram e não enviaram: {aberto}")
        self.log(f"Pulados: {pulados}")
        self.log(f"Log salvo em: {log_path.resolve()}")

    def run_cobranca(self):
        if self.df_consolidado is None:
            messagebox.showinfo("Antes", "Use o botão '1) Converter p/ Consolidado' primeiro.")
            return
        threading.Thread(target=self.cobrar, args=(self.df_consolidado, Path(self.origem_label)), daemon=True).start()

    def prompt_telefone(self, codigo: str, cliente: str) -> str:
        dlg = tk.Toplevel(self)
        dlg.title(f"Telefone de {codigo} - {cliente}")
        dlg.grab_set()
        ttk.Label(dlg, text=f"Informe o telefone (apenas números, com DDD):").pack(padx=12, pady=(12,4))
        var = tk.StringVar()
        ent = ttk.Entry(dlg, textvariable=var, width=30)
        ent.pack(padx=12, pady=6)
        ent.focus_set()
        out = {"tel": ""}

        def ok():
            out["tel"] = var.get().strip()
            dlg.destroy()
        def cancelar():
            out["tel"] = ""
            dlg.destroy()

        frm = ttk.Frame(dlg); frm.pack(pady=8)
        ttk.Button(frm, text="OK", command=ok).pack(side="left", padx=6)
        ttk.Button(frm, text="Pular", command=cancelar).pack(side="left", padx=6)
        dlg.wait_window()

        return out["tel"]

# ---------- main ----------
def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
