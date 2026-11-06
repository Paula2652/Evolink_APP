"""
EvoLink - banco de dados (MySQL)

Precisa da biblioteca:   pip install mysql-connector-python
O servidor MySQL precisa estar ligado (o mesmo que o MySQL Workbench usa).

A SENHA do banco NÃO fica neste arquivo. Ela vem da variável de ambiente
EVOLINK_DB_PASSWORD. No PowerShell do Windows (rode uma vez e reabra o VS Code):
    setx EVOLINK_DB_PASSWORD "sua_senha_aqui"
Se o servidor/usuário/porta forem outros, use também EVOLINK_DB_HOST,
EVOLINK_DB_PORT e EVOLINK_DB_USER (o padrão abaixo é o da Aiven).

O banco "evolink_app" e as tabelas são criados automaticamente na primeira execução.

Para criar o banco e ver um resumo:   python banco.py
Para explorar as tabelas:             MySQL Workbench  (schema "evolink_app")
"""
import hashlib
import hmac
import json
import os
import secrets
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal

try:
    import mysql.connector
except ImportError:  # o app mostra um aviso amigável em vez de quebrar
    mysql = None

PASTA = os.path.dirname(os.path.abspath(__file__))
CAMINHO_JSON_ANTIGO = os.path.join(PASTA, "dados_evolink.json")

# ====================================================================== CONEXÃO
# Nada de senha escrita aqui: ela vem da variável de ambiente EVOLINK_DB_PASSWORD.
CONFIG_MYSQL = {
    "host": os.environ.get("EVOLINK_DB_HOST", ""),
    "port": int(os.environ.get("EVOLINK_DB_PORT", "")),
    "user": os.environ.get("EVOLINK_DB_USER", ""),
    "password": os.environ.get("EVOLINK_DB_PASSWORD", ""),
}
NOME_BANCO = "evolink_app"

OUTROS = "Outros (especificar)"
# Quem digitar esse código no cadastro vira técnico. TROQUE por um código só seu.
CODIGO_TECNICO = "EVOLINK-TEC"
SITUACOES = ["Aberto", "Em andamento", "Aguardando peça", "Resolvido", "Cancelado"]
RECORRENCIAS = ["Única", "Mensal", "Trimestral", "Semestral", "Anual"]
TIPOS_PAGAMENTO = ["Pix", "Dinheiro", "Cartão de débito", "Cartão de crédito"]
TIPOS_EQUIPAMENTO = ["Notebook", "Desktop", "All-in-one", "Impressora", "Monitor",
                     "Roteador", "Outro"]


class ErroBanco(Exception):
    """Erro de conexão/uso do banco, com mensagem pronta para mostrar ao usuário."""


def _lista_sql(valores):
    return ", ".join("'" + v.replace("'", "''") + "'" for v in valores)


# ====================================================================== ESTRUTURA
# Uma instrução por item. O mesmo texto vira o arquivo schema_mysql.sql.
_TABELA = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"

