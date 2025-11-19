# models.py
import json
from datetime import datetime
from app import db # Importamos a instância do db criada em app.py
from sqlalchemy.orm import relationship, backref

class Cliente(db.Model):
    __tablename__ = 'clientes'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    grupo = db.Column(db.String(50), nullable=False)
    segmento = db.Column(db.String(50), nullable=False)
    
    # Relação com Categorias (lazy='dynamic' para consultas eficientes)
    categorias = db.relationship('Categoria', backref='cliente', lazy='dynamic')

    def __repr__(self):
        return f'<Cliente {self.nome}>'

class Categoria(db.Model):
    __tablename__ = 'categorias'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    nome_categoria = db.Column(db.String(200), nullable=False)
    status_recebimento = db.Column(db.String(10), default='PENDENTE', nullable=False)
    
    # Campo para armazenar os documentos como JSON string/Text
    detalhes_documentos_json = db.Column(db.Text, nullable=True) 

    # Coluna para registrar a última atualização
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Garante que não haja categorias duplicadas para o mesmo cliente
    __table_args__ = (db.UniqueConstraint('cliente_id', 'nome_categoria', name='_cliente_categoria_uc'),)

    def __repr__(self):
        return f'<Categoria {self.nome_categoria} Status: {self.status_recebimento}>'

# FUNÇÕES AUXILIARES PARA MANIPULAÇÃO DE DADOS JSON DENTRO DO MODELO

def get_documentos(self):
    """Obtém os detalhes dos documentos como objeto Python (lista de dicts)."""
    if self.detalhes_documentos_json:
        return json.loads(self.detalhes_documentos_json)
    return []

def set_documentos(self, doc_list):
    """Define os detalhes dos documentos a partir de um objeto Python (lista de dicts)."""
    self.detalhes_documentos_json = json.dumps(doc_list)

# Cria a propriedade 'detalhes_documentos' para que possamos acessá-la como um objeto normal
Categoria.detalhes_documentos = property(get_documentos, set_documentos)