"""
EvoLink - versão enxuta (CustomTkinter) com banco de dados SQLite e layout responsivo

Arquivos (deixe na MESMA pasta):  evolink_app.py  +  banco.py
Como executar:  pip install customtkinter   ->   python evolink_app.py

Layout automático:
  - janela larga (>= 760 px)   -> modo COMPUTADOR (menu lateral)
  - janela estreita (< 760 px) -> modo CELULAR (barra superior + menu embaixo)
Também dá para forçar o modo em  Usuário > Visual do app.
"""
import sqlite3
from datetime import datetime
from tkinter import font as tkfont
from tkinter import messagebox

import customtkinter as ctk

import banco

# ---------------------------------------------------------------- cores (iguais ao EvoLink web)
NAVY950, NAVY900, NAVY800 = "#0a1428", "#0d1b35", "#122343"
NAV_HOVER, NAV_ATIVO, NAV_BORDA = "#16284a", "#1a3262", "#2f4f93"
BLUE500, BLUE400 = "#3b6fe0", "#5c8bf0"
INK, INK_DIM = "#e7ecf7", "#93a1c2"
PAPER, CARD, LINE = "#f3f5fa", "#ffffff", "#e2e6f0"
TEXTO, TEXTO2 = "#1b2440", "#6b7593"
VERDE, VERMELHO, AMBAR = "#2fa66a", "#e05a5a", "#e0a13b"

BREAKPOINT = 760  # abaixo dessa largura (px) o app usa o layout de celular

# (chave, ícone, texto no menu lateral, texto curto no menu do celular)
ITENS_MENU = [
    ("usuario", "👤", "Usuário", "Usuário"),
    ("equipamentos", "💻", "Equipamentos", "Equip."),
    ("chamado", "🆕", "Novo chamado", "Novo"),
    ("defeitos", "🛠", "Defeitos e soluções", "Soluções"),
    ("pagamentos", "💳", "Pagamentos", "Pagar"),
]

# cores dos selos de situação do chamado: (fundo, texto)
COR_SITUACAO = {
    "Aberto": ("#e8effd", "#2f57b8"),
    "Em andamento": ("#fff4e0", "#a8701a"),
    "Aguardando peça": ("#fff4e0", "#a8701a"),
    "Resolvido": ("#e6f6ee", "#1f8a55"),
    "Cancelado": ("#eef1f8", "#6b7593"),
}
ITEM_TECNICO = ("tecnico", "🧰", "Painel do técnico", "Painel")
SEM_CHAMADO = "Sem chamado (plano / mensalidade)"


