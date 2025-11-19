import os
import json
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS 
from models import db, Cliente, DocumentoChecklist 
from waitress import serve # Servidor robusto para hospedagem em nuvem

# --- CONFIGURAÇÃO INICIAL DO FLASK ---
app = Flask(__name__)
CORS(app) 

# Configuração do SQLite (cria um arquivo 'checklist.db' no projeto)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///checklist.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Caminho para os arquivos mestres
DADOS_MESTRES_PATH = 'data/dados_mestres.json'
ARQUIVOS_SIMULADOS_GCS_PATH = 'data/arquivos_simulados_gcs.json'

# --- FUNÇÕES DE UTILIDADE (SIMULANDO NUVEM) ---

def carregar_dados_mestres():
    """Lê o arquivo JSON com a lista de documentos cobrados (para inicialização)."""
    try:
        with open(DADOS_MESTRES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERRO: Arquivo {DADOS_MESTRES_PATH} não encontrado.")
        return []

def carregar_arquivos_simulados():
    """Lê o arquivo JSON que simula o conteúdo do bucket GCS/S3."""
    try:
        with open(ARQUIVOS_SIMULADOS_GCS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERRO: Arquivo {ARQUIVOS_SIMULADOS_GCS_PATH} não encontrado.")
        return {}

def listar_arquivos_na_pasta_do_cliente(bucket_cliente):
    """
    SIMULAÇÃO DE NUVEM: Retorna a lista de arquivos lendo o JSON de simulação, 
    em vez de ler o disco local.
    """
    arquivos_simulados = carregar_arquivos_simulados()
    # Retorna a lista de arquivos para a chave do bucket_cliente (ou lista vazia se não existir)
    return arquivos_simulados.get(bucket_cliente, [])

# --- ROTA GET: TRAZ A COMPARAÇÃO ---
@app.route('/api/clientes/<int:cliente_id>/comparacao', methods=['GET'])
def get_comparacao_documentos(cliente_id):
    """
    Endpoint que o Frontend chama para exibir o checklist.
    Combina dados do BD (status) e simulação de leitura de bucket (existência do arquivo).
    """
    with app.app_context():
        cliente = Cliente.query.get_or_404(cliente_id)
        documentos_cobrados = DocumentoChecklist.query.filter_by(cliente_id=cliente_id).all()
        
        # Pega a chave de busca (nome do bucket/prefixo) a partir do BD
        bucket_cliente = cliente.nome_pasta_simulada # Usamos o campo existente como bucket_cliente
        arquivos_existentes = listar_arquivos_na_pasta_do_cliente(bucket_cliente)
        
        resultado_comparacao = []
        
        for doc in documentos_cobrados:
            # Lógica de Comparação: verifica se o nome cobrado está em algum arquivo existente
            encontrado = any(doc.nome_cobrado.lower() in arq.lower() for arq in arquivos_existentes)
            
            resultado_comparacao.append({
                'id': doc.id,
                'nome_cobrado': doc.nome_cobrado,
                'status_atual': doc.status,
                'encontrado_na_pasta': 'Sim' if encontrado else 'Não',
            })

        return jsonify({
            'cliente_id': cliente.id,
            'cliente_nome': cliente.nome,
            'comparacao': resultado_comparacao
        })

# --- ROTA POST: RECEBE E SALVA O CHECKLIST ---
@app.route('/api/checklist/confirmar', methods=['POST'])
def confirmar_checklist():
    """
    Recebe os dados do checklist do Frontend e atualiza o status no banco de dados.
    """
    try:
        dados = request.get_json()
        cliente_id = dados.get('cliente_id')
        documentos_atualizados = dados.get('documentos', [])
        
        if not cliente_id or not documentos_atualizados:
            return jsonify({"erro": "Dados incompletos"}), 400

        # Simulação: Pegue o usuário de um sistema de autenticação real
        usuario = "usuario_nuvem" 
        data_atual = datetime.now()

        with app.app_context():
            for item in documentos_atualizados:
                doc_id = item['id'] 
                novo_status = item['status']
                
                doc = DocumentoChecklist.query.get(doc_id)
                
                if doc:
                    doc.status = novo_status
                    
                    if novo_status == 'RECEBIDO':
                        doc.data_confirmacao = data_atual
                        doc.usuario_confirmador = usuario
                    else:
                        doc.data_confirmacao = None
                        doc.usuario_confirmador = None

            db.session.commit()
            
        return jsonify({"mensagem": f"Checklist do cliente {cliente_id} salvo com sucesso."}), 200

    except Exception as e:
        db.session.rollback()
        print(f"Erro ao salvar checklist: {e}")
        return jsonify({"erro": "Erro interno do servidor ao salvar."}), 500

# --- FUNÇÃO DE INSERÇÃO DE DADOS INICIAIS ---
def init_db():
    """Cria tabelas e insere os dados iniciais do dados_mestres.json no BD."""
    dados_mestres = carregar_dados_mestres()
    
    for c_data in dados_mestres:
        # 1. Cria ou pega o Cliente
        cliente = Cliente.query.filter_by(id=c_data['id_cliente']).first()
        if not cliente:
            cliente = Cliente(
                id=c_data['id_cliente'],
                nome=c_data['nome_cliente'],
                # Usamos o campo existente para guardar a chave do bucket
                nome_pasta_simulada=c_data['bucket_cliente']
            )
            db.session.add(cliente)
            db.session.commit()

        # 2. Insere os Documentos
        for doc_nome in c_data['documentos_cobranca']:
            doc = DocumentoChecklist.query.filter_by(
                cliente_id=cliente.id, 
                nome_cobrado=doc_nome
            ).first()
            if not doc:
                novo_doc = DocumentoChecklist(
                    nome_cobrado=doc_nome,
                    cliente_id=cliente.id
                )
                db.session.add(novo_doc)
    
    db.session.commit()
    print("Banco de dados inicializado com sucesso e dados mestres carregados.")


# --- INICIALIZAÇÃO DO SERVIDOR ---
if __name__ == '__main__':
    with app.app_context():
        # Cria as tabelas do BD e carrega os dados mestres
        db.create_all() 
        init_db()
    
    # Define a porta a ser usada pelo Render (ambiente de produção) ou 5000 (local)
    port = int(os.environ.get('PORT', 5000))

    # Para testes locais, use app.run(debug=True)
    # Para implantação (Render/Nuvem), use o Waitress:
    print(f"Servidor rodando em 0.0.0.0:{port}...")
    serve(app, host='0.0.0.0', port=port)
    # Se quiser rodar localmente sem Waitress, comente a linha acima e descomente a abaixo:
    # app.run(debug=True)