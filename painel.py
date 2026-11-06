"""
EvoLink - cálculos e gráficos do painel (Visão geral).

Este arquivo NÃO usa tkinter: só pega as linhas que o banco devolveu, faz as contas
e desenha os gráficos com matplotlib. O evolink_app.py apenas encaixa as figuras na tela.

Precisa da biblioteca:   pip install matplotlib   (versão 3.7 ou mais nova)
Fica na MESMA pasta de evolink_app.py e banco.py.
"""
import textwrap
from collections import Counter, defaultdict
from datetime import datetime

from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from banco import SITUACOES

# ---------------------------------------------------------------- cores (iguais ao app)
AZUL, AZUL_CLARO = "#3b6fe0", "#5c8bf0"
VERDE, VERMELHO, AMBAR = "#2fa66a", "#e05a5a", "#e0a13b"
LARANJA, ROXO, CINZA = "#e08a3b", "#8b6fe0", "#93a1c2"
TEXTO, TEXTO2, LINHA = "#1b2440", "#6b7593", "#e2e6f0"
PALETA = [AZUL, VERDE, AMBAR, VERMELHO, ROXO, CINZA]
COR_SITUACAO = {"Aberto": AZUL, "Em andamento": AMBAR, "Aguardando peça": LARANJA,
                "Resolvido": VERDE, "Cancelado": CINZA}
ENCERRADAS = ("Resolvido", "Cancelado")
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"


# ====================================================================== UTILIDADES
def brl(v, casas=2):
    return "R$ " + f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _dt(texto):
    try:
        return datetime.strptime(texto, FORMATO_DATA)
    except (TypeError, ValueError):
        return None


def nome_problema(c):
    """Nome curto do problema: 'Outros (especificar)' vira só 'Outros'."""
    nome = c.get("descricao_sintoma") or "Sem sintoma"
    return "Outros" if nome.startswith("Outros") else nome


def ultimos_meses(n=12, hoje=None):
    hoje = hoje or datetime.now()
    ano, mes = hoje.year, hoje.month
    meses = []
    for _ in range(n):
        meses.append((ano, mes))
        mes -= 1
        if mes == 0:
            ano, mes = ano - 1, 12
    return meses[::-1]


def rotulo_mes(par):
    return f"{par[1]:02d}/{par[0] % 100:02d}"


def serie_mensal(registros, campo_data, campo_valor=None, n=12, hoje=None):
    """Soma (ou conta) por mês nos últimos n meses, sempre com os meses vazios = 0."""
    meses = ultimos_meses(n, hoje)
    total = {m: 0 for m in meses}
    for r in registros:
        d = _dt(r.get(campo_data))
        if d and (d.year, d.month) in total:
            total[(d.year, d.month)] += (r.get(campo_valor) or 0) if campo_valor else 1
    return {"rotulos": [rotulo_mes(m) for m in meses], "valores": [total[m] for m in meses]}


def _ordenado(contador, limite=None):
    itens = sorted(contador.items(), key=lambda kv: (-kv[1], kv[0]))
    return itens[:limite] if limite else itens


