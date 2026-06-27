#!/bin/bash
# GameVault — Script de inicialização
echo "🎮 Iniciando GameVault..."
echo ""

# Check Python
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "❌ Python não encontrado. Instale Python 3.10+ em https://python.org"
    exit 1
fi

PY=$(command -v python3 || command -v python)

# Install deps
echo "📦 Verificando dependências..."
$PY -m pip install flask pillow --quiet

# Start
echo ""
echo "✅ Iniciando servidor..."
echo "🌐 Acesse: http://localhost:5000"
echo "🔑 Admin: mcr.sbrr@gmail.com / Admin@GameVault2024!"
echo ""
$PY app.py
