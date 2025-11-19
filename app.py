import os
import json
from datetime import timedelta
from flask import Flask, jsonify, request
from flask_jwt_extended import create_access_token, jwt_required, JWTManager
from passlib.hash import pbkdf2_sha256
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy 

# Inicialização da Aplicação
app = Flask(__name__)
CORS(app) # Habilita CORS para todas as rotas

# ---------------------------------------------
# CONFIGURAÇÃO DE SEGURANÇA E BANCO DE DADOS
# ---------------------------------------------

# Chave Secreta para JWT (Lê da variável de ambiente no Render)
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "SUA_CHAVE_SECRETA_PADRAO")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
jwt = JWTManager(app)

# Configuração do Banco de Dados PostgreSQL
# Lê a DATABASE_URL da variável de ambiente no Render
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False 

# Inicializa o SQLAlchemy
db = SQLAlchemy(app)

# Importa os modelos APÓS a inicialização do 'db'
from models import Cliente, Categoria 

# SIMULAÇÃO DE USUÁRIOS (Senha de teste: '123456')
USUARIO_TESTE = {
    "username": "auditoria",
    "password_hash": "$pbkdf2-sha256$29000$.j/HuJeScu4dY0xJidEaQw$AOydwozsEvwPgCTORrIOzup7Nj7.iLnXvva..N3zUQA"
}

# ---------------------------------------------
# FUNÇÃO DE INICIALIZAÇÃO E MIGRAÇÃO DE DADOS
# ---------------------------------------------

def inicializar_banco_de_dados():
    """Cria as tabelas e popula com dados do JSON se o banco estiver vazio."""
    with app.app_context():
        # 1. Cria as tabelas (se elas já existirem, este comando ignora)
        db.create_all()
        
        # 2. Verifica se o banco já está populado
        if Cliente.query.count() == 0:
            print(">>> Banco de dados vazio. Iniciando carga de dados mestres...")
            
            try:
                # Carrega dados do JSON
                with open('data/dados_mestres.json', 'r', encoding='utf-8') as f:
                    data_clientes = json.load(f)
            except FileNotFoundError:
                print("ERRO: Arquivo data/dados_mestres.json não encontrado. Verifique o caminho.")
                return

            for cliente_data in data_clientes:
                # Cria o Cliente
                novo_cliente = Cliente(
                    nome=cliente_data['nome'],
                    grupo=cliente_data['grupo'],
                    segmento=cliente_data['segmento']
                )
                db.session.add(novo_cliente)
                db.session.flush() # Obtém o ID do cliente

                # Cria as Categorias
                for cat_data in cliente_data['categorias']:
                    nova_categoria = Categoria(
                        cliente_id=novo_cliente.id,
                        nome_categoria=cat_data['nome'], # CORRIGIDO: Usa a chave 'nome' do JSON
                        status_recebimento=cat_data.get('status_recebimento', 'PENDENTE'),
                        detalhes_documentos=cat_data['documentos'] # CORRIGIDO: Usa a chave 'documentos' do JSON
                    )
                    db.session.add(nova_categoria)
            
            # Salva todas as alterações no banco de dados
            db.session.commit()
            print(">>> Carga de dados concluída com sucesso!")
        else:
            print(">>> Tabelas já existem e estão populadas. Pulando a carga inicial.")

# Executa a função na inicialização do servidor
inicializar_banco_de_dados()

# ---------------------------------------------
# ROTAS DA API
# ---------------------------------------------

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if username == USUARIO_TESTE["username"] and \
       pbkdf2_sha256.verify(password, USUARIO_TESTE["password_hash"]):
        
        access_token = create_access_token(identity=username)
        return jsonify(access_token=access_token)
    else:
        return jsonify({"msg": "Nome de usuário ou senha incorretos"}), 401