# ---------------------------------------------------------------- utilidades
def brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_data(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return iso or ""


def numero(texto, padrao=None):
    """Converte '80,50' em 80.5. Retorna `padrao` se estiver vazio; ValueError se inválido."""
    texto = texto.strip().replace(",", ".")
    if not texto:
        if padrao is None:
            raise ValueError
        return padrao
    return float(texto)


def texto_diagnostico(diag):
    linhas = [diag["descricao"].upper(), "", "Possíveis causas:"]
    linhas += [f"  • {c}" for c in diag["causas"]]
    linhas += ["", "Sugestões e passo a passo:"]
    for s in diag["solucoes"]:
        linhas.append("")
        linhas.append(f"  ✔ {s['descricao']}")
        linhas += [f"      {p}" for p in s["passos"].splitlines()]
    return "\n".join(linhas)


def descricao_chamado(c):
    if c["outro_sintoma"]:
        return f"Outros: {c['outro_sintoma']}"
    return c["descricao_sintoma"]


# ---------------------------------------------------------------- aplicativo
class App(ctk.CTk):
    def __init__(self, caminho_banco=None):
        super().__init__()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.title("EvoLink")
        self.geometry("1040x700")
        self.minsize(340, 540)
        self.configure(fg_color=PAPER)

        # fontes: usa as do EvoLink web se estiverem instaladas
        fams = set(tkfont.families(self))
        self.fam_titulo = "Space Grotesk" if "Space Grotesk" in fams else "Segoe UI"
        self.fam_corpo = "Inter" if "Inter" in fams else "Segoe UI"

        self.db = banco.Banco(caminho_banco)
        self.sintomas = {r["descricao_sintoma"]: r["id_sintoma"] for r in self.db.listar_sintomas()}

        self.usuario = None          # id_usuario do usuário logado
        self.tipo = "cliente"        # "cliente" | "tecnico"
        self.filtro_tecnico = "Todas"
        self.pagina = "usuario"
        self.forcar = "auto"         # "auto" | "pc" | "mobile"
        self.modo = "mobile" if self.winfo_screenwidth() < 800 else "pc"
        self._job = None
        self.nav_botoes = {}

        self.raiz = ctk.CTkFrame(self, fg_color=PAPER, corner_radius=0)
        self.raiz.pack(fill="both", expand=True)
        self.bind("<Configure>", self._ao_redimensionar)
        self.protocol("WM_DELETE_WINDOW", self.fechar_app)
        self.desenhar()

    def fechar_app(self):
        try:
            self.db.fechar()
        finally:
            self.destroy()

    def itens_menu(self):
        itens = list(ITENS_MENU)
        if self.tipo == "tecnico":
            itens.append(ITEM_TECNICO)
        return itens

    # ------------------------------------------------------------ responsividade
    @property
    def pc(self):
        return self.modo == "pc"

    @property
    def pad(self):
        return 34 if self.pc else 14

    def calcular_modo(self):
        if self.forcar in ("pc", "mobile"):
            return self.forcar
        return "mobile" if self.winfo_width() < BREAKPOINT else "pc"

    def _ao_redimensionar(self, event):
        if event.widget is not self:
            return
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(150, self._aplicar_modo)

    def _aplicar_modo(self):
        self._job = None
        novo = self.calcular_modo()
        if novo != self.modo:
            self.modo = novo
            self.desenhar()
        elif self.usuario and self.pagina in ("defeitos", "pagamentos"):
            self.mostrar_pagina(self.pagina)  # refaz a quebra de linha dos textos

    def larg_util(self):
        w = self.winfo_width()
        if w <= 1:
            w = 1040 if self.pc else 400
        return max(220, w - (248 if self.pc else 0) - 2 * self.pad - 24)

    # ------------------------------------------------------------ fábricas de widgets
    def ft(self, tam, negrito=True):
        return ctk.CTkFont(family=self.fam_titulo, size=tam,
                           weight="bold" if negrito else "normal")

    def fc(self, tam, negrito=False):
        return ctk.CTkFont(family=self.fam_corpo, size=tam,
                           weight="bold" if negrito else "normal")

    def limpar(self, frame):
        for w in frame.winfo_children():
            w.destroy()

    def painel(self, parent):
        return ctk.CTkFrame(parent, fg_color=CARD, border_width=1,
                            border_color=LINE, corner_radius=14)

    def rotulo(self, parent, texto, **kw):
        return ctk.CTkLabel(parent, text=texto, anchor="w", text_color=TEXTO,
                            font=self.fc(13, True), **kw)

    def entrada(self, parent, placeholder="", valor="", show=None):
        e = ctk.CTkEntry(parent, height=40, corner_radius=9, fg_color=CARD,
                         border_color=LINE, border_width=1, text_color=TEXTO,
                         placeholder_text=placeholder, placeholder_text_color="#9aa3bd",
                         font=self.fc(13), show=show)
        if valor:
            e.insert(0, valor)
        return e

    def combo(self, parent, valores, comando=None):
        return ctk.CTkOptionMenu(parent, values=valores, height=40, corner_radius=9,
                                 fg_color="#eef1f8", button_color=BLUE500,
                                 button_hover_color=BLUE400, text_color=TEXTO,
                                 dropdown_fg_color=CARD, dropdown_text_color=TEXTO,
                                 dropdown_hover_color="#eef1f8", anchor="w",
                                 dynamic_resizing=False, font=self.fc(13), command=comando)

    def caixa_texto(self, parent, altura):
        return ctk.CTkTextbox(parent, height=altura, corner_radius=9, fg_color=CARD,
                              border_width=1, border_color=LINE, text_color=TEXTO,
                              font=self.fc(13), wrap="word")

    def botao(self, parent, texto, comando, estilo="primario"):
        cores = {
            "primario": (BLUE500, BLUE400, "white"),
            "fantasma": ("#eef1f8", "#e3e8f4", "#3d4766"),
            "verde": ("#e6f6ee", "#d8f1e5", "#1f8a55"),
            "perigo": ("#fdeceb", "#fbdedc", "#c8433f"),
        }
        fg, hover, txt = cores[estilo]
        return ctk.CTkButton(parent, text=texto, command=comando, height=42,
                             corner_radius=9, fg_color=fg, hover_color=hover,
                             text_color=txt, font=self.fc(13, True))

    def selo(self, parent, texto, cores, wrap=0):
        fg, tc = cores
        return ctk.CTkLabel(parent, text=texto, fg_color=fg, text_color=tc, corner_radius=999,
                            font=self.fc(11, True), padx=10, pady=3, wraplength=wrap)

    def grade_campos(self, parent):
        """Frame em grade: 2 colunas no PC, 1 no celular."""
        colunas = 2 if self.pc else 1
        g = ctk.CTkFrame(parent, fg_color="transparent")
        g.pack(fill="x", padx=12)
        for c in range(colunas):
            g.grid_columnconfigure(c, weight=1, uniform="campo")
        g._colunas = colunas
        g._n = 0
        return g

    def campo(self, grade, rotulo, fabrica):
        """Adiciona (rótulo + widget) na próxima célula da grade e devolve o widget."""
        i = grade._n
        grade._n += 1
        cel = ctk.CTkFrame(grade, fg_color="transparent")
        cel.grid(row=i // grade._colunas, column=i % grade._colunas, sticky="ew",
                 padx=6, pady=5)
        self.rotulo(cel, rotulo).pack(fill="x", pady=(0, 4))
        w = fabrica(cel)
        w.pack(fill="x")
        return w

    def cabecalho(self, titulo, sub=""):
        ctk.CTkLabel(self.conteudo, text=titulo, anchor="w", justify="left",
                     text_color=NAVY950, wraplength=self.larg_util(),
                     font=self.ft(22 if self.pc else 19)
                     ).pack(fill="x", padx=self.pad, pady=(self.pad - 6, 2))
        if sub:
            ctk.CTkLabel(self.conteudo, text=sub, anchor="w", justify="left",
                         text_color=TEXTO2, font=self.fc(13),
                         wraplength=self.larg_util()
                         ).pack(fill="x", padx=self.pad, pady=(0, 16))

    def marca_brand(self, parent, tam=36):
        return ctk.CTkLabel(parent, text="🖥", width=tam, height=tam, corner_radius=10,
                            fg_color=BLUE500, text_color="white", font=self.fc(16))

    # ------------------------------------------------------------ desenho geral
    def desenhar(self):
        self.limpar(self.raiz)
        self.nav_botoes = {}
        if self.usuario:
            self.montar_shell()
            self.mostrar_pagina(self.pagina)
        else:
            self.tela_login()

    # ------------------------------------------------------------ LOGIN
    def tela_login(self):
        self.usuario = None
        self.tipo = "cliente"
        self.limpar(self.raiz)
        self.raiz.configure(fg_color=NAVY900)

        card = ctk.CTkFrame(self.raiz, fg_color=CARD, corner_radius=18)
        if self.pc:
            card.place(relx=0.5, rely=0.5, anchor="center")
        else:
            card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.92)

        cab = ctk.CTkFrame(card, fg_color="transparent")
        cab.pack(pady=(28, 4))
        self.marca_brand(cab, 44).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(cab, text="EvoLink", text_color=NAVY950, font=self.ft(28)
                     ).pack(side="left")
        ctk.CTkLabel(card, text="Suporte & Diagnóstico", text_color=TEXTO2,
                     font=self.fc(13)).pack(pady=(0, 18))

        largura = 348 if self.pc else 140  # no celular o cartão ocupa 92% da janela
        self.e_nome = self.entrada(card, "Nome")
        self.e_nome.configure(width=largura)
        self.e_nome.pack(fill="x", padx=26, pady=6)
        self.e_senha = self.entrada(card, "Senha", show="●")
        self.e_senha.configure(width=largura)
        self.e_senha.pack(fill="x", padx=26, pady=6)
        self.e_senha.bind("<Return>", lambda e: self.entrar())
        self.e_codigo = self.entrada(card, "Código de técnico (só no cadastro, opcional)")
        self.e_codigo.configure(width=largura)
        self.e_codigo.pack(fill="x", padx=26, pady=6)

        b_entrar = self.botao(card, "Entrar", self.entrar)
        b_entrar.configure(width=largura)
        b_entrar.pack(fill="x", padx=26, pady=(14, 6))
        b_cad = self.botao(card, "Cadastrar", self.cadastrar, "fantasma")
        b_cad.configure(width=largura)
        b_cad.pack(fill="x", padx=26, pady=(0, 28))
        self.e_nome.focus()

    def entrar(self):
        nome = self.e_nome.get().strip()
        senha = self.e_senha.get()
        if not nome or not senha:
            messagebox.showwarning("Atenção", "Preencha nome e senha.")
            return
        u = self.db.autenticar(nome, senha)
        if u is None:
            messagebox.showerror("Erro", "Nome ou senha incorretos.")
            return
        self.usuario = u["id_usuario"]
        self.tipo = u["tipo"]
        self.pagina = "usuario"
        self.desenhar()

    def cadastrar(self):
        nome = self.e_nome.get().strip()
        senha = self.e_senha.get()
        if not nome or not senha:
            messagebox.showwarning("Atenção", "Preencha nome e senha para se cadastrar.")
            return
        if len(senha) < 4:
            messagebox.showwarning("Atenção", "A senha precisa ter pelo menos 4 caracteres.")
            return
        tipo = "cliente"
        codigo = self.e_codigo.get().strip()
        if codigo:
            if codigo != banco.CODIGO_TECNICO:
                messagebox.showerror("Erro", "Código de técnico incorreto.")
                return
            tipo = "tecnico"
        try:
            self.db.criar_usuario(nome, senha, tipo)
        except ValueError:
            messagebox.showerror("Erro", "Esse nome já está cadastrado.")
            return
        messagebox.showinfo("Pronto", "Cadastro realizado! Agora clique em Entrar.")

    # ------------------------------------------------------------ ESTRUTURA (menu + conteúdo)
    def montar_shell(self):
        self.raiz.configure(fg_color=PAPER)
        nome = self.db.obter_usuario(self.usuario)["nome"]
        menu = self.itens_menu()
        sufixo = "  · técnico" if self.tipo == "tecnico" else ""

        if self.pc:
            lateral = ctk.CTkFrame(self.raiz, width=248, corner_radius=0, fg_color=NAVY900)
            lateral.pack(side="left", fill="y")
            lateral.pack_propagate(False)

            marca = ctk.CTkFrame(lateral, fg_color="transparent")
            marca.pack(fill="x", padx=18, pady=(24, 18))
            self.marca_brand(marca).pack(side="left")
            textos = ctk.CTkFrame(marca, fg_color="transparent")
            textos.pack(side="left", padx=10)
            ctk.CTkLabel(textos, text="EvoLink", text_color="white", anchor="w",
                         font=self.ft(16)).pack(anchor="w")
            ctk.CTkLabel(textos, text="Suporte & Diagnóstico", text_color=INK_DIM,
                         font=self.fc(10)).pack(anchor="w")
            ctk.CTkFrame(lateral, height=1, fg_color="#1b2a4a").pack(fill="x", padx=18, pady=(0, 14))

            for chave, icone, texto, _ in menu:
                b = ctk.CTkButton(lateral, text=f"{icone}   {texto}", anchor="w", height=42,
                                  corner_radius=9, fg_color="transparent",
                                  hover_color=NAV_HOVER, text_color=INK_DIM,
                                  border_width=1, border_color=NAVY900, font=self.fc(14),
                                  command=lambda c=chave: self.mostrar_pagina(c))
                b.pack(fill="x", padx=14, pady=2)
                self.nav_botoes[chave] = b

            rodape = ctk.CTkFrame(lateral, fg_color="transparent")
            rodape.pack(side="bottom", fill="x", padx=14, pady=18)
            ctk.CTkButton(rodape, text="⏻   Sair", anchor="w", height=42, corner_radius=9,
                          fg_color="#3a1f2e", hover_color="#5a2a3a", text_color="#ffb3b0",
                          font=self.fc(14), command=self.sair).pack(fill="x")
            linha = ctk.CTkFrame(rodape, fg_color="transparent")
            linha.pack(fill="x", pady=(12, 0), padx=4)
            ctk.CTkLabel(linha, text="●", text_color=VERDE, width=12, font=self.fc(10)
                         ).pack(side="left")
            ctk.CTkLabel(linha, text=nome + sufixo, text_color=INK_DIM, anchor="w",
                         font=self.fc(12, True)).pack(side="left", padx=6)
        else:
            topo = ctk.CTkFrame(self.raiz, height=58, corner_radius=0, fg_color=NAVY900)
            topo.pack(side="top", fill="x")
            topo.pack_propagate(False)
            self.marca_brand(topo, 34).pack(side="left", padx=(14, 8), pady=12)
            ctk.CTkLabel(topo, text="EvoLink", text_color="white", font=self.ft(17)
                         ).pack(side="left")
            ctk.CTkLabel(topo, text=f"●  {nome.split()[0]}", text_color=INK_DIM,
                         font=self.fc(12, True)).pack(side="right", padx=14)

            barra = ctk.CTkFrame(self.raiz, height=64, corner_radius=0, fg_color=NAVY900)
            barra.pack(side="bottom", fill="x")
            itens = len(menu) + 1
            for i in range(itens):
                barra.grid_columnconfigure(i, weight=1, uniform="nav")
            for i, (chave, icone, _, curto) in enumerate(menu):
                b = ctk.CTkButton(barra, text=f"{icone}\n{curto}", height=54, corner_radius=10,
                                  fg_color="transparent", hover_color=NAV_HOVER,
                                  text_color=INK_DIM, font=self.fc(10), width=40,
                                  command=lambda c=chave: self.mostrar_pagina(c))
                b.grid(row=0, column=i, sticky="ew", padx=1, pady=5)
                self.nav_botoes[chave] = b
            ctk.CTkButton(barra, text="⏻\nSair", height=54, corner_radius=10, width=40,
                          fg_color="transparent", hover_color="#3a1f2e", text_color="#ffb3b0",
                          font=self.fc(10), command=self.sair
                          ).grid(row=0, column=itens - 1, sticky="ew", padx=1, pady=5)

        self.conteudo = ctk.CTkScrollableFrame(self.raiz, fg_color=PAPER, corner_radius=0)
        self.conteudo.pack(side="left", fill="both", expand=True)

    def marcar_nav(self):
        for chave, b in self.nav_botoes.items():
            ativo = chave == self.pagina
            if self.pc:
                b.configure(fg_color=NAV_ATIVO if ativo else "transparent",
                            text_color="white" if ativo else INK_DIM,
                            border_color=NAV_BORDA if ativo else NAVY900)
            else:
                b.configure(text_color=BLUE400 if ativo else INK_DIM,
                            fg_color=NAV_HOVER if ativo else "transparent")

    def mostrar_pagina(self, chave):
        self.pagina = chave
        self.marcar_nav()
        self.limpar(self.conteudo)
        {
            "usuario": self.pagina_usuario,
            "equipamentos": self.pagina_equipamentos,
            "chamado": self.pagina_novo_chamado,
            "defeitos": self.pagina_defeitos,
            "pagamentos": self.pagina_pagamentos,
            "tecnico": self.pagina_tecnico,
        }[chave]()

    def sair(self):
        if messagebox.askyesno("Sair", "Deseja realmente sair do EvoLink?"):
            self.fechar_app()

    # ------------------------------------------------------------ 1) USUÁRIO
    def pagina_usuario(self):
        self.cabecalho("Usuário", "Seus dados de contato.")
        u = self.db.obter_usuario(self.usuario)

        p = self.painel(self.conteudo)
        p.pack(fill="x", padx=self.pad, pady=(0, 14))
        ctk.CTkFrame(p, height=8, fg_color="transparent").pack()
        grade = self.grade_campos(p)
        campos = {
            "nome": self.campo(grade, "Nome:", lambda c: self.entrada(c, valor=u["nome"])),
            "telefone": self.campo(grade, "Telefone:", lambda c: self.entrada(c, valor=u["telefone"])),
            "endereco": self.campo(grade, "Endereço:", lambda c: self.entrada(c, valor=u["endereco"])),
            "email": self.campo(grade, "E-mail:", lambda c: self.entrada(c, valor=u["email"])),
        }

        def gravar():
            nome = campos["nome"].get().strip()
            if not nome:
                messagebox.showwarning("Atenção", "O nome não pode ficar vazio.")
                return
            try:
                self.db.atualizar_usuario(self.usuario, nome, campos["telefone"].get().strip(),
                                          campos["endereco"].get().strip(),
                                          campos["email"].get().strip())
            except ValueError:
                messagebox.showerror("Erro", "Já existe um usuário com esse nome.")
                return
            messagebox.showinfo("Salvo", "Dados do usuário salvos com sucesso.")
            self.desenhar()

        b = self.botao(p, "Salvar dados", gravar)
        if self.pc:
            b.configure(width=160)
            b.pack(anchor="w", padx=20, pady=(8, 18))
        else:
            b.pack(fill="x", padx=20, pady=(8, 18))

        # visual do app
        p2 = self.painel(self.conteudo)
        p2.pack(fill="x", padx=self.pad, pady=(0, 20))
        ctk.CTkLabel(p2, text="Visual do app", anchor="w", text_color=NAVY950,
                     font=self.ft(15)).pack(fill="x", padx=20, pady=(16, 0))
        ctk.CTkLabel(p2, text="Automático adapta à largura da janela. Você pode forçar "
                              "o visual de celular ou de computador.", anchor="w",
                     justify="left", text_color=TEXTO2, font=self.fc(12),
                     wraplength=self.larg_util() - 40).pack(fill="x", padx=20, pady=(2, 10))
        nomes = {"auto": "Automático", "mobile": "Celular", "pc": "Computador"}
        seg = ctk.CTkSegmentedButton(
            p2, values=list(nomes.values()), command=self.trocar_visual,
            selected_color=BLUE500, selected_hover_color=BLUE400,
            unselected_color="#eef1f8", unselected_hover_color="#e3e8f4",
            text_color=TEXTO, fg_color="#eef1f8", font=self.fc(12, True), height=36)
        seg.set(nomes[self.forcar])
        seg.pack(fill="x", padx=20, pady=(0, 18))

    def trocar_visual(self, escolha):
        self.forcar = {"Automático": "auto", "Celular": "mobile", "Computador": "pc"}[escolha]
        if self.forcar == "mobile":
            self.geometry("400x780")
        elif self.forcar == "pc":
            self.geometry("1040x700")
        self.modo = self.calcular_modo()
        self.desenhar()

    # ------------------------------------------------------------ 2) EQUIPAMENTOS (tabela produtos)
    def pagina_equipamentos(self):
        self.cabecalho("Equipamentos",
                       "Cadastre os computadores e periféricos para vincular aos chamados.")

        form = self.painel(self.conteudo)
        form.pack(fill="x", padx=self.pad, pady=(0, 14))
        ctk.CTkLabel(form, text="Novo equipamento", anchor="w", text_color=NAVY950,
                     font=self.ft(16)).pack(fill="x", padx=18, pady=(16, 8))
        grade = self.grade_campos(form)
        cb_tipo = self.campo(grade, "Tipo:", lambda c: self.combo(c, banco.TIPOS_EQUIPAMENTO))
        e_marca = self.campo(grade, "Marca:", lambda c: self.entrada(c, "Ex.: Dell"))
        e_modelo = self.campo(grade, "Modelo:", lambda c: self.entrada(c, "Ex.: Inspiron 15"))
        e_so = self.campo(grade, "Sistema operacional:",
                          lambda c: self.entrada(c, "Ex.: Windows 11"))
        e_serie = self.campo(grade, "Nº de série (opcional):", lambda c: self.entrada(c))

        def cadastrar():
            marca, modelo = e_marca.get().strip(), e_modelo.get().strip()
            if not marca or not modelo:
                messagebox.showwarning("Atenção", "Informe a marca e o modelo.")
                return
            self.db.criar_produto(self.usuario, cb_tipo.get(), marca, modelo,
                                  e_so.get().strip(), e_serie.get().strip())
            messagebox.showinfo("Pronto", "Equipamento cadastrado!")
            self.mostrar_pagina("equipamentos")

        b = self.botao(form, "Cadastrar equipamento", cadastrar)
        if self.pc:
            b.configure(width=210)
            b.pack(anchor="w", padx=18, pady=(8, 18))
        else:
            b.pack(fill="x", padx=18, pady=(8, 18))

        lista = self.painel(self.conteudo)
        lista.pack(fill="x", padx=self.pad, pady=(0, 20))
        ctk.CTkLabel(lista, text="Meus equipamentos", anchor="w", text_color=NAVY950,
                     font=self.ft(16)).pack(fill="x", padx=18, pady=(16, 8))
        produtos = self.db.listar_produtos(self.usuario)
        if not produtos:
            ctk.CTkLabel(lista, text="Nenhum equipamento cadastrado ainda.", anchor="w",
                         text_color=TEXTO2, font=self.fc(13)
                         ).pack(fill="x", padx=18, pady=(0, 18))
        quebra = self.larg_util() - (200 if self.pc else 70)
        for p in produtos:
            linha = ctk.CTkFrame(lista, fg_color=PAPER, corner_radius=10)
            linha.pack(fill="x", padx=14, pady=4)
            linha.grid_columnconfigure(0, weight=1)
            detalhes = " · ".join(x for x in [p["tipo"], p["sistema_operacional"],
                                              f"Série {p['numero_serie']}" if p["numero_serie"] else ""] if x)
            ctk.CTkLabel(linha, text=f"{p['marca']} {p['modelo']}\n{detalhes}", anchor="w",
                         justify="left", text_color=TEXTO, font=self.fc(12), wraplength=quebra
                         ).grid(row=0, column=0, sticky="w", padx=12, pady=10)
            bx = self.botao(linha, "Excluir", lambda i=p["id_produto"]: self.excluir_equipamento(i),
                            "perigo")
            bx.configure(width=90, height=34)
            bx.grid(row=0 if self.pc else 1, column=1 if self.pc else 0,
                    sticky="e" if self.pc else "w", padx=12,
                    pady=(10 if self.pc else 0, 10))
        if produtos:
            ctk.CTkFrame(lista, height=10, fg_color="transparent").pack()

    def excluir_equipamento(self, id_produto):
        if messagebox.askyesno("Excluir", "Excluir este equipamento?\n"
                                          "Os chamados dele continuam salvos."):
            self.db.excluir_produto(id_produto, self.usuario)
            self.mostrar_pagina("equipamentos")

    # ------------------------------------------------------------ 3) NOVO CHAMADO
    def pagina_novo_chamado(self):
        self.cabecalho("Novo chamado",
                       "Registre o defeito e veja uma sugestão de solução antes do técnico chegar.")
        grade = ctk.CTkFrame(self.conteudo, fg_color="transparent")
        grade.pack(fill="x", padx=self.pad, pady=(0, 20))
        if self.pc:
            grade.grid_columnconfigure(0, weight=3, uniform="col")
            grade.grid_columnconfigure(1, weight=2, uniform="col")
        else:
            grade.grid_columnconfigure(0, weight=1)

        # --- formulário
        form = self.painel(grade)
        if self.pc:
            form.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        else:
            form.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        ctk.CTkLabel(form, text="Dados do chamado", anchor="w", text_color=NAVY950,
                     font=self.ft(16)).pack(fill="x", padx=18, pady=(16, 8))

        produtos = self.db.listar_produtos(self.usuario)
        self.mapa_produtos = {"Não informar": None}
        for p in produtos:
            self.mapa_produtos[f"{p['marca']} {p['modelo']} (#{p['id_produto']})"] = p["id_produto"]
        self.rotulo(form, "Equipamento:").pack(fill="x", padx=18, pady=(0, 4))
        self.cb_produto = self.combo(form, list(self.mapa_produtos))
        self.cb_produto.pack(fill="x", padx=18)
        if not produtos:
            ctk.CTkLabel(form, text="Dica: cadastre seu equipamento em \"Equipamentos\" "
                                    "para vincular ao chamado.", anchor="w", justify="left",
                         text_color=TEXTO2, font=self.fc(11), wraplength=self.larg_util() // 2
                         ).pack(fill="x", padx=18, pady=(4, 0))

        self.rotulo(form, "Problema encontrado:").pack(fill="x", padx=18, pady=(14, 4))
        self.cb_problema = self.combo(form, list(self.sintomas), self._problema_mudou)
        self.cb_problema.set("Selecione...")
        self.cb_problema.pack(fill="x", padx=18)

        self.e_outro = self.entrada(form, "Especifique o problema")

        self.rotulo(form, "Defeito e informações:").pack(fill="x", padx=18, pady=(14, 4))
        self.t_info = self.caixa_texto(form, 110)
        self.t_info.pack(fill="x", padx=18)

        linha = ctk.CTkFrame(form, fg_color="transparent")
        linha.pack(fill="x", padx=18, pady=(14, 18))
        b1 = self.botao(linha, "🧠  Diagnóstico inteligente", self.diagnosticar, "fantasma")
        b2 = self.botao(linha, "Abrir chamado", self.abrir_chamado)
        if self.pc:
            b1.pack(side="left")
            b2.pack(side="left", padx=10)
        else:
            b1.pack(fill="x", pady=(0, 8))
            b2.pack(fill="x")

        # --- diagnóstico
        diag = self.painel(grade)
        if self.pc:
            diag.grid(row=0, column=1, sticky="nsew", padx=(9, 0))
        else:
            diag.grid(row=1, column=0, sticky="ew")
        ctk.CTkLabel(diag, text="Diagnóstico inteligente", anchor="w", text_color=NAVY950,
                     font=self.ft(16)).pack(fill="x", padx=18, pady=(16, 8))
        self.t_diag = ctk.CTkTextbox(diag, height=420 if self.pc else 300, corner_radius=9,
                                     fg_color=PAPER, border_width=0, text_color=TEXTO,
                                     font=self.fc(13), wrap="word")
        self.t_diag.pack(fill="x", padx=18, pady=(0, 18))
        self._escrever_diag("Selecione o problema encontrado e clique em "
                            "\"Diagnóstico inteligente\" para ver as possíveis causas, "
                            "as sugestões e o passo a passo.")

    def _problema_mudou(self, escolha):
        if escolha == banco.OUTROS:
            self.e_outro.pack(fill="x", padx=18, pady=(8, 0), after=self.cb_problema)
        else:
            self.e_outro.pack_forget()

    def _escrever_diag(self, texto):
        self.t_diag.configure(state="normal")
        self.t_diag.delete("1.0", "end")
        self.t_diag.insert("1.0", texto)
        self.t_diag.configure(state="disabled")

    def diagnosticar(self):
        problema = self.cb_problema.get()
        if problema not in self.sintomas:
            messagebox.showwarning("Atenção", "Selecione o problema encontrado.")
            return
        self._escrever_diag(texto_diagnostico(self.db.diagnostico(self.sintomas[problema])))

    def abrir_chamado(self):
        problema = self.cb_problema.get()
        if problema not in self.sintomas:
            messagebox.showwarning("Atenção", "Selecione o problema encontrado.")
            return
        outro = ""
        if problema == banco.OUTROS:
            outro = self.e_outro.get().strip()
            if not outro:
                messagebox.showwarning("Atenção", "Especifique o problema.")
                return
        id_chamado = self.db.criar_chamado(
            id_cliente=self.usuario,
            id_sintoma=self.sintomas[problema],
            id_produto=self.mapa_produtos.get(self.cb_produto.get()),
            outro_sintoma=outro,
            descricao_problema=self.t_info.get("1.0", "end").strip())
        messagebox.showinfo("Chamado aberto", f"Chamado #{id_chamado} aberto com sucesso!")
        self.mostrar_pagina("chamado")

    # ------------------------------------------------------------ 4) DEFEITOS E SOLUÇÕES
    def pagina_defeitos(self):
        self.cabecalho("Defeitos do computador e soluções",
                       "Problemas mais comuns, possíveis causas e o que fazer primeiro.")
        colunas = 2 if self.pc else 1
        grade = ctk.CTkFrame(self.conteudo, fg_color="transparent")
        grade.pack(fill="x", padx=self.pad, pady=(0, 20))
        for c in range(colunas):
            grade.grid_columnconfigure(c, weight=1, uniform="card")

        quebra = (self.larg_util() - (colunas - 1) * 14) // colunas - 40
        i = 0
        for desc, id_sintoma in self.sintomas.items():
            if desc == banco.OUTROS:
                continue
            d = self.db.diagnostico(id_sintoma)
            card = self.painel(grade)
            card.grid(row=i // colunas, column=i % colunas, sticky="nsew", padx=6, pady=6)
            i += 1
            ctk.CTkLabel(card, text=desc, anchor="w", text_color=NAVY950,
                         font=self.ft(15), wraplength=quebra, justify="left"
                         ).pack(fill="x", padx=18, pady=(16, 6))
            ctk.CTkLabel(card, text="POSSÍVEIS CAUSAS", anchor="w", text_color=TEXTO2,
                         font=self.fc(10, True)).pack(fill="x", padx=18)
            ctk.CTkLabel(card, text="\n".join(f"• {c}" for c in d["causas"]), anchor="w",
                         justify="left", text_color=TEXTO, font=self.fc(12),
                         wraplength=quebra).pack(fill="x", padx=18, pady=(2, 8))
            ctk.CTkLabel(card, text="SUGESTÃO", anchor="w", text_color="#1f8a55",
                         font=self.fc(10, True)).pack(fill="x", padx=18)
            ctk.CTkLabel(card, text="\n".join(f"✔ {s['descricao']}" for s in d["solucoes"]),
                         anchor="w", justify="left", text_color=TEXTO, font=self.fc(12),
                         wraplength=quebra).pack(fill="x", padx=18, pady=(2, 10))
            b = self.botao(card, "Ver passo a passo", lambda dd=d: self.abrir_passos(dd), "fantasma")
            b.configure(height=36)
            b.pack(fill="x", padx=18, pady=(0, 16))

    def abrir_passos(self, diag):
        janela = ctk.CTkToplevel(self)
        janela.title(diag["descricao"])
        janela.geometry("460x560" if self.pc else "370x560")
        janela.configure(fg_color=PAPER)
        caixa = self.caixa_texto(janela, 400)
        caixa.pack(fill="both", expand=True, padx=14, pady=(14, 8))
        caixa.insert("1.0", texto_diagnostico(diag))
        caixa.configure(state="disabled")
        self.botao(janela, "Fechar", janela.destroy).pack(fill="x", padx=14, pady=(0, 14))
        janela.after(200, lambda: (janela.lift(), janela.focus()))

    # ------------------------------------------------------------ 5) PAGAMENTOS
    def pagina_pagamentos(self):
        self.cabecalho("Pagamentos", "Registre pagamentos e acompanhe o histórico dos chamados.")
        meus = self.db.listar_chamados(self.usuario)
        pendentes = [c for c in meus
                     if c["total_pago"] is None and c["situacao_chamado"] != "Cancelado"]

        # cartões de resumo
        resumo = ctk.CTkFrame(self.conteudo, fg_color="transparent")
        resumo.pack(fill="x", padx=self.pad, pady=(0, 14))
        stats = [(str(len(meus)), "Chamados", NAVY950),
                 (str(len(pendentes)), "Pendentes", BLUE500),
                 (brl(self.db.total_pago(self.usuario)), "Total pago", "#1f8a55")]
        for i in range(3):
            resumo.grid_columnconfigure(i, weight=1, uniform="stat")
        for i, (num, lab, cor) in enumerate(stats):
            s = self.painel(resumo)
            s.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 5, 0 if i == 2 else 5))
            ctk.CTkLabel(s, text=num, text_color=cor, anchor="w",
                         font=self.ft(24 if self.pc else 14)).pack(fill="x", padx=14, pady=(14, 0))
            ctk.CTkLabel(s, text=lab, text_color=TEXTO2, anchor="w",
                         font=self.fc(12 if self.pc else 10)).pack(fill="x", padx=14, pady=(0, 12))

        # registrar pagamento
        form = self.painel(self.conteudo)
        form.pack(fill="x", padx=self.pad, pady=(0, 14))
        ctk.CTkLabel(form, text="Registrar pagamento", anchor="w", text_color=NAVY950,
                     font=self.ft(16)).pack(fill="x", padx=18, pady=(16, 8))

        mapa = {SEM_CHAMADO: None}
        for c in pendentes:
            mapa[f"#{c['id_chamado']} - {descricao_chamado(c)}"] = c["id_chamado"]

        grade = self.grade_campos(form)
        cb_chamado = self.campo(grade, "Chamado:", lambda p: self.combo(p, list(mapa)))
        e_valor = self.campo(grade, "Valor (R$):", lambda p: self.entrada(p, "Ex.: 80,00"))
        e_desc = self.campo(grade, "Desconto (R$):", lambda p: self.entrada(p, "0,00"))
        cb_tipo = self.campo(grade, "Forma de pagamento:",
                             lambda p: self.combo(p, banco.TIPOS_PAGAMENTO))
        cb_recor = self.campo(grade, "Recorrência:",
                              lambda p: self.combo(p, banco.RECORRENCIAS))
        e_periodo = self.campo(grade, "Período (mês/ano):",
                               lambda p: self.entrada(p, valor=datetime.now().strftime("%m/%Y")))

        def registrar():
            try:
                valor = numero(e_valor.get())
                desconto = numero(e_desc.get(), 0.0)
                if valor <= 0 or desconto < 0 or desconto > valor:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Atenção", "Informe um valor válido "
                                                  "(o desconto não pode passar do valor).")
                return
            self.db.registrar_pagamento(
                id_usuario=self.usuario, preco_pago=round(valor - desconto, 2),
                tipo_pagamento=cb_tipo.get(), id_chamado=mapa[cb_chamado.get()],
                desconto=desconto, recorrencia=cb_recor.get(),
                periodo_pagamento=e_periodo.get().strip())
            messagebox.showinfo("Pagamento", "Pagamento registrado!")
            self.mostrar_pagina("pagamentos")

        b = self.botao(form, "Registrar pagamento", registrar)
        if self.pc:
            b.configure(width=190)
            b.pack(anchor="w", padx=18, pady=(8, 18))
        else:
            b.pack(fill="x", padx=18, pady=(8, 18))

        # histórico
        hist = self.painel(self.conteudo)
        hist.pack(fill="x", padx=self.pad, pady=(0, 20))
        ctk.CTkLabel(hist, text="Histórico de chamados", anchor="w", text_color=NAVY950,
                     font=self.ft(16)).pack(fill="x", padx=18, pady=(16, 8))
        if not meus:
            ctk.CTkLabel(hist, text="Nenhum chamado aberto ainda.", text_color=TEXTO2,
                         anchor="w", font=self.fc(13)).pack(fill="x", padx=18, pady=(0, 18))
        quebra = self.larg_util() - (250 if self.pc else 70)
        for c in meus[:30]:
            linha = ctk.CTkFrame(hist, fg_color=PAPER, corner_radius=10)
            linha.pack(fill="x", padx=14, pady=4)
            linha.grid_columnconfigure(0, weight=1)
            equip = f" — {c['marca']} {c['modelo']}" if c["marca"] else ""
            ctk.CTkLabel(linha, text=f"#{c['id_chamado']}  {descricao_chamado(c)}{equip}\n"
                                     f"{fmt_data(c['data_abertura'])}",
                         anchor="w", justify="left", text_color=TEXTO, font=self.fc(12),
                         wraplength=quebra
                         ).grid(row=0, column=0, sticky="w", padx=12, pady=10)

            selos = ctk.CTkFrame(linha, fg_color="transparent")
            selos.grid(row=0 if self.pc else 1, column=1 if self.pc else 0,
                       sticky="e" if self.pc else "w", padx=12,
                       pady=(10 if self.pc else 0, 10))
            self.selo(selos, c["situacao_chamado"],
                      COR_SITUACAO[c["situacao_chamado"]]).pack(
                side="left" if not self.pc else "top", anchor="w" if not self.pc else "e",
                pady=(0, 4 if self.pc else 0), padx=(0, 6 if not self.pc else 0))
            if c["total_pago"] is not None:
                texto, cores = f"Pago · {brl(c['total_pago'])} · {c['tipo_pagamento']}", ("#e6f6ee", "#1f8a55")
            else:
                texto, cores = "Sem pagamento", ("#eef1f8", "#6b7593")
            self.selo(selos, texto, cores, wrap=quebra).pack(
                side="left" if not self.pc else "top", anchor="w" if not self.pc else "e")
        if meus:
            ctk.CTkFrame(hist, height=10, fg_color="transparent").pack()


    # ------------------------------------------------------------ 6) PAINEL DO TÉCNICO
    def pagina_tecnico(self):
        if self.tipo != "tecnico":
            self.mostrar_pagina("usuario")
            return
        self.cabecalho("Painel do técnico",
                       "Veja os chamados de todos os clientes e atualize a situação de cada um.")
        topo = ctk.CTkFrame(self.conteudo, fg_color="transparent")
        topo.pack(fill="x", padx=self.pad, pady=(0, 10))
        self.rotulo(topo, "Filtrar por situação:").pack(anchor="w", pady=(0, 4))
        cb = self.combo(topo, ["Todas"] + banco.SITUACOES, self._filtrar_tecnico)
        cb.set(self.filtro_tecnico)
        if self.pc:
            cb.configure(width=260)
            cb.pack(anchor="w")
        else:
            cb.pack(fill="x")

        chamados = self.db.listar_todos_chamados(
            None if self.filtro_tecnico == "Todas" else self.filtro_tecnico)
        if not chamados:
            ctk.CTkLabel(self.conteudo, text="Nenhum chamado encontrado.", anchor="w",
                         text_color=TEXTO2, font=self.fc(13)
                         ).pack(fill="x", padx=self.pad, pady=10)
        quebra = self.larg_util() - (330 if self.pc else 60)
        for c in chamados:
            card = self.painel(self.conteudo)
            card.pack(fill="x", padx=self.pad, pady=5)
            card.grid_columnconfigure(0, weight=1)
            equip = f"{c['marca']} {c['modelo']}" if c["marca"] else "Equipamento não informado"
            cliente = f"Cliente: {c['nome_cliente']}" + (f" · {c['telefone']}" if c["telefone"] else "")
            linhas = [f"#{c['id_chamado']}  {descricao_chamado(c)}", cliente,
                      f"{equip} · {fmt_data(c['data_abertura'])}"]
            if c["descricao_problema"]:
                linhas.append(f"Relato: {c['descricao_problema']}")
            ctk.CTkLabel(card, text="\n".join(linhas), anchor="w", justify="left",
                         text_color=TEXTO, font=self.fc(12), wraplength=quebra
                         ).grid(row=0, column=0, sticky="w", padx=16, pady=14)

            acoes = ctk.CTkFrame(card, fg_color="transparent")
            if self.pc:
                acoes.grid(row=0, column=1, sticky="e", padx=16, pady=14)
            else:
                acoes.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))
            cb_sit = self.combo(acoes, banco.SITUACOES)
            cb_sit.set(c["situacao_chamado"])
            bt = self.botao(acoes, "Salvar situação",
                            lambda i=c["id_chamado"], w=cb_sit: self.salvar_situacao(i, w.get()),
                            "verde")
            if self.pc:
                cb_sit.configure(width=190)
                cb_sit.pack(pady=(0, 6))
            else:
                cb_sit.pack(fill="x", pady=(0, 6))
            bt.pack(fill="x")

            # atalho: só aparece enquanto o chamado ainda não foi encerrado
            if c["situacao_chamado"] not in ("Resolvido", "Cancelado"):
                self.botao(acoes, "✔ Marcar como resolvido",
                           lambda i=c["id_chamado"]: self.salvar_situacao(i, "Resolvido")
                           ).pack(fill="x", pady=(6, 0))

    def _filtrar_tecnico(self, escolha):
        self.filtro_tecnico = escolha
        self.mostrar_pagina("tecnico")

    def salvar_situacao(self, id_chamado, situacao):
        if situacao in ("Resolvido", "Cancelado"):
            if not messagebox.askyesno(
                    "Confirmar",
                    f"Marcar o chamado #{id_chamado} como {situacao}?\n"
                    "Isso registra a data de fechamento."):
                return
        self.db.atualizar_situacao(id_chamado, situacao)
        messagebox.showinfo("Salvo", f"Chamado #{id_chamado} agora está: {situacao}.")
        self.mostrar_pagina("tecnico")


if __name__ == "__main__":
    App().mainloop()
