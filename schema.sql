-- Database schema per l'app di gestione ferie

-- Tabella utenti
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabella movimenti (utilizzo, maturazioni, rettifiche, ecc.)
CREATE TABLE movimenti (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    tipo_permesso VARCHAR(50) NOT NULL,
    tipo_movimento VARCHAR(50) NOT NULL,
    ore DECIMAL(5,2) NOT NULL,
    data_movimento DATE NOT NULL,
    anno_maturazione INTEGER,
    note TEXT,
    cancellato BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabella configurazioni (valori di maturazione personalizzati per utente)
CREATE TABLE configurazioni (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    chiave VARCHAR(100) NOT NULL,
    valore VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indici per performance
CREATE INDEX idx_movimenti_user_id ON movimenti(user_id);
CREATE INDEX idx_movimenti_data ON movimenti(data_movimento);
CREATE INDEX idx_movimenti_tipo_permesso ON movimenti(tipo_permesso);
CREATE INDEX idx_movimenti_cancellato ON movimenti(cancellato);
CREATE INDEX idx_configurazioni_user_id ON configurazioni(user_id);
CREATE INDEX idx_configurazioni_chiave ON configurazioni(chiave);

-- Constraint per evitare duplicati nelle configurazioni
CREATE UNIQUE INDEX idx_configurazioni_user_chiave ON configurazioni(user_id, chiave);

-- Constraint per validare i tipi di movimento
ALTER TABLE movimenti ADD CONSTRAINT check_tipo_movimento 
CHECK (tipo_movimento IN ('MATURAZIONE', 'UTILIZZO', 'RETRIBUZIONE', 'RETTIFICA_POSITIVA', 'RETTIFICA_NEGATIVA', 'SALDO_INIZIALE'));

-- Constraint per validare che le ore siano positive
ALTER TABLE movimenti ADD CONSTRAINT check_ore_positive 
CHECK (ore > 0);
