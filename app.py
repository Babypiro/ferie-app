from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import csv
import io
import calendar

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')

# Configurazione Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Configurazione Database
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_database():
    """Inizializza il database creando le tabelle se non esistono"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Controlla se la tabella users esiste
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'users'
            );
        """)
        
        tables_exist = cur.fetchone()['exists']
        
        if not tables_exist:
            print("🔧 Inizializzazione database in corso...")
            
            # Crea le tabelle
            cur.execute("""
                -- Tabella utenti
                CREATE TABLE users (
                    id SERIAL PRIMARY KEY,
                    nome VARCHAR(100) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );

                -- Tabella movimenti
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

                -- Tabella configurazioni
                CREATE TABLE configurazioni (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    chiave VARCHAR(100) NOT NULL,
                    valore VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );

                -- Indici
                CREATE INDEX idx_movimenti_user_id ON movimenti(user_id);
                CREATE INDEX idx_movimenti_data ON movimenti(data_movimento);
                CREATE INDEX idx_movimenti_tipo_permesso ON movimenti(tipo_permesso);
                CREATE INDEX idx_movimenti_cancellato ON movimenti(cancellato);
                CREATE INDEX idx_configurazioni_user_id ON configurazioni(user_id);
                CREATE INDEX idx_configurazioni_chiave ON configurazioni(chiave);
                CREATE UNIQUE INDEX idx_configurazioni_user_chiave ON configurazioni(user_id, chiave);

                -- Constraint
                ALTER TABLE movimenti ADD CONSTRAINT check_tipo_movimento 
                CHECK (tipo_movimento IN ('MATURAZIONE', 'UTILIZZO', 'RETRIBUZIONE', 'RETTIFICA_POSITIVA', 'RETTIFICA_NEGATIVA', 'SALDO_INIZIALE'));

                ALTER TABLE movimenti ADD CONSTRAINT check_ore_positive 
                CHECK (ore > 0);
            """)
            
            conn.commit()
            print("✅ Database inizializzato con successo!")
        else:
            print("✅ Database già inizializzato")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Errore inizializzazione database: {e}")

class User(UserMixin):
    def __init__(self, id, email, nome, password_hash):
        self.id = id
        self.email = email
        self.nome = nome
        self.password_hash = password_hash

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_data = cur.fetchone()
    cur.close()
    conn.close()
    
    if user_data:
        return User(user_data['id'], user_data['email'], user_data['nome'], user_data['password'])
    return None

def ore_a_giorni(ore):
    """Converte ore in giorni (8 ore = 1 giorno)"""
    if ore is None:
        return 0
    return round(ore / 8, 2)

def get_configurazione(chiave, default_value=0):
    """Ottiene una configurazione per l'utente corrente"""
    if not current_user.is_authenticated:
        return default_value
        
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT valore FROM configurazioni WHERE user_id = %s AND chiave = %s",
        (current_user.id, chiave)
    )
    result = cur.fetchone()
    cur.close()
    conn.close()
    
    return float(result['valore']) if result else default_value

def set_configurazione(chiave, valore):
    """Imposta una configurazione per l'utente corrente"""
    if not current_user.is_authenticated:
        return
        
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Verifica se esiste già
    cur.execute(
        "SELECT id FROM configurazioni WHERE user_id = %s AND chiave = %s",
        (current_user.id, chiave)
    )
    
    if cur.fetchone():
        # Aggiorna
        cur.execute(
            "UPDATE configurazioni SET valore = %s, updated_at = NOW() WHERE user_id = %s AND chiave = %s",
            (valore, current_user.id, chiave)
        )
    else:
        # Inserisci
        cur.execute(
            "INSERT INTO configurazioni (user_id, chiave, valore) VALUES (%s, %s, %s)",
            (current_user.id, chiave, valore)
        )
    
    conn.commit()
    cur.close()
    conn.close()

