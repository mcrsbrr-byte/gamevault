# 🎮 GameVault — Loja de Jogos Digitais

## Conta de Administrador
- **Email:** mcr.sbrr@gmail.com
- **Senha:** Admin@GameVault2024!
- **Painel Admin:** http://localhost:5000/admin

## Como Iniciar

### 1. Instalar Python (3.10+)
### 2. Instalar dependências:
```
pip install flask pillow
```

### 3. Rodar o servidor:
```
python app.py
```

### 4. Acessar no navegador:
```
http://localhost:5000
```

## Configurar Email (notificações)
Edite o arquivo `app.py` e defina:
```python
SMTP_PASS = 'sua_senha_de_app_gmail'
```
Ou crie um arquivo `.env` com: `SMTP_PASS=sua_senha`

Para Gmail, ative **"Senhas de app"** em: https://myaccount.google.com/apppasswords

## Estrutura
```
gamevault/
├── app.py              # Aplicação principal
├── gamevault.db        # Banco de dados (criado automaticamente)
├── static/
│   ├── css/style.css   # Estilos
│   ├── js/main.js      # Scripts
│   └── uploads/        # Imagens e arquivos dos jogos
│       ├── covers/     # Capas dos jogos
│       ├── files/      # Arquivos dos jogos (ISO, ROM...)
│       ├── avatars/    # Fotos de perfil
│       └── banners/    # Banners do slider
└── templates/          # Páginas HTML
```

## Funcionalidades
- ✅ 484 jogos em 7 consoles pré-cadastrados
- ✅ Painel admin completo (adicionar/editar jogos, capas, arquivos)
- ✅ Sistema de compras com carrinho
- ✅ Cupons de desconto (GAMER10, PRIMEIRACOMPRA, PACK5)
- ✅ Pagamento via PIX e Cartão
- ✅ Sistema de pontos/fidelidade
- ✅ Lista de desejos
- ✅ Avaliações com estrelas
- ✅ Notificações no site e por email
- ✅ Newsletter
- ✅ Relatório CSV
- ✅ Tema claro/escuro
- ✅ Slider/carousel na home
- ✅ Jogos gratuitos
- ✅ Pacotes/bundles
- ✅ Filtros por categoria
- ✅ Busca em tempo real
- ✅ Chat Tawk.to (configure o ID no base.html)
- ✅ WhatsApp flutuante
- ✅ Pop-up de boas-vindas
- ✅ Sitemap.xml para SEO
- ✅ Páginas de erro 404/403 personalizadas
- ✅ Rate limiting no login
- ✅ Compressão de imagens automática

## Cupons Pré-configurados
| Código | Desconto |
|--------|----------|
| GAMER10 | 10% em qualquer compra |
| PRIMEIRACOMPRA | 15% (1 uso por código) |
| PACK5 | R$ 5,00 off em compras acima de R$ 20 |

## Adicionar Jogos (Admin)
1. Faça login com mcr.sbrr@gmail.com
2. Acesse /admin
3. Clique em "Novo Jogo"
4. Preencha as informações, faça upload da capa e do arquivo
5. Clique em "Adicionar Jogo"
