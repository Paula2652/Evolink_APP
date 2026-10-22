"""
EvoLink - banco de dados (SQLite)

Usa só a biblioteca padrão do Python (sqlite3): não precisa instalar nada.
O arquivo do banco é criado automaticamente em  dados_evolink.db  (mesma pasta).

Para criar o banco e ver um resumo:   python banco.py
Para abrir e explorar as tabelas:     DB Browser for SQLite  ou  extensão "SQLite Viewer" do VS Code.
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime

PASTA = os.path.dirname(os.path.abspath(__file__))
CAMINHO_BANCO = os.path.join(PASTA, "dados_evolink.db")
CAMINHO_JSON_ANTIGO = os.path.join(PASTA, "dados_evolink.json")

OUTROS = "Outros (especificar)"
# Quem digitar esse código no cadastro vira técnico. TROQUE por um código só seu.
CODIGO_TECNICO = "EVOLINK-TEC"
SITUACOES = ["Aberto", "Em andamento", "Aguardando peça", "Resolvido", "Cancelado"]
RECORRENCIAS = ["Única", "Mensal", "Trimestral", "Semestral", "Anual"]
TIPOS_PAGAMENTO = ["Pix", "Dinheiro", "Cartão de débito", "Cartão de crédito"]
TIPOS_EQUIPAMENTO = ["Notebook", "Desktop", "All-in-one", "Impressora", "Monitor",
                     "Roteador", "Outro"]


def _lista_sql(valores):
    return ", ".join("'" + v.replace("'", "''") + "'" for v in valores)


# ====================================================================== ESTRUTURA
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario  INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    telefone    TEXT NOT NULL DEFAULT '',
    endereco    TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL DEFAULT '',
    senha       TEXT NOT NULL,                -- nunca a senha pura: algoritmo$salt$hash
    tipo        TEXT NOT NULL DEFAULT 'cliente' CHECK (tipo IN ('cliente', 'tecnico')),
    criado_em   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS produtos (
    id_produto           INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario           INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    tipo                 TEXT NOT NULL DEFAULT 'Desktop',
    marca                TEXT NOT NULL,
    modelo               TEXT NOT NULL,
    sistema_operacional  TEXT NOT NULL DEFAULT '',
    numero_serie         TEXT NOT NULL DEFAULT '',
    observacoes          TEXT NOT NULL DEFAULT '',
    criado_em            TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS sintomas (
    id_sintoma         INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao_sintoma  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS solucoes (
    id_solucao         INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao_solucao  TEXT NOT NULL UNIQUE,
    passo_a_passo      TEXT NOT NULL DEFAULT ''   -- um passo por linha
);

CREATE TABLE IF NOT EXISTS causas (
    id_causa         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_sintoma       INTEGER NOT NULL REFERENCES sintomas(id_sintoma) ON DELETE CASCADE,
    descricao_causa  TEXT NOT NULL,
    UNIQUE (id_sintoma, descricao_causa)
);

-- defeitos liga cada sintoma às soluções possíveis (relação N:N)
CREATE TABLE IF NOT EXISTS defeitos (
    id_defeito  INTEGER PRIMARY KEY AUTOINCREMENT,
    id_sintoma  INTEGER NOT NULL REFERENCES sintomas(id_sintoma) ON DELETE CASCADE,
    id_solucao  INTEGER NOT NULL REFERENCES solucoes(id_solucao) ON DELETE CASCADE,
    ordem       INTEGER NOT NULL DEFAULT 1,       -- ordem em que a solução é sugerida
    UNIQUE (id_sintoma, id_solucao)
);

CREATE TABLE IF NOT EXISTS chamados (
    id_chamado          INTEGER PRIMARY KEY AUTOINCREMENT,
    id_cliente          INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    id_produto          INTEGER REFERENCES produtos(id_produto) ON DELETE SET NULL,
    id_sintoma          INTEGER NOT NULL REFERENCES sintomas(id_sintoma),
    situacao_chamado    TEXT NOT NULL DEFAULT 'Aberto'
                        CHECK (situacao_chamado IN ({_lista_sql(SITUACOES)})),
    outro_sintoma       TEXT NOT NULL DEFAULT '',  -- usado quando o sintoma é "Outros"
    descricao_problema  TEXT NOT NULL DEFAULT '',
    data_abertura       TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    data_fechamento     TEXT
);

CREATE TABLE IF NOT EXISTS pagamentos (
    id_pagamento      INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario        INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    id_chamado        INTEGER REFERENCES chamados(id_chamado) ON DELETE SET NULL,  -- vazio = plano/mensalidade
    preco_pago        REAL NOT NULL CHECK (preco_pago >= 0),   -- valor final, já com desconto
    desconto          REAL NOT NULL DEFAULT 0 CHECK (desconto >= 0),
    recorrencia       TEXT NOT NULL DEFAULT 'Única'
                      CHECK (recorrencia IN ({_lista_sql(RECORRENCIAS)})),
    periodo_pagamento TEXT NOT NULL DEFAULT '',                -- ex.: 10/2026
    tipo_pagamento    TEXT NOT NULL
                      CHECK (tipo_pagamento IN ({_lista_sql(TIPOS_PAGAMENTO)})),
    data_pagamento    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_produtos_usuario  ON produtos(id_usuario);
CREATE INDEX IF NOT EXISTS idx_chamados_cliente  ON chamados(id_cliente);
CREATE INDEX IF NOT EXISTS idx_chamados_produto  ON chamados(id_produto);
CREATE INDEX IF NOT EXISTS idx_chamados_sintoma  ON chamados(id_sintoma);
CREATE INDEX IF NOT EXISTS idx_causas_sintoma    ON causas(id_sintoma);
CREATE INDEX IF NOT EXISTS idx_defeitos_sintoma  ON defeitos(id_sintoma);
CREATE INDEX IF NOT EXISTS idx_pagamentos_user   ON pagamentos(id_usuario);
CREATE INDEX IF NOT EXISTS idx_pagamentos_chamad ON pagamentos(id_chamado);
"""