# ROTA 1: LISTAR TODOS OS CLIENTES (Lendo do Banco de Dados)
@app.route("/api/clientes", methods=["GET"])
@jwt_required()
def clientes():
    # Consulta todos os clientes
    todos_clientes = Cliente.query.all()
    
    lista_clientes = []
    for cliente in todos_clientes:
        # Calcula o total de categorias e as concluídas usando a relação
        total_categorias = cliente.categorias.count()
        concluidas = cliente.categorias.filter_by(status_recebimento='RECEBIDO').count()
        
        lista_clientes.append({
            "id": cliente.id,
            "nome": cliente.nome,
            "grupo": cliente.grupo,
            "segmento": cliente.segmento,
            "total_categorias": total_categorias,
            "concluidas": concluidas
        })
        
    return jsonify(lista_clientes)


# ROTA 2: DETALHES DAS CATEGORIAS DO CLIENTE (Lendo do Banco de Dados)
@app.route("/api/clientes/<int:cliente_id>/categorias", methods=["GET"])
@jwt_required()
def detalhes_cliente(cliente_id):
    cliente = Cliente.query.get(cliente_id)

    if not cliente:
        return jsonify({"erro": "Cliente não encontrado"}), 404

    lista_categorias = []
    # Busca categorias relacionadas ao cliente e ordena
    for categoria in cliente.categorias.order_by(Categoria.nome_categoria).all():
        documentos = categoria.detalhes_documentos # Chama o getter que retorna o objeto Python
        
        # AQUI É ONDE O 'STATUS_BUCKET' É INJETADO (Simulação de auditoria)
        # O modelo inicial não tem status_bucket, então vamos simular que todos são 'Não' por padrão
        documentos_com_status = []
        for doc_nome in documentos:
             # Nesta fase, apenas a lista de nomes de documentos é salva
             # A lógica real para verificar o bucket e definir 'Sim' ou 'Não'
             # não está implementada, então simulamos que todos são 'Sim' se a lista existir.
             status_simulacao = 'Sim' 
             documentos_com_status.append({
                 "nome_documento": doc_nome,
                 "status_bucket": status_simulacao
             })
        # FIM DA SIMULAÇÃO

        lista_categorias.append({
            "nome_categoria": categoria.nome_categoria,
            "status_recebimento": categoria.status_recebimento,
            "total_documentos": len(documentos_com_status),
            "documentos_encontrados": sum(1 for doc in documentos_com_status if doc['status_bucket'] == 'Sim'),
            "detalhes_documentos": documentos_com_status 
        })
        
    return jsonify({
        "cliente_nome": cliente.nome,
        "categorias": lista_categorias
    })


# ROTA 3: CONFIRMAR RECEBIMENTO (Escrevendo no Banco de Dados)
@app.route("/api/categorias/confirmar", methods=["POST"])
@jwt_required()
def confirmar_recebimento():
    data = request.get_json()
    cliente_id = data.get("cliente_id")
    nome_categoria = data.get("nome_categoria")
    status = data.get("status")

    if not all([cliente_id, nome_categoria, status]):
        return jsonify({"erro": "Dados insuficientes."}), 400

    if status not in ['RECEBIDO', 'PENDENTE']:
        return jsonify({"erro": "Status inválido."}), 400
    
    try:
        # 1. Busca a categoria no banco de dados
        categoria = Categoria.query.filter_by(
            cliente_id=cliente_id,
            nome_categoria=nome_categoria
        ).first()

        if not categoria:
            return jsonify({"erro": "Categoria não encontrada para este cliente."}), 404

        # 2. Atualiza o status
        categoria.status_recebimento = status
        
        # 3. Salva a mudança no banco de dados
        db.session.commit()
        
        return jsonify({"mensagem": f"Status de '{nome_categoria}' atualizado para {status}."})
        
    except Exception as e:
        # Desfaz qualquer transação em caso de erro
        db.session.rollback() 
        print(f"Erro ao atualizar status: {e}")
        return jsonify({"erro": "Erro interno ao salvar no banco de dados."}), 500


if __name__ == "__main__":
    app.run(debug=True)