ESQUEMA = [
    f"""CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario  INT NOT NULL AUTO_INCREMENT,
    nome        VARCHAR(150) NOT NULL,
    telefone    VARCHAR(50)  NOT NULL DEFAULT '',
    endereco    VARCHAR(255) NOT NULL DEFAULT '',
    email       VARCHAR(255) NOT NULL DEFAULT '',
    senha       VARCHAR(255) NOT NULL COMMENT 'nunca a senha pura: algoritmo$salt$hash',
    tipo        ENUM('cliente', 'tecnico') NOT NULL DEFAULT 'cliente',
    criado_em   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_usuario),
    UNIQUE KEY uq_usuarios_nome (nome)
) {_TABELA}""",

    f"""CREATE TABLE IF NOT EXISTS produtos (
    id_produto           INT NOT NULL AUTO_INCREMENT,
    id_usuario           INT NOT NULL,
    tipo                 VARCHAR(50)  NOT NULL DEFAULT 'Desktop',
    marca                VARCHAR(255) NOT NULL,
    modelo               VARCHAR(255) NOT NULL,
    sistema_operacional  VARCHAR(255) NOT NULL DEFAULT '',
    numero_serie         VARCHAR(255) NOT NULL DEFAULT '',
    observacoes          TEXT NOT NULL,
    criado_em            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_produto),
    CONSTRAINT fk_produtos_usuario FOREIGN KEY (id_usuario)
        REFERENCES usuarios (id_usuario) ON DELETE CASCADE
) {_TABELA}""",

    f"""CREATE TABLE IF NOT EXISTS sintomas (
    id_sintoma         INT NOT NULL AUTO_INCREMENT,
    descricao_sintoma  VARCHAR(255) NOT NULL,
    PRIMARY KEY (id_sintoma),
    UNIQUE KEY uq_sintomas_descricao (descricao_sintoma)
) {_TABELA}""",

    f"""CREATE TABLE IF NOT EXISTS solucoes (
    id_solucao         INT NOT NULL AUTO_INCREMENT,
    descricao_solucao  VARCHAR(255) NOT NULL,
    passo_a_passo      TEXT NOT NULL COMMENT 'um passo por linha',
    PRIMARY KEY (id_solucao),
    UNIQUE KEY uq_solucoes_descricao (descricao_solucao)
) {_TABELA}""",

    f"""CREATE TABLE IF NOT EXISTS causas (
    id_causa         INT NOT NULL AUTO_INCREMENT,
    id_sintoma       INT NOT NULL,
    descricao_causa  VARCHAR(255) NOT NULL,
    PRIMARY KEY (id_causa),
    UNIQUE KEY uq_causas (id_sintoma, descricao_causa),
    CONSTRAINT fk_causas_sintoma FOREIGN KEY (id_sintoma)
        REFERENCES sintomas (id_sintoma) ON DELETE CASCADE
) {_TABELA}""",

    # defeitos liga cada sintoma às soluções possíveis (relação N:N)
    f"""CREATE TABLE IF NOT EXISTS defeitos (
    id_defeito  INT NOT NULL AUTO_INCREMENT,
    id_sintoma  INT NOT NULL,
    id_solucao  INT NOT NULL,
    ordem       INT NOT NULL DEFAULT 1 COMMENT 'ordem em que a solução é sugerida',
    PRIMARY KEY (id_defeito),
    UNIQUE KEY uq_defeitos (id_sintoma, id_solucao),
    CONSTRAINT fk_defeitos_sintoma FOREIGN KEY (id_sintoma)
        REFERENCES sintomas (id_sintoma) ON DELETE CASCADE,
    CONSTRAINT fk_defeitos_solucao FOREIGN KEY (id_solucao)
        REFERENCES solucoes (id_solucao) ON DELETE CASCADE
) {_TABELA}""",

    f"""CREATE TABLE IF NOT EXISTS chamados (
    id_chamado          INT NOT NULL AUTO_INCREMENT,
    id_cliente          INT NOT NULL,
    id_produto          INT NULL,
    id_sintoma          INT NOT NULL,
    situacao_chamado    ENUM({_lista_sql(SITUACOES)}) NOT NULL DEFAULT 'Aberto',
    outro_sintoma       VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'usado quando o sintoma é Outros',
    descricao_problema  TEXT NOT NULL,
    data_abertura       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data_fechamento     DATETIME NULL,
    PRIMARY KEY (id_chamado),
    CONSTRAINT fk_chamados_cliente FOREIGN KEY (id_cliente)
        REFERENCES usuarios (id_usuario) ON DELETE CASCADE,
    CONSTRAINT fk_chamados_produto FOREIGN KEY (id_produto)
        REFERENCES produtos (id_produto) ON DELETE SET NULL,
    CONSTRAINT fk_chamados_sintoma FOREIGN KEY (id_sintoma)
        REFERENCES sintomas (id_sintoma)
) {_TABELA}""",

    f"""CREATE TABLE IF NOT EXISTS pagamentos (
    id_pagamento       INT NOT NULL AUTO_INCREMENT,
    id_usuario         INT NOT NULL,
    id_chamado         INT NULL COMMENT 'vazio = plano/mensalidade',
    preco_pago         DECIMAL(10,2) NOT NULL COMMENT 'valor final, já com desconto',
    desconto           DECIMAL(10,2) NOT NULL DEFAULT 0,
    recorrencia        ENUM({_lista_sql(RECORRENCIAS)}) NOT NULL DEFAULT 'Única',
    periodo_pagamento  VARCHAR(20) NOT NULL DEFAULT '' COMMENT 'ex.: 10/2026',
    tipo_pagamento     ENUM({_lista_sql(TIPOS_PAGAMENTO)}) NOT NULL,
    data_pagamento     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_pagamento),
    CONSTRAINT ck_pagamentos_preco CHECK (preco_pago >= 0),
    CONSTRAINT ck_pagamentos_desconto CHECK (desconto >= 0),
    CONSTRAINT fk_pagamentos_usuario FOREIGN KEY (id_usuario)
        REFERENCES usuarios (id_usuario) ON DELETE CASCADE,
    CONSTRAINT fk_pagamentos_chamado FOREIGN KEY (id_chamado)
        REFERENCES chamados (id_chamado) ON DELETE SET NULL
) {_TABELA}""",
]
# (o MySQL cria sozinho os índices das chaves estrangeiras, por isso não há CREATE INDEX)

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
    def __init__(self):
        if mysql is None:
            raise ErroBanco("A biblioteca do MySQL não está instalada.\n\n"
                            "No terminal do VS Code, rode:\n"
                            "pip install mysql-connector-python")
        if not CONFIG_MYSQL["password"]:
            raise ErroBanco("A senha do banco ainda não foi definida.\n\n"
                            "No PowerShell, rode (troque pela sua senha):\n"
                            "setx EVOLINK_DB_PASSWORD \"sua_senha_aqui\"\n\n"
                            "Depois feche e abra o VS Code e execute o EvoLink de novo.")
        try:
            self.con = mysql.connector.connect(
                **CONFIG_MYSQL, charset="utf8mb4", collation="utf8mb4_unicode_ci",
                autocommit=True, connection_timeout=10)
            cur = self.con.cursor()
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{NOME_BANCO}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.close()
            self.con.database = NOME_BANCO
        except mysql.connector.Error as e:
            raise ErroBanco("Não consegui conectar ao MySQL.\n\n"
                            f"Detalhe: {e}\n\n"
                            "Confira se o MySQL está ligado e se usuário, servidor e a "
                            "senha (variável EVOLINK_DB_PASSWORD) estão corretos.") from e
        for instrucao in ESQUEMA:
            self._executar(instrucao)
        self._semear()
        self._migrar_json_antigo()

    def fechar(self):
        try:
            self.con.close()
        except mysql.connector.Error:
            pass

    # ---------------------------------------------------------------- ferramentas internas
    def _garantir_conexao(self):
        """O MySQL fecha conexões paradas por muito tempo; aqui a reabrimos se precisar."""
        try:
            self.con.ping(reconnect=True, attempts=3, delay=1)
        except mysql.connector.Error as e:
            raise ErroBanco(f"Perdi a conexão com o MySQL: {e}") from e

    @staticmethod
    def _converter(linha):
        """Datas viram texto 'AAAA-MM-DD HH:MM:SS' e valores DECIMAL viram float,
        para o app funcionar igual ao tempo do SQLite."""
        if linha is None:
            return None
        for chave, valor in linha.items():
            if isinstance(valor, datetime):
                linha[chave] = valor.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(valor, Decimal):
                linha[chave] = float(valor)
        return linha

    def _consultar(self, sql, params=()):
        """SELECT que devolve uma lista de dicionários."""
        self._garantir_conexao()
        cur = self.con.cursor(dictionary=True)
        try:
            cur.execute(sql, params)
            return [self._converter(l) for l in cur.fetchall()]
        finally:
            cur.close()

    def _um(self, sql, params=()):
        """SELECT que devolve só a primeira linha (ou None)."""
        linhas = self._consultar(sql, params)
        return linhas[0] if linhas else None

    def _valor(self, sql, params=()):
        """SELECT que devolve só o primeiro valor da primeira linha."""
        linha = self._um(sql, params)
        return next(iter(linha.values())) if linha else None

    def _executar(self, sql, params=()):
        """INSERT/UPDATE/DELETE/CREATE. Devolve o id gerado (quando houver)."""
        self._garantir_conexao()
        cur = self.con.cursor()
        try:
            cur.execute(sql, params)
            return cur.lastrowid
        finally:
            cur.close()

    @contextmanager
    def _transacao(self):
        """Agrupa várias instruções: ou grava tudo, ou não grava nada."""
        self._garantir_conexao()
        self.con.start_transaction()
        try:
            yield
            self.con.commit()
        except Exception:
            self.con.rollback()
            raise

    # ---------------------------------------------------------------- dados iniciais
    def _semear(self):
        if self._valor("SELECT COUNT(*) FROM sintomas"):
            return
        with self._transacao():
            for sintoma, causas, solucoes in SEED:
                id_sintoma = self._executar(
                    "INSERT INTO sintomas (descricao_sintoma) VALUES (%s)", (sintoma,))
                for causa in causas:
                    self._executar(
                        "INSERT INTO causas (id_sintoma, descricao_causa) VALUES (%s, %s)",
                        (id_sintoma, causa))
                for ordem, (desc, passos) in enumerate(solucoes, start=1):
                    self._executar(
                        "INSERT INTO solucoes (descricao_solucao, passo_a_passo) "
                        "VALUES (%s, %s) "
                        "ON DUPLICATE KEY UPDATE descricao_solucao = descricao_solucao",
                        (desc, passos))
                    id_solucao = self._valor(
                        "SELECT id_solucao FROM solucoes WHERE descricao_solucao = %s",
                        (desc,))
                    self._executar(
                        "INSERT INTO defeitos (id_sintoma, id_solucao, ordem) "
                        "VALUES (%s, %s, %s)", (id_sintoma, id_solucao, ordem))

    # ---------------------------------------------------------------- usuários
    def criar_usuario(self, nome, senha, tipo="cliente"):
        try:
            return self._executar(
                "INSERT INTO usuarios (nome, senha, tipo) VALUES (%s, %s, %s)",
                (nome.strip(), _hash_senha(senha), tipo))
        except mysql.connector.IntegrityError:
            raise ValueError("nome já cadastrado")

    def autenticar(self, nome, senha):
        u = self._um("SELECT * FROM usuarios WHERE nome = %s", (nome.strip(),))
        if u is None or not _confere_senha(senha, u["senha"]):
            return None
        if not u["senha"].startswith("pbkdf2$"):  # atualiza hash antigo para o formato novo
            self._executar("UPDATE usuarios SET senha = %s WHERE id_usuario = %s",
                           (_hash_senha(senha), u["id_usuario"]))
        return u

    def obter_usuario(self, id_usuario):
        return self._um("SELECT * FROM usuarios WHERE id_usuario = %s", (id_usuario,))

    def atualizar_usuario(self, id_usuario, nome, telefone, endereco, email):
        try:
            self._executar(
                "UPDATE usuarios SET nome = %s, telefone = %s, endereco = %s, email = %s "
                "WHERE id_usuario = %s",
                (nome.strip(), telefone, endereco, email, id_usuario))
        except mysql.connector.IntegrityError:
            raise ValueError("nome já cadastrado")

    # ---------------------------------------------------------------- produtos
    def listar_produtos(self, id_usuario):
        return self._consultar(
            "SELECT * FROM produtos WHERE id_usuario = %s ORDER BY id_produto DESC",
            (id_usuario,))

    def criar_produto(self, id_usuario, tipo, marca, modelo, sistema_operacional="",
                      numero_serie="", observacoes=""):
        return self._executar(
            "INSERT INTO produtos (id_usuario, tipo, marca, modelo, sistema_operacional, "
            "numero_serie, observacoes) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (id_usuario, tipo, marca, modelo, sistema_operacional, numero_serie,
             observacoes))

    def excluir_produto(self, id_produto, id_usuario):
        self._executar("DELETE FROM produtos WHERE id_produto = %s AND id_usuario = %s",
                       (id_produto, id_usuario))

    # ---------------------------------------------------------------- sintomas / soluções
    def listar_sintomas(self):
        return self._consultar(
            "SELECT id_sintoma, descricao_sintoma FROM sintomas ORDER BY id_sintoma")

    def diagnostico(self, id_sintoma):
        """Causas e soluções (com passo a passo) de um sintoma."""
        s = self._um("SELECT * FROM sintomas WHERE id_sintoma = %s", (id_sintoma,))
        causas = [r["descricao_causa"] for r in self._consultar(
            "SELECT descricao_causa FROM causas WHERE id_sintoma = %s ORDER BY id_causa",
            (id_sintoma,))]
        solucoes = [
            {"id_solucao": r["id_solucao"], "descricao": r["descricao_solucao"],
             "passos": r["passo_a_passo"]}
            for r in self._consultar(
                "SELECT so.id_solucao, so.descricao_solucao, so.passo_a_passo "
                "FROM defeitos d JOIN solucoes so ON so.id_solucao = d.id_solucao "
                "WHERE d.id_sintoma = %s ORDER BY d.ordem", (id_sintoma,))]
        return {"id_sintoma": id_sintoma, "descricao": s["descricao_sintoma"],
                "causas": causas, "solucoes": solucoes}

    # ---------------------------------------------------------------- chamados
    def criar_chamado(self, id_cliente, id_sintoma, id_produto=None, outro_sintoma="",
                      descricao_problema=""):
        return self._executar(
            "INSERT INTO chamados (id_cliente, id_produto, id_sintoma, outro_sintoma, "
            "descricao_problema) VALUES (%s, %s, %s, %s, %s)",
            (id_cliente, id_produto, id_sintoma, outro_sintoma, descricao_problema))

    def atualizar_situacao(self, id_chamado, situacao):
        if situacao not in SITUACOES:
            raise ValueError("situação inválida")
        fechamento = "NOW()" if situacao in ("Resolvido", "Cancelado") else "NULL"
        self._executar(
            f"UPDATE chamados SET situacao_chamado = %s, data_fechamento = {fechamento} "
            "WHERE id_chamado = %s", (situacao, id_chamado))

    def listar_chamados(self, id_cliente):
        return self._consultar(
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
             WHERE c.id_cliente = %s
             ORDER BY c.id_chamado DESC
            """, (id_cliente,))

    def listar_todos_chamados(self, situacao=None):
        """Para o painel do técnico: chamados de todos os clientes (abertos primeiro)."""
        return self._consultar(
            """
            SELECT c.id_chamado, c.situacao_chamado, c.data_abertura, c.outro_sintoma,
                   c.descricao_problema, s.descricao_sintoma, p.marca, p.modelo,
                   u.nome AS nome_cliente, u.telefone
              FROM chamados c
              JOIN usuarios u ON u.id_usuario = c.id_cliente
              JOIN sintomas s ON s.id_sintoma = c.id_sintoma
              LEFT JOIN produtos p ON p.id_produto = c.id_produto
             WHERE (%s IS NULL OR c.situacao_chamado = %s)
             ORDER BY CASE WHEN c.situacao_chamado IN ('Resolvido', 'Cancelado') THEN 1 ELSE 0 END,
                      c.id_chamado DESC
            """, (situacao, situacao))

    # ---------------------------------------------------------------- dados do painel (gráficos)
    def dados_painel(self, id_cliente=None):
        """Linhas cruas para a Visão geral. Sem id_cliente = todos os clientes (técnico);
        com id_cliente = só os dados desse cliente. As contas ficam no painel.py."""
        filtro_c = "WHERE c.id_cliente = %s" if id_cliente is not None else ""
        filtro_p = "WHERE g.id_usuario = %s" if id_cliente is not None else ""
        params = (id_cliente,) if id_cliente is not None else ()
        chamados = self._consultar(
            f"""
            SELECT c.id_chamado, c.id_cliente, c.situacao_chamado, c.data_abertura,
                   c.data_fechamento, c.outro_sintoma, s.descricao_sintoma,
                   p.tipo AS tipo_equipamento, u.nome AS nome_cliente,
                   (SELECT SUM(g.preco_pago) FROM pagamentos g
                     WHERE g.id_chamado = c.id_chamado) AS total_pago
              FROM chamados c
              JOIN usuarios u ON u.id_usuario = c.id_cliente
              JOIN sintomas s ON s.id_sintoma = c.id_sintoma
              LEFT JOIN produtos p ON p.id_produto = c.id_produto
              {filtro_c}
            """, params)
        pagamentos = self._consultar(
            f"""
            SELECT g.id_pagamento, g.id_usuario, g.id_chamado, g.preco_pago, g.desconto,
                   g.recorrencia, g.tipo_pagamento, g.data_pagamento, u.nome AS nome_cliente
              FROM pagamentos g
              JOIN usuarios u ON u.id_usuario = g.id_usuario
              {filtro_p}
            """, params)
        usuarios = None
        if id_cliente is None:
            usuarios = self._consultar("SELECT id_usuario, nome, tipo, criado_em FROM usuarios")
        return {"chamados": chamados, "pagamentos": pagamentos, "usuarios": usuarios}

    # ---------------------------------------------------------------- pagamentos
    def registrar_pagamento(self, id_usuario, preco_pago, tipo_pagamento, id_chamado=None,
                            desconto=0.0, recorrencia="Única", periodo_pagamento=""):
        return self._executar(
            "INSERT INTO pagamentos (id_usuario, id_chamado, preco_pago, desconto, "
            "recorrencia, periodo_pagamento, tipo_pagamento) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (id_usuario, id_chamado, preco_pago, desconto, recorrencia,
             periodo_pagamento, tipo_pagamento))

    def total_pago(self, id_usuario):
        return self._valor(
            "SELECT COALESCE(SUM(preco_pago), 0) FROM pagamentos WHERE id_usuario = %s",
            (id_usuario,)) or 0.0

    # ---------------------------------------------------------------- migração do JSON antigo
    def _migrar_json_antigo(self):
        """Se existir o dados_evolink.json da versão anterior e o banco estiver vazio,
        importa usuários e chamados e renomeia o JSON para .migrado."""
        if not os.path.exists(CAMINHO_JSON_ANTIGO):
            return
        if self._valor("SELECT COUNT(*) FROM usuarios"):
            return
        try:
            with open(CAMINHO_JSON_ANTIGO, "r", encoding="utf-8") as f:
                antigo = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        sintomas = {r["descricao_sintoma"]: r["id_sintoma"] for r in self.listar_sintomas()}
        ids = {}
        with self._transacao():
            for chave, reg in antigo.get("usuarios", {}).items():
                perfil = reg.get("perfil", {})
                ids[chave] = self._executar(
                    "INSERT INTO usuarios (nome, telefone, endereco, email, senha) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (perfil.get("nome") or chave, perfil.get("telefone", ""),
                     perfil.get("endereco", ""), perfil.get("email", ""),
                     f"sha256${reg['salt']}${reg['hash']}"))
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
                id_chamado = self._executar(
                    "INSERT INTO chamados (id_cliente, id_sintoma, outro_sintoma, "
                    "descricao_problema, data_abertura) VALUES (%s, %s, %s, %s, %s)",
                    (id_usuario, id_sintoma, outro, c.get("informacoes", ""),
                     dt.strftime("%Y-%m-%d %H:%M:%S")))
                if c.get("pago"):
                    forma = c.get("forma") if c.get("forma") in TIPOS_PAGAMENTO else "Dinheiro"
                    self._executar(
                        "INSERT INTO pagamentos (id_usuario, id_chamado, preco_pago, "
                        "periodo_pagamento, tipo_pagamento, data_pagamento) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (id_usuario, id_chamado, float(c.get("valor", 0)),
                         dt.strftime("%m/%Y"), forma, dt.strftime("%Y-%m-%d %H:%M:%S")))
        try:
            os.replace(CAMINHO_JSON_ANTIGO, CAMINHO_JSON_ANTIGO + ".migrado")
        except OSError:
            pass


if __name__ == "__main__":
    try:
        b = Banco()
    except ErroBanco as erro:
        print(erro)
        raise SystemExit(1)
    print(f"Conectado ao MySQL em {CONFIG_MYSQL['host']}:{CONFIG_MYSQL['port']}, "
          f"banco \"{NOME_BANCO}\"\n")
    for tabela in ["usuarios", "produtos", "chamados", "sintomas", "solucoes",
                   "causas", "defeitos", "pagamentos"]:
        n = b._valor(f"SELECT COUNT(*) FROM {tabela}")
        print(f"  {tabela:<11} {n:>3} registro(s)")
    b.fechar()