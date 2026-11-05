# Como estudar o CatalogLens

Comece executando `python -m cataloglens demo` e `python -m cataloglens serve` na
pasta do projeto. O programa não precisa de chave de IA para funcionar.

## Primeiro entenda o caminho dos dados

Abra `data/harbor.json` e encontre o preço `74,90`. Depois localize esse produto no
painel e clique em **Inspect**. Ele é armazenado como `7490` centavos. Leia
`price_cents` em `cataloglens/core.py` e acompanhe a transformação.

Exercício: altere o preço para `74,999` numa cópia do arquivo, importe essa cópia e
verifique por que o registro foi rejeitado. Não mude os dados originais nem o
relatório publicado para fabricar um resultado melhor.

## Depois leia as consultas SQL

Em `cataloglens/store.py`, comece por `search`. Os filtros viram parâmetros `?`.
Isso separa o texto recebido dos comandos SQL. Observe também a ordenação por
preço e a seleção do snapshot mais recente.

Exercício: adicione um filtro por loja e um teste que confirme que esse filtro
funciona junto com preço e categoria. Pense no comportamento para uma loja que
não existe e para um nome contendo uma aspa.

## Investigue um erro antes de tentar corrigi-lo

Execute `python -m cataloglens evaluate`. Por que `Paper Notebook` vira `laptops`?
A regra reconhece uma palavra sem compreender o contexto. `Laptop Sleeve` também
não é um laptop. O painel mostra essas falhas, em vez de escondê-las.

Exercício: crie um segundo classificador baseado em regras para acessórios e
compare as duas versões num conjunto novo de exemplos rotulados. Preserve a
versão original para medir a mudança. Não edite os rótulos para combinar com o
que seu código prevê.

## Só então entre na integração de IA

Leia `cataloglens/ai.py`. Há quatro partes: o pedido ao modelo, a estrutura
esperada, a validação local e o salvamento para revisão. O modelo não pode mudar
preços. Uma frase presente na descrição pode apoiar uma sugestão errada; por
isso a existência da citação não substitui revisão e avaliação.

As chamadas reais exigem uma conta Anthropic, chave e modelo configurados, e têm
custo. Não compartilhe sua chave nem a coloque no GitHub. Os testes usam respostas
simuladas para verificar o contrato da integração; isso não mede a qualidade de
um modelo real.

## Antes de apresentar

Explique com suas palavras uma importação, uma consulta, um teste e uma limitação.
Rode o projeto do início numa pasta nova. Diferencie o que já executou localmente
do que ainda precisa experimentar, especialmente a classificação com Claude.