# ====================================================================== CÁLCULOS
def calcular(dados, hoje=None):
    """Recebe o dicionário de banco.dados_painel() e devolve tudo pronto para exibir."""
    hoje = hoje or datetime.now()
    chamados = dados.get("chamados", [])
    pagamentos = dados.get("pagamentos", [])
    usuarios = dados.get("usuarios")  # None na visão do cliente
    st = {"hoje": hoje}

    # ---- cartões
    mes_atual = (hoje.year, hoje.month)
    fat_mes = sum(p["preco_pago"] for p in pagamentos
                  if (d := _dt(p["data_pagamento"])) and (d.year, d.month) == mes_atual)
    fat_total = sum(p["preco_pago"] for p in pagamentos)
    st["resumo"] = {
        "chamados": len(chamados),
        "abertos": sum(1 for c in chamados if c["situacao_chamado"] not in ENCERRADAS),
        "clientes": (sum(1 for u in usuarios if u["tipo"] == "cliente")
                     if usuarios is not None else None),
        "faturamento_mes": fat_mes,
        "faturamento_total": fat_total,
        "ticket_medio": fat_total / len(pagamentos) if pagamentos else 0.0,
    }

    # ---- 1) situação
    cont = Counter(c["situacao_chamado"] for c in chamados)
    st["situacao"] = [(s, cont[s]) for s in SITUACOES if cont[s]]

    # ---- 2) principais problemas
    st["problemas"] = _ordenado(Counter(nome_problema(c) for c in chamados), 8)

    # ---- 3) chamados por mês, 4) cadastros por mês, 5) faturamento por mês
    st["chamados_mes"] = serie_mensal(chamados, "data_abertura", hoje=hoje)
    st["cadastros_mes"] = (serie_mensal([u for u in usuarios if u["tipo"] == "cliente"],
                                        "criado_em", hoje=hoje)
                           if usuarios is not None else None)
    st["faturamento_mes"] = serie_mensal(pagamentos, "data_pagamento", "preco_pago", hoje=hoje)

    # ---- 6) formas de pagamento, 9) recorrência
    st["formas"] = _ordenado(Counter(p["tipo_pagamento"] for p in pagamentos))
    st["recorrencia"] = _ordenado(Counter(p["recorrencia"] for p in pagamentos))

    # ---- 7) equipamentos
    st["equipamentos"] = _ordenado(
        Counter(c.get("tipo_equipamento") or "Não informado" for c in chamados))

    # ---- 8) tempo médio de resolução por problema
    horas = defaultdict(list)
    for c in chamados:
        ini, fim = _dt(c["data_abertura"]), _dt(c.get("data_fechamento"))
        if c["situacao_chamado"] == "Resolvido" and ini and fim and fim >= ini:
            horas[nome_problema(c)].append((fim - ini).total_seconds() / 3600)
    medias = sorted(((p, sum(v) / len(v)) for p, v in horas.items()), key=lambda kv: -kv[1])[:8]
    em_dias = bool(medias) and max(v for _, v in medias) >= 48
    st["tempo_resolucao"] = {
        "rotulos": [p for p, _ in medias],
        "valores": [round(v / 24 if em_dias else v, 1) for _, v in medias],
        "unidade": "dias" if em_dias else "horas",
    }

    # ---- tabela: problemas x situação
    tabela = defaultdict(Counter)
    for c in chamados:
        tabela[nome_problema(c)][c["situacao_chamado"]] += 1
    st["problema_situacao"] = [
        [p] + [tabela[p][s] for s in SITUACOES] + [sum(tabela[p].values())]
        for p in sorted(tabela, key=lambda p: -sum(tabela[p].values()))
    ]

    # ---- tabela: chamados sem pagamento
    sem = []
    for c in chamados:
        if c.get("total_pago") is None and c["situacao_chamado"] != "Cancelado":
            ini = _dt(c["data_abertura"])
            fim = _dt(c.get("data_fechamento")) or hoje
            sem.append({"id": c["id_chamado"], "cliente": c.get("nome_cliente", ""),
                        "problema": nome_problema(c),
                        "data": ini.strftime("%d/%m/%Y") if ini else "",
                        "dias": max(0, (fim - ini).days) if ini else 0})
    st["sem_pagamento"] = sorted(sem, key=lambda x: -x["dias"])

    # ---- tabela: últimos pagamentos
    ult = sorted(pagamentos, key=lambda p: p["data_pagamento"] or "", reverse=True)[:10]
    st["ultimos_pagamentos"] = [
        {"cliente": p.get("nome_cliente", ""), "valor": p["preco_pago"],
         "desconto": p["desconto"], "forma": p["tipo_pagamento"],
         "data": (_dt(p["data_pagamento"]).strftime("%d/%m/%Y")
                  if _dt(p["data_pagamento"]) else "")}
        for p in ult
    ]

    # ---- tabela: ranking de clientes
    por_cliente = defaultdict(lambda: {"nome": "", "chamados": 0, "pago": 0.0})
    for c in chamados:
        r = por_cliente[c["id_cliente"]]
        r["nome"] = c.get("nome_cliente", "")
        r["chamados"] += 1
    for p in pagamentos:
        r = por_cliente[p["id_usuario"]]
        r["nome"] = r["nome"] or p.get("nome_cliente", "")
        r["pago"] += p["preco_pago"]
    st["ranking"] = sorted(por_cliente.values(), key=lambda r: (-r["pago"], -r["chamados"]))[:10]
    return st


