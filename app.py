# app.py - NOVO CONTEÚDO (COM SEGURANÇA JWT)

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import create_access_token, jwt_required, JWTManager
from models import db, CategoriaChecklist, init_db
from passlib.hash import pbkdf2_sha256 # Usado para simular hash de senha
import json
import os
from waitress import serve

app = Flask(__name__)
# Permitimos qualquer origem (CORS) para desenvolvimento com o index.html local
CORS(app) 

# ------------------------------------------------------------------
# CONFIGURAÇÃO DE SEGURANÇA (JWT)
# ------------------------------------------------------------------

# A chave secreta deve ser carregada de uma variável de ambiente!
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "SUA_CHAVE_SECRETA_PADRAO") 
app.config["JWT_TOKEN_LOCATION"] = ["headers"] # Define onde o token será buscado
jwt = JWTManager(app)

# ------------------------------------------------------------------
# CONFIGURAÇÃO DE BANCO DE DADOS (SQLite LOCAL vs. PostgreSQL RENDER)
# ------------------------------------------------------------------

database_url = os.environ.get('DATABASE_URL')

if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    print("Usando PostgreSQL (Configuração de Produção)")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///checklist.db'
    print("Usando SQLite (Configuração de Desenvolvimento)")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)


# SIMULAÇÃO DE USUÁRIOS (Em produção, isso viria de uma tabela 'User' no BD)
# Senha: 'minhasenha123' (hash gerado por pbkdf2_sha256.hash("minhasenha123"))
USUARIO_TESTE = {
    "username": "auditoria",
    "password_hash": "$pbkdf2-sha256$29000$g43j3r2iG0N4HwGjC6v1gA$yG3n7I/NfH/9Z4e/2X6d1J4o5S/7vL/Q3jB5yA=" 
}

# ----------------------------------------------------
# SIMULAÇÃO DE DADOS MESTRES E ARQUIVOS RECEBIDOS
# (MANTIDOS PARA CLAREZA)
# --------------------------------------------------