# ====================================================================== DADOS INICIAIS
# (sintoma, [causas], [(solução, passo a passo), ...])
SEED = [
    ("Computador lento",
     ["Muitos programas abertos ao mesmo tempo", "Pouca memória RAM disponível",
      "Disco quase cheio"],
     [("Fechar programas desnecessários",
       "1. Pressione Ctrl + Shift + Esc para abrir o Gerenciador de Tarefas.\n"
       "2. Na aba \"Processos\", ordene pela coluna Memória ou CPU.\n"
       "3. Selecione o programa que você não está usando e clique em \"Finalizar tarefa\".\n"
       "4. Salve seu trabalho antes de fechar qualquer programa."),
      ("Limpar arquivos temporários",
       "1. Pressione Windows + R, digite %temp% e tecle Enter.\n"
       "2. Selecione tudo (Ctrl + A) e pressione Delete.\n"
       "3. Se aparecer aviso de arquivo em uso, clique em \"Ignorar\".\n"
       "4. Esvazie a Lixeira em seguida."),
      ("Reiniciar o computador",
       "1. Salve seus arquivos e feche os programas.\n"
       "2. Clique em Iniciar > Energia > Reiniciar.\n"
       "3. Aguarde o computador ligar novamente e teste o problema.")]),

    ("Computador não liga",
     ["Cabo de energia desconectado", "Fonte de alimentação com defeito",
      "Tomada sem energia"],
     [("Verificar o cabo de energia",
       "1. Desligue a chave da fonte (atrás do gabinete) e tire o cabo da tomada.\n"
       "2. Confira se o cabo está bem encaixado na fonte e na tomada.\n"
       "3. Procure cabo dobrado, rachado ou com mau contato; se houver, troque.\n"
       "4. Religue tudo e tente ligar o computador."),
      ("Testar em outra tomada",
       "1. Ligue o cabo em outra tomada ou régua que você sabe que funciona.\n"
       "2. Se usar estabilizador ou régua, confira se está ligado.\n"
       "3. Tente ligar o computador."),
      ("Chamar o técnico para revisar a fonte",
       "1. Não abra a fonte nem mexa dentro do gabinete ligado na tomada.\n"
       "2. Anote o que acontece (nenhuma luz, liga e desliga, cheiro de queimado).\n"
       "3. Abra um chamado com essas informações e aguarde o técnico.")]),

    ("Internet sem conexão",
     ["Cabo de rede desconectado", "Roteador travado ou fora do ar",
      "Configuração de Wi-Fi incorreta"],
     [("Verificar o cabo de rede",
       "1. Confira se o cabo está encaixado no computador e no roteador.\n"
       "2. Observe as luzinhas da entrada de rede: devem estar acesas ou piscando.\n"
       "3. Se possível, teste com outro cabo."),
      ("Conferir a conexão Wi-Fi",
       "1. Clique no ícone de rede na barra de tarefas.\n"
       "2. Verifique se o Wi-Fi está ligado e se o Modo Avião está desativado.\n"
       "3. Escolha a rede correta e digite a senha novamente, se pedir."),
      ("Reiniciar o roteador",
       "1. Desligue o roteador da tomada.\n"
       "2. Aguarde 30 segundos.\n"
       "3. Ligue novamente e espere as luzes estabilizarem (cerca de 2 minutos).\n"
       "4. Teste a conexão.")]),

    ("Impressora não imprime",
     ["Impressora sem papel ou tinta", "Fila de impressão travada",
      "Driver desatualizado"],
     [("Verificar papel e nível de tinta",
       "1. Confira se há papel na bandeja e se não está enroscado.\n"
       "2. Veja o nível de tinta ou toner no painel da impressora.\n"
       "3. Abra as tampas e procure papel atolado; observe luzes de erro piscando."),
      ("Limpar a fila de impressão",
       "1. Pressione Windows + R, digite services.msc e tecle Enter.\n"
       "2. Clique com o botão direito em \"Spooler de impressão\" e escolha \"Parar\".\n"
       "3. Abra C:\\Windows\\System32\\spool\\PRINTERS e apague os arquivos dentro da pasta.\n"
       "4. Volte aos serviços e clique em \"Iniciar\" no Spooler de impressão."),
      ("Reinstalar o driver da impressora",
       "1. Abra Configurações > Bluetooth e dispositivos > Impressoras e scanners e remova a impressora.\n"
       "2. Baixe o driver mais recente no site do fabricante.\n"
       "3. Instale o driver e reinicie o computador.\n"
       "4. Adicione a impressora de novo e imprima uma página de teste.")]),

    ("Teclado ou mouse com defeito",
     ["Cabo USB solto ou danificado", "Pilhas fracas (dispositivo sem fio)",
      "Porta USB com defeito"],
     [("Reconectar o cabo em outra porta USB",
       "1. Desconecte o cabo do teclado ou do mouse.\n"
       "2. Conecte em outra porta USB (de preferência atrás do gabinete).\n"
       "3. Aguarde o Windows reconhecer o dispositivo."),
      ("Trocar as pilhas do dispositivo",
       "1. Desligue o dispositivo e abra o compartimento das pilhas.\n"
       "2. Troque por pilhas novas, atento à posição (+ e -).\n"
       "3. Ligue e confira se o receptor USB está conectado."),
      ("Testar em outro computador",
       "1. Conecte o teclado ou o mouse em outro computador.\n"
       "2. Se funcionar lá, o defeito está no seu computador (porta ou driver).\n"
       "3. Se também não funcionar, o dispositivo está com defeito e precisa ser trocado.")]),

    ("Monitor sem imagem",
     ["Cabo de vídeo desconectado", "Monitor desligado ou em economia de energia",
      "Placa de vídeo com defeito"],
     [("Verificar o cabo de vídeo",
       "1. Confira se o cabo (HDMI, VGA ou DisplayPort) está bem encaixado no monitor e no computador.\n"
       "2. Se tiver parafusos (VGA), aperte-os.\n"
       "3. Se possível, teste com outro cabo.\n"
       "4. Se houver placa de vídeo dedicada, use a saída da placa de vídeo."),
      ("Checar o botão de energia do monitor",
       "1. Veja se a luz de energia do monitor está acesa.\n"
       "2. Aperte o botão de energia e mexa o mouse para sair da economia de energia.\n"
       "3. Use o botão de entrada (Input/Source) para escolher a porta correta."),
      ("Testar o monitor em outra máquina",
       "1. Ligue o monitor em outro computador.\n"
       "2. Se aparecer imagem, o problema está no computador original (cabo ou placa de vídeo).\n"
       "3. Se continuar sem imagem, o monitor precisa de reparo.")]),

    ("Erro ao abrir programas",
     ["Arquivo do programa corrompido", "Falta de atualização do sistema",
      "Conflito com antivírus"],
     [("Reiniciar o computador",
       "1. Salve seus arquivos e feche os programas.\n"
       "2. Clique em Iniciar > Energia > Reiniciar.\n"
       "3. Aguarde o computador ligar novamente e teste o problema."),
      ("Reinstalar o programa",
       "1. Abra Configurações > Aplicativos > Aplicativos instalados.\n"
       "2. Localize o programa, clique nos três pontos e em \"Desinstalar\".\n"
       "3. Baixe o instalador atualizado no site oficial.\n"
       "4. Instale novamente e abra o programa."),
      ("Atualizar o sistema operacional",
       "1. Abra Configurações > Windows Update.\n"
       "2. Clique em \"Verificar se há atualizações\".\n"
       "3. Instale tudo o que for encontrado e reinicie o computador.")]),

    ("Espaço insuficiente no disco",
     ["Muitos arquivos temporários acumulados", "Downloads e instaladores antigos",
      "Lixeira cheia"],
     [("Esvaziar a lixeira",
       "1. Antes, confira se não há nada importante dentro da Lixeira.\n"
       "2. Clique com o botão direito no ícone da Lixeira.\n"
       "3. Escolha \"Esvaziar Lixeira\" e confirme."),
      ("Remover arquivos temporários",
       "1. Abra Configurações > Sistema > Armazenamento.\n"
       "2. Clique em \"Arquivos temporários\".\n"
       "3. Marque o que deseja apagar (não marque Downloads se ainda precisa deles).\n"
       "4. Clique em \"Remover arquivos\"."),
      ("Desinstalar programas não utilizados",
       "1. Abra Configurações > Aplicativos > Aplicativos instalados.\n"
       "2. Ordene por tamanho.\n"
       "3. Desinstale os programas que você não usa mais.\n"
       "4. Apague também instaladores antigos da pasta Downloads.")]),

    (OUTROS,
     ["Problema não listado - descreva nos detalhes"],
     [("Descreva o problema com o máximo de detalhes",
       "1. No campo \"Defeito e informações\", escreva o que está acontecendo.\n"
       "2. Informe quando começou e se aparece alguma mensagem de erro.\n"
       "3. Diga o que você já tentou fazer."),
      ("Aguarde o contato do técnico",
       "1. Mantenha o equipamento como está (não tente consertar por conta própria).\n"
       "2. Deixe telefone e e-mail atualizados na tela Usuário.\n"
       "3. Aguarde o contato do técnico.")]),
]


