# app.py - NOVO CONTEÚDO

from flask import Flask, request, jsonify
from flask_cors import CORS
from models import db, CategoriaChecklist, init_db
import json
import os
from waitress import serve

app = Flask(__name__)
CORS(app) # Permite que o frontend acesse a API

# ------------------------------------------------------------------
# CONFIGURAÇÃO DE BANCO DE DADOS (SQLite LOCAL vs. PostgreSQL RENDER)
# ------------------------------------------------------------------

# 1. Tenta obter a URL do PostgreSQL das variáveis de ambiente do Render
database_url = os.environ.get('DATABASE_URL')

if database_url:
    # Corrige o prefixo 'postgres' para 'postgresql' se necessário, para compatibilidade com SQLAlchemy 2.x
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    print("Usando PostgreSQL (Configuração de Produção)")
else:
    # Fallback para SQLite local (Configuração de Desenvolvimento)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///checklist.db'
    print("Usando SQLite (Configuração de Desenvolvimento)")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# ----------------------------------------------------
# SIMULAÇÃO DE DADOS MESTRES E ARQUIVOS RECEBIDOS
# ----------------------------------------------------

def carregar_dados_mestres():
    """Carrega os dados mestre dos clientes e categorias do JSON."""
    try:
        # Assumindo que o JSON está na pasta 'data/'
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
# ROTAS DA API
# ----------------------------------------------------

# Rota 1: Lista Todos os Clientes (para a tela inicial)
@app.route('/api/clientes', methods=['GET'])
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

            # Estrutura a resposta como na imagem do painel
            clientes_listagem.append({
                'id': cliente_id,
                'nome': cliente['nome'],
                'grupo': cliente.get('grupo', 'N/A'),
                'segmento': cliente.get('segmento', 'N/A'),
                'total_categorias': total_categorias,
                'concluidas': concluidas
            })
            
    return jsonify(clientes_listagem)


# Rota 2: Detalhes das Categorias do Cliente
@app.route('/api/clientes/<int:cliente_id>/categorias', methods=['GET'])
def detalhes_cliente(cliente_id):
    """
    Retorna a lista de categorias para um cliente,
    com status de recebimento e status de arquivos.
    """
    dados_mestres = carregar_dados_mestres()
    arquivos_recebidos = carregar_arquivos_simulados()
    
    # 1. Encontra o cliente nos dados mestres
    cliente = next((c for c in dados_mestres if c['id'] == cliente_id), None)
    
    if not cliente:
        return jsonify({"erro": "Cliente não encontrado"}), 404

    resposta_categorias = []
    
    with app.app_context():
        for categoria_mestra in cliente.get('categorias', []):
            nome_categoria = categoria_mestra['nome']
            documentos_cobrados = categoria_mestra.get('documentos', [])
            
            # 2. Busca o status de persistência no BD
            status_bd = CategoriaChecklist.query.filter_by(
                cliente_id=cliente_id,
                nome_categoria=nome_categoria
            ).first()
            
            status_recebimento = status_bd.status_recebimento if status_bd else 'PENDENTE'
            
            # 3. Verifica os arquivos (para a coluna de documentos na sub-tabela)
            detalhes_documentos = []
            for doc_nome in documentos_cobrados:
                encontrado = 'Sim' if doc_nome in arquivos_recebidos else 'Não'
                detalhes_documentos.append({
                    'nome_documento': doc_nome,
                    'status_bucket': encontrado
                })
            
            # 4. Estrutura a resposta final para o Frontend
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


# Rota 3: Salva o Status da Categoria
@app.route('/api/categorias/confirmar', methods=['POST'])
def salvar_categoria():
    data = request.get_json()
    cliente_id = data.get('cliente_id')
    nome_categoria = data.get('nome_categoria')
    novo_status = data.get('status', 'PENDENTE').upper() # Deve ser 'RECEBIDO' ou 'PENDENTE'

    if not all([cliente_id, nome_categoria, novo_status]):
        return jsonify({"erro": "Dados incompletos fornecidos."}), 400

    if novo_status not in ['RECEBIDO', 'PENDENTE']:
        return jsonify({"erro": "Status inválido."}), 400

    with app.app_context():
        try:
            # Tenta encontrar a categoria existente no BD
            categoria_db = CategoriaChecklist.query.filter_by(
                cliente_id=cliente_id,
                nome_categoria=nome_categoria
            ).first()

            if categoria_db:
                # Atualiza o status
                categoria_db.status_recebimento = novo_status
            else:
                # Cria uma nova entrada se não existir
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

# Cria as tabelas do BD quando a aplicação for iniciada
with app.app_context():
    init_db(app)

if __name__ == '__main__':
    # Se estiver no Render, a inicialização é feita pelo Procfile com Waitress
    if os.environ.get('DATABASE_URL'):
        # A execução via 'waitress-serve' é feita pelo Procfile/Render, 
        # então este bloco só serve para o teste local.
        print("Ambiente de Produção (Rodando via Procfile no Render)")
    else:
        # Execução local com Waitress para simular o modo de produção
        print(f"Servidor rodando em 0.0.0.0:5000 (Local)...")
        serve(app, host='0.0.0.0', port=5000)