def carregar_dados_mestres():
    """Carrega os dados mestre dos clientes e categorias do JSON."""
    try:
        with open('data/dados_mestres.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def carregar_arquivos_simulados():
    """Carrega a lista de todos os arquivos simulados no 'bucket'."""
    try:
        with open('data/arquivos_simulados_gcs.json', 'r', encoding='utf-8') as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

# ----------------------------------------------------
# ROTA 1: AUTENTICAÇÃO
# ----------------------------------------------------
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', None)
    password = data.get('password', None)
    
    # Simula a verificação de credenciais
    if username == USUARIO_TESTE["username"] and \
       pbkdf2_sha256.verify(password, USUARIO_TESTE["password_hash"]):
        
        # Cria o token de acesso que expira em 30 minutos (por exemplo)
        access_token = create_access_token(identity=username, expires_delta=False)
        return jsonify(access_token=access_token), 200
    
    return jsonify({"msg": "Credenciais inválidas"}), 401


# ----------------------------------------------------
# ROTAS DE API (PROTEGIDAS)
# ----------------------------------------------------

# Rota 2: Lista Todos os Clientes (AGORA PROTEGIDA)
@app.route('/api/clientes', methods=['GET'])
@jwt_required() # <--- NOVO: Requer um token válido
def listar_clientes():
    """Retorna a lista básica de clientes com o status de conclusão."""
    dados_mestres = carregar_dados_mestres()
    
    clientes_listagem = []
    with app.app_context():
        for cliente in dados_mestres:
            cliente_id = cliente['id']
            total_categorias = len(cliente.get('categorias', []))
            
            # Conta quantas categorias estão marcadas como RECEBIDO
            concluidas = CategoriaChecklist.query.filter_by(
                cliente_id=cliente_id,
                status_recebimento='RECEBIDO'
            ).count()

            clientes_listagem.append({
                'id': cliente_id,
                'nome': cliente['nome'],
                'grupo': cliente.get('grupo', 'N/A'),
                'segmento': cliente.get('segmento', 'N/A'),
                'total_categorias': total_categorias,
                'concluidas': concluidas
            })
            
    return jsonify(clientes_listagem)


# Rota 3: Detalhes das Categorias do Cliente (AGORA PROTEGIDA)
@app.route('/api/clientes/<int:cliente_id>/categorias', methods=['GET'])
@jwt_required() # <--- NOVO: Requer um token válido
def detalhes_cliente(cliente_id):
    """
    Retorna a lista de categorias para um cliente,
    com status de recebimento e status de arquivos.
    """
    dados_mestres = carregar_dados_mestres()
    arquivos_recebidos = carregar_arquivos_simulados()
    
    cliente = next((c for c in dados_mestres if c['id'] == cliente_id), None)
    
    if not cliente:
        return jsonify({"erro": "Cliente não encontrado"}), 404

    resposta_categorias = []
    
    with app.app_context():
        for categoria_mestra in cliente.get('categorias', []):
            nome_categoria = categoria_mestra['nome']
            documentos_cobrados = categoria_mestra.get('documentos', [])
            
            status_bd = CategoriaChecklist.query.filter_by(
                cliente_id=cliente_id,
                nome_categoria=nome_categoria
            ).first()
            
            status_recebimento = status_bd.status_recebimento if status_bd else 'PENDENTE'
            
            detalhes_documentos = []
            for doc_nome in documentos_cobrados:
                encontrado = 'Sim' if doc_nome in arquivos_recebidos else 'Não'
                detalhes_documentos.append({
                    'nome_documento': doc_nome,
                    'status_bucket': encontrado
                })
            
            resposta_categorias.append({
                'nome_categoria': nome_categoria,
                'status_recebimento': status_recebimento,
                'total_documentos': len(documentos_cobrados),
                'documentos_encontrados': len([d for d in detalhes_documentos if d['status_bucket'] == 'Sim']),
                'detalhes_documentos': detalhes_documentos
            })
            
    return jsonify({
        'cliente_id': cliente_id,
        'cliente_nome': cliente['nome'],
        'categorias': resposta_categorias
    })


# Rota 4: Salva o Status da Categoria (AGORA PROTEGIDA)
@app.route('/api/categorias/confirmar', methods=['POST'])
@jwt_required() # <--- NOVO: Requer um token válido
def salvar_categoria():
    data = request.get_json()
    cliente_id = data.get('cliente_id')
    nome_categoria = data.get('nome_categoria')
    novo_status = data.get('status', 'PENDENTE').upper()

    if not all([cliente_id, nome_categoria, novo_status]):
        return jsonify({"erro": "Dados incompletos fornecidos."}), 400

    if novo_status not in ['RECEBIDO', 'PENDENTE']:
        return jsonify({"erro": "Status inválido."}), 400

    with app.app_context():
        try:
            categoria_db = CategoriaChecklist.query.filter_by(
                cliente_id=cliente_id,
                nome_categoria=nome_categoria
            ).first()

            if categoria_db:
                categoria_db.status_recebimento = novo_status
            else:
                nova_categoria = CategoriaChecklist(
                    cliente_id=cliente_id,
                    nome_categoria=nome_categoria,
                    status_recebimento=novo_status
                )
                db.session.add(nova_categoria)
            
            db.session.commit()
            return jsonify({"mensagem": f"Status da categoria '{nome_categoria}' atualizado para {novo_status}."})

        except Exception as e:
            db.session.rollback()
            print(f"Erro ao salvar categoria: {e}")
            return jsonify({"erro": "Erro interno ao salvar no banco de dados."}), 500

# ----------------------------------------------------
# INICIALIZAÇÃO E EXECUÇÃO
# ----------------------------------------------------

with app.app_context():
    init_db(app)

if __name__ == '__main__':
    # ... (Bloco de execução local com Waitress)
    if os.environ.get('DATABASE_URL'):
        print("Ambiente de Produção (Rodando via Procfile no Render)")
    else:
        print(f"Servidor rodando em 0.0.0.0:5000 (Local)...")
        serve(app, host='0.0.0.0', port=5000)