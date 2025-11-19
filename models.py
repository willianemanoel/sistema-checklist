# models.py - NOVO CONTEÚDO

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# ----------------------------------------------------
# Tabela para persistir o STATUS de cada CATEGORIA
# ----------------------------------------------------
class CategoriaChecklist(db.Model):
    __tablename__ = 'categoria_checklist'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Chave para o Cliente (do JSON)
    cliente_id = db.Column(db.Integer, nullable=False)
    
    # Nome da Categoria (do JSON)
    nome_categoria = db.Column(db.String(255), nullable=False)
    
    # Status de Recebimento da Categoria
    status_recebimento = db.Column(db.String(20), default='PENDENTE') # 'PENDENTE' ou 'RECEBIDO'
    
    # Garante que não haja duplicatas de CATEGORIA para o mesmo CLIENTE
    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'nome_categoria', name='uc_cliente_categoria'),
    )

    def __repr__(self):
        return f"<CategoriaChecklist {self.cliente_id} - {self.nome_categoria}: {self.status_recebimento}>"

# Funções de inicialização do banco de dados (serão chamadas pelo app.py)
def init_db(app):
    with app.app_context():
        # Cria as tabelas se não existirem
        db.create_all()