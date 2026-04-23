# Lanchonete Kimara

Site com cardapio online, carrinho, pedidos pelo WhatsApp, area admin e persistencia em SQLite.

## Como rodar

```powershell
python app.py
```

Depois abra:

```text
http://127.0.0.1:8000
```

Painel administrativo:

```text
http://127.0.0.1:8000/admin
```

Credenciais iniciais:

- Usuario: `admin`
- Senha: `1234`

Voce pode trocar em hospedagem usando variaveis de ambiente:

- `ADMIN_USER`
- `ADMIN_PASS`

## O que faz

- Cliente busca produtos, filtra por categoria e monta carrinho.
- Taxa de entrega muda conforme o bairro selecionado.
- Pedido e salvo no SQLite e depois enviado pelo WhatsApp.
- Admin edita produtos, promocao, bairros de entrega e dados da loja.
- Admin acompanha pedidos e altera status.

## Publicar no Render

Configure:

- Build Command: `pip install -r requirements.txt`
- Start Command: `python app.py`
- Environment Variable: `HOST=0.0.0.0`

O Render define `PORT` automaticamente.