# ====================================================================== DESENHO
def _estilo(ax, grade="y"):
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(LINHA)
    ax.tick_params(colors=TEXTO2, labelsize=8)
    ax.set_axisbelow(True)
    ax.grid(axis=grade, color="#eef1f8", linewidth=1)


def _vazio(ax, texto="Sem dados ainda"):
    ax.axis("off")
    ax.text(0.5, 0.5, texto, ha="center", va="center", color=TEXTO2, fontsize=10,
            transform=ax.transAxes)


def _curto(texto, limite=26):
    return "\n".join(textwrap.wrap(texto, limite)[:2]) or texto


def _rosca(ax, itens, cores=None):
    """itens = [(rótulo, valor)]. Rosca com legenda embaixo."""
    if not itens or not sum(v for _, v in itens):
        return _vazio(ax)
    rotulos = [r for r, _ in itens]
    valores = [v for _, v in itens]
    cores = cores or [PALETA[i % len(PALETA)] for i in range(len(itens))]
    ondas, _, textos = ax.pie(
        valores, colors=cores, startangle=90, counterclock=False,
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 2},
        autopct=lambda p: f"{p:.0f}%" if p >= 6 else "", pctdistance=0.79)
    for t in textos:
        t.set_color("white")
        t.set_fontsize(8)
        t.set_fontweight("bold")
    ax.set_aspect("equal")
    ax.figure.legend(ondas, [f"{r} ({v})" for r, v in itens], loc="outside lower center",
                     ncol=2, frameon=False, fontsize=8, labelcolor=TEXTO2)


def _barras(ax, rotulos, valores, cor=AZUL, fmt=None, inteiro=True):
    if not valores or not sum(valores):
        return _vazio(ax)
    _estilo(ax)
    barras = ax.bar(rotulos, valores, color=cor, width=0.62)
    ax.bar_label(barras, labels=[(fmt(v) if fmt else f"{v:g}") if v else "" for v in valores],
                 fontsize=6.5, color=TEXTO2, padding=2)
    if inteiro:
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.margins(y=0.15)
    ax.tick_params(axis="x", labelsize=8)
    if len(rotulos) > 4:
        for t in ax.get_xticklabels():
            t.set_rotation(35)
            t.set_ha("right")
            t.set_rotation_mode("anchor")


def _linha(ax, rotulos, valores, cor=AZUL):
    if not valores or not sum(valores):
        return _vazio(ax)
    _estilo(ax)
    x = list(range(len(valores)))
    ax.plot(x, valores, color=cor, marker="o", markersize=4, linewidth=2)
    ax.fill_between(x, valores, color=cor, alpha=0.12)
    ax.set_xticks(x, rotulos)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_ylim(bottom=0)
    ax.tick_params(axis="x", labelsize=8, rotation=45)


def _barras_h(ax, rotulos, valores, cor=AZUL, fmt=None):
    if not valores or not sum(valores):
        return _vazio(ax)
    _estilo(ax, "x")
    pos = list(range(len(valores)))
    barras = ax.barh(pos, valores, color=cor, height=0.62)
    ax.set_yticks(pos, [_curto(r) for r in rotulos])
    ax.invert_yaxis()
    ax.bar_label(barras, labels=[fmt(v) if fmt else f"{v:g}" for v in valores],
                 fontsize=8, color=TEXTO2, padding=3)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5, integer=fmt is None))
    ax.margins(x=0.22)


