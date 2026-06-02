# Polymarket/Kalshi Arbitrage Scanner

Projeto em Python/FastAPI para revisar, estabilizar e evoluir um sistema de arbitragem entre Polymarket e Kalshi. Esta base entrega um scanner em modo seguro: coleta mercados, cruza possíveis pares equivalentes, calcula oportunidades YES/NO entre venues e exibe sinais em um dashboard local.

## O que ja vem pronto

- Cliente Polymarket para Gamma API e, opcionalmente, CLOB orderbook publico.
- Cliente Kalshi para listagem publica de mercados abertos.
- Matcher automatico por titulo, numeros e data de fechamento.
- Mapeamento manual em `config/manual_pairs.yaml` para pares revisados.
- Motor de arbitragem com porcentagem bruta, taxas configuraveis, tamanho maximo e lucro estimado.
- Calculadora por sinal com odd decimal, stake total, divisao YES/NO, contratos, lucro e porcentagem.
- Dashboard FastAPI em `http://127.0.0.1:8011`.
- Login local e pagina `/admin` para criar usuarios e ativar/desativar acessos.
- Tema escuro para a experiencia principal do dashboard.
- Scanner paginado para todos os mercados abertos das duas venues quando `polymarket_limit` e `kalshi_limit` estao em `0`.
- Controle configuravel de concorrencia, conexoes HTTP e retry/backoff para respeitar rate limits.
- Testes unitarios para matcher e calculo de arbitragem.
- Modo `simulation` para demonstracao sem depender de credenciais.

## Como rodar

```powershell
cd "C:\Users\Pichau\Documents\New project\polymarket-kalshi-arbitrage"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\run.ps1
```

Depois abra `http://127.0.0.1:8011`.

Login inicial de demo:

```text
usuario: admin
senha: admin123
```

Antes de publicar, altere `ARBITRAGE_ADMIN_USER`, `ARBITRAGE_ADMIN_PASSWORD` e `ARBITRAGE_SESSION_SECRET` no ambiente.

## Deploy no Render Free

O projeto inclui `render.yaml` para criar um Web Service no Render.

1. Suba este projeto para um repositório GitHub/GitLab/Bitbucket.
2. No Render, escolha **New > Blueprint** ou **New > Web Service** e conecte o repositório.
3. Se usar Blueprint, o Render lerá `render.yaml`.
4. Informe as variáveis solicitadas:

```text
ARBITRAGE_ADMIN_USER=seu_usuario_admin
ARBITRAGE_ADMIN_PASSWORD=sua_senha_admin
ARBITRAGE_SEED_USERS=[{"username":"tester1","password":"tester123","role":"viewer"}]
```

`ARBITRAGE_SEED_USERS` é opcional, mas é útil no plano grátis porque recria usuários de teste quando o serviço reinicia. Use `role` como `viewer` para testadores e `admin` apenas para quem pode gerenciar usuários.

O comando de start no Render é:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Para usar dados publicos reais, altere `config/settings.yaml`:

```yaml
scanner:
  data_mode: "live"
  polymarket_limit: 0
  kalshi_limit: 0
  max_concurrent_requests: 8
  retry_attempts: 2
  retry_backoff_seconds: 0.5
```

## Como funciona o sinal

Para o mesmo evento binario, o scanner testa duas direcoes:

- comprar YES na Polymarket + comprar NO na Kalshi;
- comprar YES na Kalshi + comprar NO na Polymarket.

Ha sinal quando:

```text
YES_ask + NO_ask + taxas < 1.00
```

Na tela, isso aparece em linguagem simples:

```text
AQUI A ARBITRAGEM ACONTECE QUANDO O CUSTO DO SIM + NAO FICA ABAIXO DE $1.00.
EXEMPLO: SIM $0.49 + NAO $0.47 = $0.96. VOCE PAGA $0.96 PARA RECEBER $1.00 NO FINAL.
```

O lucro estimado e:

```text
(1.00 - custo_total) * tamanho
```

## Pontos que precisam de revisao humana

- Mercados parecidos podem ter regras de resolucao diferentes.
- Pares com baixa confianca aparecem com aviso e nao devem ser executados automaticamente.
- Taxas, slippage, limites, KYC, geoblocking, latencia e regras de cada venue precisam ser confirmados na conta real.
- Execucao de ordens esta propositalmente fora do fluxo automatico desta primeira versao.

## Proximas melhorias

- Integrar WebSocket para reduzir atraso em vez de depender de polling.
- Adicionar executor dry-run com fila de ordens e simulacao de fill parcial.
- Conectar autenticacao Kalshi para orderbooks privados/assinados quando necessario.
- Conectar SDK oficial Polymarket para criacao/cancelamento de ordens.
- Criar painel de auditoria com historico de sinais e falsos positivos.

## Referencias usadas

- Polymarket API: https://docs.polymarket.com/api-reference
- Polymarket orderbook: https://docs.polymarket.com/trading/orderbook
- Kalshi API: https://docs.kalshi.com/
- Kalshi markets: https://docs.kalshi.com/api-reference/market/get-markets
- Repositorio de referencia enviado: https://github.com/ImMike/polymarket-arbitrage
- API unificada citada: https://github.com/gtg7784/dr-manhattan-ts