# Route principali
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user_data = cur.fetchone()
        cur.close()
        conn.close()
        
        if user_data and check_password_hash(user_data['password'], password):
            user = User(user_data['id'], user_data['email'], user_data['nome'], user_data['password'])
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Email o password non corretti', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        password = request.form['password']
        
        # Verifica se l'email esiste già
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        
        if cur.fetchone():
            flash('Email già registrata', 'error')
        else:
            # Crea nuovo utente
            password_hash = generate_password_hash(password)
            cur.execute(
                "INSERT INTO users (nome, email, password) VALUES (%s, %s, %s)",
                (nome, email, password_hash)
            )
            conn.commit()
            flash('Registrazione completata! Ora puoi fare il login.', 'success')
            cur.close()
            conn.close()
            return redirect(url_for('login'))
        
        cur.close()
        conn.close()
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Calcola i saldi per tipo di permesso
    conn = get_db_connection()
    cur = conn.cursor()
    
    current_year = datetime.now().year
    
    # Query per ottenere i saldi per tipo
    cur.execute("""
        SELECT 
            tipo_permesso,
            SUM(CASE WHEN tipo_movimento IN ('MATURAZIONE', 'RETTIFICA_POSITIVA', 'SALDO_INIZIALE') THEN ore
                     WHEN tipo_movimento IN ('UTILIZZO', 'RETRIBUZIONE', 'RETTIFICA_NEGATIVA') THEN -ore
                     ELSE 0 END) as saldo_ore
        FROM movimenti 
        WHERE user_id = %s 
        AND cancellato = false 
        AND (anno_maturazione = %s OR anno_maturazione IS NULL)
        GROUP BY tipo_permesso
    """, (current_user.id, current_year))
    
    saldi = cur.fetchall()
    cur.close()
    conn.close()
    
    # Trasforma in dizionario per facilità di uso nel template
    saldi_dict = {}
    for saldo in saldi:
        saldi_dict[saldo['tipo_permesso']] = {
            'ore': saldo['saldo_ore'] or 0,
            'giorni': ore_a_giorni(saldo['saldo_ore'] or 0)
        }
    
    # Assicura che ci siano i tipi principali anche se saldo = 0
    for tipo in ['FERIE', 'ROL', 'EX FEST']:
        if tipo not in saldi_dict:
            saldi_dict[tipo] = {'ore': 0, 'giorni': 0}
    
    return render_template('dashboard.html', saldi=saldi_dict, current_year=current_year, ore_a_giorni=ore_a_giorni)

@app.route('/inserisci')
@login_required
def inserisci():
    return render_template('inserisci.html')

@app.route('/api/inserisci_permessi', methods=['POST'])
@login_required
def inserisci_permessi():
    try:
        data = request.get_json()
        permessi = data.get('permessi', [])
        
        if not permessi:
            return jsonify({'success': False, 'message': 'Nessun permesso da inserire'})
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        for permesso in permessi:
            cur.execute("""
                INSERT INTO movimenti (user_id, tipo_permesso, tipo_movimento, ore, data_movimento, note, anno_maturazione)
                VALUES (%s, %s, 'UTILIZZO', %s, %s, %s, %s)
            """, (
                current_user.id,
                permesso['tipo'],
                permesso['ore'],
                permesso['data'],
                permesso.get('note', ''),
                datetime.strptime(permesso['data'], '%Y-%m-%d').year
            ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': f'Inseriti {len(permessi)} permessi con successo!'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Errore durante l\'inserimento: {str(e)}'})