# ====================================================================== SENHAS
def _hash_senha(senha, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), bytes.fromhex(salt), 200_000)
    return f"pbkdf2${salt}${h.hex()}"


def _confere_senha(senha, guardada):
    try:
        algoritmo, salt, h = guardada.split("$")
    except ValueError:
        return False
    if algoritmo == "pbkdf2":
        novo = _hash_senha(senha, salt).split("$")[2]
    elif algoritmo == "sha256":  # formato da versão antiga (arquivo JSON)
        novo = hashlib.sha256((salt + senha).encode("utf-8")).hexdigest()
    else:
        return False
    return hmac.compare_digest(novo, h)


# ====================================================================== ACESSO AO BANCO
class Banco:
    def __init__(self, caminho=None):
        self.caminho = caminho or CAMINHO_BANCO
        self.con = sqlite3.connect(self.caminho)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.executescript(SCHEMA)
        self._atualizar_estrutura()
        self._semear()
        self._migrar_json_antigo()

    def fechar(self):
        self.con.close()

    # ---------------------------------------------------------------- bancos de versões antigas
    def _atualizar_estrutura(self):
        colunas = [r["name"] for r in self.con.execute("PRAGMA table_info(usuarios)")]
        if "tipo" not in colunas:
            with self.con:
                self.con.execute("ALTER TABLE usuarios ADD COLUMN tipo TEXT NOT NULL "
                                 "DEFAULT 'cliente' CHECK (tipo IN ('cliente', 'tecnico'))")

    # ---------------------------------------------------------------- dados iniciais
    def _semear(self):
        if self.con.execute("SELECT COUNT(*) FROM sintomas").fetchone()[0]:
            return
        with self.con:
            for sintoma, causas, solucoes in SEED:
                id_sintoma = self.con.execute(
                    "INSERT INTO sintomas (descricao_sintoma) VALUES (?)", (sintoma,)
                ).lastrowid
                for causa in causas:
                    self.con.execute(
                        "INSERT INTO causas (id_sintoma, descricao_causa) VALUES (?, ?)",
                        (id_sintoma, causa))
                for ordem, (desc, passos) in enumerate(solucoes, start=1):
                    self.con.execute(
                        "INSERT OR IGNORE INTO solucoes (descricao_solucao, passo_a_passo) "
                        "VALUES (?, ?)", (desc, passos))
                    id_solucao = self.con.execute(
                        "SELECT id_solucao FROM solucoes WHERE descricao_solucao = ?",
                        (desc,)).fetchone()[0]
                    self.con.execute(
                        "INSERT INTO defeitos (id_sintoma, id_solucao, ordem) VALUES (?, ?, ?)",
                        (id_sintoma, id_solucao, ordem))

    # ---------------------------------------------------------------- usuários
    def criar_usuario(self, nome, senha, tipo="cliente"):
        try:
            with self.con:
                return self.con.execute(
                    "INSERT INTO usuarios (nome, senha, tipo) VALUES (?, ?, ?)",
                    (nome.strip(), _hash_senha(senha), tipo)).lastrowid
        except sqlite3.IntegrityError:
            raise ValueError("nome já cadastrado")

    def autenticar(self, nome, senha):
        u = self.con.execute("SELECT * FROM usuarios WHERE nome = ?", (nome.strip(),)).fetchone()
        if u is None or not _confere_senha(senha, u["senha"]):
            return None
        if not u["senha"].startswith("pbkdf2$"):  # atualiza hash antigo para o formato novo
            with self.con:
                self.con.execute("UPDATE usuarios SET senha = ? WHERE id_usuario = ?",
                                 (_hash_senha(senha), u["id_usuario"]))
        return u

    def obter_usuario(self, id_usuario):
        return self.con.execute("SELECT * FROM usuarios WHERE id_usuario = ?",
                                (id_usuario,)).fetchone()

    def atualizar_usuario(self, id_usuario, nome, telefone, endereco, email):
        try:
            with self.con:
                self.con.execute(
                    "UPDATE usuarios SET nome=?, telefone=?, endereco=?, email=? "
                    "WHERE id_usuario=?", (nome.strip(), telefone, endereco, email, id_usuario))
        except sqlite3.IntegrityError:
            raise ValueError("nome já cadastrado")

    # ---------------------------------------------------------------- produtos
    def listar_produtos(self, id_usuario):
        return self.con.execute(
            "SELECT * FROM produtos WHERE id_usuario = ? ORDER BY id_produto DESC",
            (id_usuario,)).fetchall()

    def criar_produto(self, id_usuario, tipo, marca, modelo, sistema_operacional="",
                      numero_serie="", observacoes=""):
        with self.con:
            return self.con.execute(
                "INSERT INTO produtos (id_usuario, tipo, marca, modelo, sistema_operacional, "
                "numero_serie, observacoes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (id_usuario, tipo, marca, modelo, sistema_operacional, numero_serie,
                 observacoes)).lastrowid

    def excluir_produto(self, id_produto, id_usuario):
        with self.con:
            self.con.execute("DELETE FROM produtos WHERE id_produto = ? AND id_usuario = ?",
                             (id_produto, id_usuario))

    # ---------------------------------------------------------------- sintomas / soluções
    def listar_sintomas(self):
        return self.con.execute(
            "SELECT id_sintoma, descricao_sintoma FROM sintomas ORDER BY id_sintoma").fetchall()

    def diagnostico(self, id_sintoma):
        """Causas e soluções (com passo a passo) de um sintoma."""
        s = self.con.execute("SELECT * FROM sintomas WHERE id_sintoma = ?",
                             (id_sintoma,)).fetchone()
        causas = [r[0] for r in self.con.execute(
            "SELECT descricao_causa FROM causas WHERE id_sintoma = ? ORDER BY id_causa",
            (id_sintoma,))]
        solucoes = [
            {"id_solucao": r["id_solucao"], "descricao": r["descricao_solucao"],
             "passos": r["passo_a_passo"]}
            for r in self.con.execute(
                "SELECT so.id_solucao, so.descricao_solucao, so.passo_a_passo "
                "FROM defeitos d JOIN solucoes so ON so.id_solucao = d.id_solucao "
                "WHERE d.id_sintoma = ? ORDER BY d.ordem", (id_sintoma,))]
        return {"id_sintoma": id_sintoma, "descricao": s["descricao_sintoma"],
                "causas": causas, "solucoes": solucoes}

    # ---------------------------------------------------------------- chamados
    def criar_chamado(self, id_cliente, id_sintoma, id_produto=None, outro_sintoma="",
                      descricao_problema=""):
        with self.con:
            return self.con.execute(
                "INSERT INTO chamados (id_cliente, id_produto, id_sintoma, outro_sintoma, "
                "descricao_problema) VALUES (?, ?, ?, ?, ?)",
                (id_cliente, id_produto, id_sintoma, outro_sintoma,
                 descricao_problema)).lastrowid

    def atualizar_situacao(self, id_chamado, situacao):
        if situacao not in SITUACOES:
            raise ValueError("situação inválida")
        fechamento = "datetime('now','localtime')" if situacao in ("Resolvido", "Cancelado") else "NULL"
        with self.con:
            self.con.execute(
                f"UPDATE chamados SET situacao_chamado = ?, data_fechamento = {fechamento} "
                "WHERE id_chamado = ?", (situacao, id_chamado))

    def listar_chamados(self, id_cliente):
        return self.con.execute(
            """
            SELECT c.id_chamado, c.situacao_chamado, c.data_abertura, c.outro_sintoma,
                   c.descricao_problema, s.descricao_sintoma, p.marca, p.modelo,
                   (SELECT SUM(g.preco_pago) FROM pagamentos g
                     WHERE g.id_chamado = c.id_chamado) AS total_pago,
                   (SELECT g.tipo_pagamento FROM pagamentos g
                     WHERE g.id_chamado = c.id_chamado
                     ORDER BY g.id_pagamento DESC LIMIT 1) AS tipo_pagamento
              FROM chamados c
              JOIN sintomas s ON s.id_sintoma = c.id_sintoma
              LEFT JOIN produtos p ON p.id_produto = c.id_produto
             WHERE c.id_cliente = ?
             ORDER BY c.id_chamado DESC
            """, (id_cliente,)).fetchall()

    def listar_todos_chamados(self, situacao=None):
        """Para o painel do técnico: chamados de todos os clientes (abertos primeiro)."""
        return self.con.execute(
            """
            SELECT c.id_chamado, c.situacao_chamado, c.data_abertura, c.outro_sintoma,
                   c.descricao_problema, s.descricao_sintoma, p.marca, p.modelo,
                   u.nome AS nome_cliente, u.telefone
              FROM chamados c
              JOIN usuarios u ON u.id_usuario = c.id_cliente
              JOIN sintomas s ON s.id_sintoma = c.id_sintoma
              LEFT JOIN produtos p ON p.id_produto = c.id_produto
             WHERE (? IS NULL OR c.situacao_chamado = ?)
             ORDER BY CASE WHEN c.situacao_chamado IN ('Resolvido', 'Cancelado') THEN 1 ELSE 0 END,
                      c.id_chamado DESC
            """, (situacao, situacao)).fetchall()

    # ---------------------------------------------------------------- pagamentos
    def registrar_pagamento(self, id_usuario, preco_pago, tipo_pagamento, id_chamado=None,
                            desconto=0.0, recorrencia="Única", periodo_pagamento=""):
        with self.con:
            return self.con.execute(
                "INSERT INTO pagamentos (id_usuario, id_chamado, preco_pago, desconto, "
                "recorrencia, periodo_pagamento, tipo_pagamento) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (id_usuario, id_chamado, preco_pago, desconto, recorrencia,
                 periodo_pagamento, tipo_pagamento)).lastrowid

    def total_pago(self, id_usuario):
        return self.con.execute(
            "SELECT COALESCE(SUM(preco_pago), 0) FROM pagamentos WHERE id_usuario = ?",
            (id_usuario,)).fetchone()[0]

    # ---------------------------------------------------------------- migração do JSON antigo
    def _migrar_json_antigo(self):
        """Se existir o dados_evolink.json da versão anterior e o banco estiver vazio,
        importa usuários e chamados e renomeia o JSON para .migrado."""
        if not os.path.exists(CAMINHO_JSON_ANTIGO):
            return
        if self.con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]:
            return
        try:
            with open(CAMINHO_JSON_ANTIGO, "r", encoding="utf-8") as f:
                antigo = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        sintomas = {r["descricao_sintoma"]: r["id_sintoma"] for r in self.listar_sintomas()}
        ids = {}
        with self.con:
            for chave, reg in antigo.get("usuarios", {}).items():
                perfil = reg.get("perfil", {})
                ids[chave] = self.con.execute(
                    "INSERT INTO usuarios (nome, telefone, endereco, email, senha) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (perfil.get("nome") or chave, perfil.get("telefone", ""),
                     perfil.get("endereco", ""), perfil.get("email", ""),
                     f"sha256${reg['salt']}${reg['hash']}")).lastrowid
            for c in antigo.get("chamados", []):
                id_usuario = ids.get(c.get("usuario"))
                if id_usuario is None:
                    continue
                try:
                    dt = datetime.strptime(c.get("data", ""), "%d/%m/%Y %H:%M")
                except ValueError:
                    dt = datetime.now()
                categoria = c.get("categoria") or ""
                id_sintoma = sintomas.get(categoria, sintomas[OUTROS])
                outro = ""
                if id_sintoma == sintomas[OUTROS]:
                    outro = c.get("problema", "").replace("Outros:", "").strip()
                id_chamado = self.con.execute(
                    "INSERT INTO chamados (id_cliente, id_sintoma, outro_sintoma, "
                    "descricao_problema, data_abertura) VALUES (?, ?, ?, ?, ?)",
                    (id_usuario, id_sintoma, outro, c.get("informacoes", ""),
                     dt.strftime("%Y-%m-%d %H:%M:%S"))).lastrowid
                if c.get("pago"):
                    forma = c.get("forma") if c.get("forma") in TIPOS_PAGAMENTO else "Dinheiro"
                    self.con.execute(
                        "INSERT INTO pagamentos (id_usuario, id_chamado, preco_pago, "
                        "periodo_pagamento, tipo_pagamento, data_pagamento) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (id_usuario, id_chamado, float(c.get("valor", 0)),
                         dt.strftime("%m/%Y"), forma, dt.strftime("%Y-%m-%d %H:%M:%S")))
        try:
            os.replace(CAMINHO_JSON_ANTIGO, CAMINHO_JSON_ANTIGO + ".migrado")
        except OSError:
            pass


if __name__ == "__main__":
    b = Banco()
    print(f"Banco criado/aberto em: {b.caminho}\n")
    for tabela in ["usuarios", "produtos", "chamados", "sintomas", "solucoes",
                   "causas", "defeitos", "pagamentos"]:
        n = b.con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
        print(f"  {tabela:<11} {n:>3} registro(s)")
    b.fechar()