# cada gráfico: (título, pergunta que responde, função que desenha em `ax` usando `st`)
def _g_situacao(ax, st):
    _rosca(ax, st["situacao"], [COR_SITUACAO[s] for s, _ in st["situacao"]])


def _g_problemas(ax, st):
    _barras_h(ax, [p for p, _ in st["problemas"]], [v for _, v in st["problemas"]], AZUL)


def _g_chamados_mes(ax, st):
    _linha(ax, st["chamados_mes"]["rotulos"], st["chamados_mes"]["valores"], AZUL)


def _g_cadastros_mes(ax, st):
    s = st["cadastros_mes"] or {"rotulos": [], "valores": []}
    _barras(ax, s["rotulos"], s["valores"], AZUL_CLARO)


def _g_faturamento_mes(ax, st):
    s = st["faturamento_mes"]
    _barras(ax, s["rotulos"], s["valores"], VERDE,
            fmt=lambda v: f"{v:,.0f}".replace(",", "."), inteiro=False)
    if sum(s["valores"]):
        ax.set_ylabel("R$", fontsize=8, color=TEXTO2)


def _g_formas(ax, st):
    _rosca(ax, st["formas"])


def _g_equipamentos(ax, st):
    _barras(ax, [e for e, _ in st["equipamentos"]], [v for _, v in st["equipamentos"]], AMBAR)


def _g_tempo(ax, st):
    t = st["tempo_resolucao"]
    if not t["valores"]:
        return _vazio(ax, "Nenhum chamado resolvido ainda")
    _barras_h(ax, t["rotulos"], t["valores"], ROXO, fmt=lambda v: f"{v:g} {t['unidade'][0]}")


def _g_recorrencia(ax, st):
    _barras(ax, [r for r, _ in st["recorrencia"]], [v for _, v in st["recorrencia"]], VERDE)


GRAFICOS = {
    "situacao": ("Chamados por situação", "Quantos estão abertos, em andamento ou resolvidos?",
                 _g_situacao),
    "problemas": ("Principais problemas", "Quais defeitos mais aparecem?", _g_problemas),
    "chamados_mes": ("Chamados por mês", "A demanda está subindo ou caindo?", _g_chamados_mes),
    "cadastros_mes": ("Novos cadastros por mês", "Quantos clientes novos chegam?",
                      _g_cadastros_mes),
    "faturamento_mes": ("Faturamento por mês", "Quanto foi pago a cada mês?",
                        _g_faturamento_mes),
    "formas": ("Formas de pagamento", "Pix, dinheiro, débito ou crédito?", _g_formas),
    "equipamentos": ("Chamados por equipamento", "Notebook, impressora, desktop...?",
                     _g_equipamentos),
    "tempo_resolucao": ("Tempo médio de resolução", "Qual problema demora mais para resolver?",
                        _g_tempo),
    "recorrencia": ("Recorrência dos pagamentos", "Mensalidade ou pagamento único?",
                    _g_recorrencia),
}

ORDEM_TECNICO = ["situacao", "problemas", "chamados_mes", "cadastros_mes", "faturamento_mes",
                 "formas", "equipamentos", "tempo_resolucao", "recorrencia"]
ORDEM_CLIENTE = ["situacao", "problemas", "chamados_mes", "faturamento_mes", "formas",
                 "tempo_resolucao"]
TITULOS_CLIENTE = {"faturamento_mes": "Meus pagamentos por mês",
                   "problemas": "Meus problemas mais frequentes"}


def criar_figura(chave, st, largura, altura, dpi=100):
    """Monta a figura de um gráfico (sem pyplot, então não acumula memória)."""
    fig = Figure(figsize=(max(largura, 200) / dpi, max(altura, 150) / dpi), dpi=dpi,
                 facecolor="white", layout="constrained")
    ax = fig.add_subplot(111)
    ax.set_facecolor("white")
    GRAFICOS[chave][2](ax, st)
    return fig