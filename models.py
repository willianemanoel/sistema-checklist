from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Cliente(db.Model):
    __tablename__ = 'cliente'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)
    # Coluna usada para mapear o cliente ao prefixo do bucket (simulação de nuvem)
    nome_pasta_simulada = db.Column(db.String(120), unique=True, nullable=False)
    documentos = db.relationship('DocumentoChecklist', backref='cliente', lazy=True)

class DocumentoChecklist(db.Model):
    __tablename__ = 'documento_checklist'
    id = db.Column(db.Integer, primary_key=True)
    
    # Ex: '09060-5_AplicAut.xls' - O documento que você cobra
    nome_cobrado = db.Column(db.String(255), nullable=False)
    
    # Chave estrangeira que conecta ao cliente
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    
    # O Status final ('PENDENTE', 'RECEBIDO', 'NAO_APLICA')
    status = db.Column(db.String(50), default='PENDENTE', nullable=False)
    
    data_confirmacao = db.Column(db.DateTime, nullable=True)
    usuario_confirmador = db.Column(db.String(120), nullable=True)

    def to_dict(self):
        # Converte o objeto datetime para string ISO 8601 (formato JSON)
        return {
            'id': self.id,
            'nome_cobrado': self.nome_cobrado,
            'status': self.status,
            'data_confirmacao': self.data_confirmacao.isoformat() if self.data_confirmacao else None
        }