@app.route('/storico')
@login_required
def storico():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT * FROM movimenti 
        WHERE user_id = %s AND cancellato = false 
        ORDER BY data_movimento DESC, id DESC
    """, (current_user.id,))
    
    movimenti = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template('storico.html', movimenti=movimenti, ore_a_giorni=ore_a_giorni)

@app.route('/api/cancella_movimento/<int:movimento_id>', methods=['POST'])
@login_required
def cancella_movimento(movimento_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica che il movimento appartenga all'utente corrente
        cur.execute("SELECT id FROM movimenti WHERE id = %s AND user_id = %s", 
                   (movimento_id, current_user.id))
        
        if not cur.fetchone():
            return jsonify({'success': False, 'message': 'Movimento non trovato'})
        
        # Soft delete
        cur.execute("UPDATE movimenti SET cancellato = true WHERE id = %s", (movimento_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Movimento eliminato con successo'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Errore: {str(e)}'})

@app.route('/maturazioni', methods=['GET', 'POST'])
@login_required
def maturazioni():
    if request.method == 'POST':
        mese = int(request.form['mese'])
        anno = int(request.form['anno'])
        
        # Ottieni i valori di maturazione configurati
        maturazione_ferie = get_configurazione('maturazione_ferie', 14)
        maturazione_rol = get_configurazione('maturazione_rol', 4)
        maturazione_ex_fest = get_configurazione('maturazione_ex_fest', 8)
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Data del primo giorno del mese
            data_maturazione = datetime(anno, mese, 1)
            
            # Inserisci le maturazioni
            maturazioni_data = [
                ('FERIE', maturazione_ferie),
                ('ROL', maturazione_rol),
                ('EX FEST', maturazione_ex_fest)
            ]
            
            for tipo, ore in maturazioni_data:
                cur.execute("""
                    INSERT INTO movimenti (user_id, tipo_permesso, tipo_movimento, ore, data_movimento, anno_maturazione)
                    VALUES (%s, %s, 'MATURAZIONE', %s, %s, %s)
                """, (current_user.id, tipo, ore, data_maturazione, anno))
            
            conn.commit()
            cur.close()
            conn.close()
            
            flash(f'Maturazione per {calendar.month_name[mese]} {anno} aggiunta con successo!', 'success')
            
        except Exception as e:
            flash(f'Errore durante l\'inserimento: {str(e)}', 'error')
        
        return redirect(url_for('maturazioni'))
    
    # GET request - mostra la pagina
    maturazione_ferie = get_configurazione('maturazione_ferie', 14)
    maturazione_rol = get_configurazione('maturazione_rol', 4)
    maturazione_ex_fest = get_configurazione('maturazione_ex_fest', 8)
    current_year = datetime.now().year
    
    return render_template('maturazioni.html', 
                         maturazione_ferie=maturazione_ferie,
                         maturazione_rol=maturazione_rol,
                         maturazione_ex_fest=maturazione_ex_fest,
                         current_year=current_year,
                         ore_a_giorni=ore_a_giorni)

@app.route('/configurazioni', methods=['GET', 'POST'])
@login_required
def configurazioni():
    if request.method == 'POST':
        try:
            # Salva le nuove configurazioni
            maturazione_ferie = float(request.form['maturazione_ferie'])
            maturazione_rol = float(request.form['maturazione_rol'])
            maturazione_ex_fest = float(request.form['maturazione_ex_fest'])
            
            set_configurazione('maturazione_ferie', maturazione_ferie)
            set_configurazione('maturazione_rol', maturazione_rol)
            set_configurazione('maturazione_ex_fest', maturazione_ex_fest)
            
            flash('Configurazioni salvate con successo!', 'success')
            
        except Exception as e:
            flash(f'Errore durante il salvataggio: {str(e)}', 'error')
        
        return redirect(url_for('configurazioni'))
    
    # GET request - mostra la pagina
    maturazione_ferie = get_configurazione('maturazione_ferie', 14)
    maturazione_rol = get_configurazione('maturazione_rol', 4)
    maturazione_ex_fest = get_configurazione('maturazione_ex_fest', 8)
    
    # Valori di default
    default_ferie = 14
    default_rol = 4
    default_ex_fest = 8
    
    return render_template('configurazioni.html',
                         maturazione_ferie=maturazione_ferie,
                         maturazione_rol=maturazione_rol,
                         maturazione_ex_fest=maturazione_ex_fest,
                         default_ferie=default_ferie,
                         default_rol=default_rol,
                         default_ex_fest=default_ex_fest,
                         ore_a_giorni=ore_a_giorni)

@app.context_processor
def inject_functions():
    return {'ore_a_giorni': ore_a_giorni}

# Inizializza il database all'avvio
with app.app_context():
    if DATABASE_URL:
        init_database()

if __name__ == '__main__':
    app.run(debug=True)
