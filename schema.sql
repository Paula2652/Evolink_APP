-- EvoLink: estrutura do banco (gerada a partir do banco.py)
PRAGMA foreign_keys = ON;

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
                        CHECK (situacao_chamado IN ('Aberto', 'Em andamento', 'Aguardando peça', 'Resolvido', 'Cancelado')),
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
                      CHECK (recorrencia IN ('Única', 'Mensal', 'Trimestral', 'Semestral', 'Anual')),
    periodo_pagamento TEXT NOT NULL DEFAULT '',                -- ex.: 10/2026
    tipo_pagamento    TEXT NOT NULL
                      CHECK (tipo_pagamento IN ('Pix', 'Dinheiro', 'Cartão de débito', 'Cartão de crédito')),
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
