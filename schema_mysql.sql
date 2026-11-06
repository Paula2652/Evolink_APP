-- EvoLink: estrutura do banco para MySQL (gerada a partir do banco.py)
-- Para usar no MySQL Workbench: abra este arquivo e clique no raio (Execute All).
-- O app também cria tudo isso sozinho na primeira execução, então rodar este arquivo é opcional.
-- Os sintomas, causas e soluções iniciais são inseridos pelo app na primeira execução.

CREATE DATABASE IF NOT EXISTS evolink CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE evolink;

CREATE TABLE IF NOT EXISTS usuarios (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS produtos (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sintomas (
    id_sintoma         INT NOT NULL AUTO_INCREMENT,
    descricao_sintoma  VARCHAR(255) NOT NULL,
    PRIMARY KEY (id_sintoma),
    UNIQUE KEY uq_sintomas_descricao (descricao_sintoma)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS solucoes (
    id_solucao         INT NOT NULL AUTO_INCREMENT,
    descricao_solucao  VARCHAR(255) NOT NULL,
    passo_a_passo      TEXT NOT NULL COMMENT 'um passo por linha',
    PRIMARY KEY (id_solucao),
    UNIQUE KEY uq_solucoes_descricao (descricao_solucao)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS causas (
    id_causa         INT NOT NULL AUTO_INCREMENT,
    id_sintoma       INT NOT NULL,
    descricao_causa  VARCHAR(255) NOT NULL,
    PRIMARY KEY (id_causa),
    UNIQUE KEY uq_causas (id_sintoma, descricao_causa),
    CONSTRAINT fk_causas_sintoma FOREIGN KEY (id_sintoma)
        REFERENCES sintomas (id_sintoma) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS defeitos (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chamados (
    id_chamado          INT NOT NULL AUTO_INCREMENT,
    id_cliente          INT NOT NULL,
    id_produto          INT NULL,
    id_sintoma          INT NOT NULL,
    situacao_chamado    ENUM('Aberto', 'Em andamento', 'Aguardando peça', 'Resolvido', 'Cancelado') NOT NULL DEFAULT 'Aberto',
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pagamentos (
    id_pagamento       INT NOT NULL AUTO_INCREMENT,
    id_usuario         INT NOT NULL,
    id_chamado         INT NULL COMMENT 'vazio = plano/mensalidade',
    preco_pago         DECIMAL(10,2) NOT NULL COMMENT 'valor final, já com desconto',
    desconto           DECIMAL(10,2) NOT NULL DEFAULT 0,
    recorrencia        ENUM('Única', 'Mensal', 'Trimestral', 'Semestral', 'Anual') NOT NULL DEFAULT 'Única',
    periodo_pagamento  VARCHAR(20) NOT NULL DEFAULT '' COMMENT 'ex.: 10/2026',
    tipo_pagamento     ENUM('Pix', 'Dinheiro', 'Cartão de débito', 'Cartão de crédito') NOT NULL,
    data_pagamento     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_pagamento),
    CONSTRAINT ck_pagamentos_preco CHECK (preco_pago >= 0),
    CONSTRAINT ck_pagamentos_desconto CHECK (desconto >= 0),
    CONSTRAINT fk_pagamentos_usuario FOREIGN KEY (id_usuario)
        REFERENCES usuarios (id_usuario) ON DELETE CASCADE,
    CONSTRAINT fk_pagamentos_chamado FOREIGN KEY (id_chamado)
        REFERENCES chamados (id_chamado) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
