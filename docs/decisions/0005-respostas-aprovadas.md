# 0005. Respostas aprovadas: o modelo escolhe, não escreve

- **Status:** proposta, aprovada pela Nathaly em 2026-11-15 para implementar e medir. Vira "aceita" ou "rejeitada" com o resultado, registrado abaixo.
- **Data:** 2026-11-15

## Contexto
Na linha de base da v2 (2026-11-13; 100 perguntas, 50 com base e 50 sem; `qwen3:4b-instruct`, prompt `answer-v1`, busca híbrida), o atendente acertou a decisão em 80/100, mas **respondeu sem base em 16 de 50** perguntas. Em 11 delas a resposta é perigosa ou inventada: "encerre a conta" para quem acha que alguém entrou nela (P056), "sim, pode comprar ingresso" (P100), regra do Pix MED aplicada a boleto e a cartão (P068, P071). Mediana de 11,7 s por resposta.

O que já foi medido e não resolveu:
- **Prompts `answer-v2` e `answer-v3`** (README, seção Resultados): o v3 resolveu a P010, mas passou a inventar negativas (sem base 1/8 → 3/8 na v1). Mexer no texto do prompt troca um erro por outro.
- **Trava 1 (`MIN_SIMILARITY`)**: as notas dos dois grupos se sobrepõem. Em 0,86, ela barraria 7 dos 16 erros e derrubaria 14 das 46 respostas certas.
- **Rerankers (2026-11-15, sem o LLM, 20 candidatos por pergunta):**

  | | Similaridade (hoje) | `mmarco-mMiniLMv2-L12-H384-v1` | `bge-reranker-v2-m3` |
  |---|---|---|---|
  | Separa com base de sem base (AUC) | 0,709 | 0,702 | 0,761 |
  | Artigo principal entre os 4 primeiros | 44/50 | 40/50 | 47/50 |
  | Tempo extra por pergunta | 0 | 0,8 s | 8,7 s |

  O bge dá nota quase zero às respostas inventadas mais graves, mas também às respostas "não oferecemos" (P009, P016, P025, P029, P084, P085) e à P010: o mesmo ponto cego do LLM. Como trava, barraria 5 erros e derrubaria 11 respostas certas. Não adotado. (O script e o resultado deste experimento ainda não estão no repositório: entram num PR próprio, para os números serem reproduzíveis.)

**O que a Nathaly pediu para o produto:** responder o máximo possível; aceitar mensagens com várias perguntas; responder cada parte com a fonte; para a parte que as políticas não cobrem, dizer que não sabe e **oferecer** um atendente, sem encaminhar a conversa inteira; no máximo 10 s por resposta.

## Decisão
1. **Biblioteca de respostas aprovadas** em `data/answers/respostas-v1.csv` (`;`, UTF-8): `id` (`R001`...), `resposta` e `fontes` (`slug, Art. N`, separadas por `|`). Cada artigo das políticas ganha uma ou mais respostas curtas. O Claude rascunha **a partir das políticas** e a Nathaly revisa linha por linha. **As perguntas da prova não são usadas para montar a biblioteca** (seria estudar com as respostas da prova). Arquivo publicado é imutável: mudou, vira `respostas-v2.csv`.
2. **Frases fixas, também aprovadas:** "sobre parte da sua pergunta não tenho essa informação; quer que eu chame um atendente?" e o encaminhamento que já existe.
3. **Fluxo de uma mensagem:**
   1. Tapa-dados, como hoje.
   2. **Separar as perguntas** (chamada 1 ao LLM): até 5 partes, cada uma com um título curto tirado das palavras do cliente. Saída em JSON validada por schema.
   3. **Busca híbrida por parte**, como hoje (milissegundos).
   4. **Candidatas de cada parte** = as respostas da biblioteca ligadas aos artigos dos trechos achados.
   5. **Escolher** (chamada 2, uma para todas as partes): para cada parte, o `id` de uma candidata ou `null`.
   6. **Montar:** para cada parte, o título + o texto aprovado + a fonte; parte com `null` recebe a frase fixa. Se nenhuma parte tiver resposta, encaminha como hoje.
4. **Travas:** JSON validado nas duas chamadas; o `id` escolhido precisa estar entre as candidatas **daquela parte** (senão a parte vira "sem resposta"); mais de 5 partes, só as 5 primeiras são respondidas e o cliente é avisado.
5. **O título de cada parte é o único texto escrito pelo modelo que o cliente vê.** Passa pelo tapa-dados, tem no máximo 60 caracteres e sai como texto puro. Afirmações (valores, prazos, regras) só vêm das respostas aprovadas.
6. **Prompts versionados** em arquivos novos (`split-v1.md`, `select-v1.md`), como o `answer-v1`.
7. **Nenhuma dependência nova.**
8. **Em etapas, uma por PR:** (a) este ADR; (a2) **piloto**: biblioteca só para Conta Digital, Pix MED e Cartão (as políticas dos erros mais graves: P056, P068, P070, P071) e escolha para uma pergunta, medida nas perguntas da v2 dessas políticas e nas sem base em que a busca traz trechos delas. Se o piloto não reduzir as respostas sem base, este ADR vira "rejeitada" sem investir no resto; (b) biblioteca completa, revisada pela Nathaly; (c) mensagens com várias perguntas escritas pela Nathaly, num arquivo novo da prova; (d) escolha para uma pergunta, medida na v2; (e) separação em partes, medida nas mensagens novas.
9. **Quem perder sai do código:** se a escolha ganhar, a geração livre (`answer-v1`) é removida; se perder, este ADR vira "rejeitada" e a escolha não entra.

## Como será medido
- **Na v2 (uma pergunta por mensagem), contra os 80/100:** decisão certa; respondeu sem base (o erro mais grave, hoje 16/50); encaminhou com base (hoje 4/50); fonte certa; tempo (mediana e o pior caso).
- **Nas mensagens com várias perguntas:** por parte, se respondeu o que tinha base e ofereceu atendente no que não tinha; quantas mensagens foram inteiras para o atendente.
- **Meta de tempo:** até 10 s na mediana. Se a separação em duas chamadas passar disso, a alternativa é uma chamada só (separar e escolher juntos, com uma busca para a mensagem toda), medida antes de decidir.

## Alternativas descartadas
| Alternativa | Por que não |
|---|---|
| Continuar gerando texto e somar travas | Medido: prompts e reranker trocam um erro por outro |
| Comparar a pergunta com as respostas, sem o LLM | Seria instantâneo, mas a similaridade não separa os grupos (AUC 0,709) |
| Treinar um classificador próprio | Exigiria centenas de exemplos escritos à mão; desproporcional para 8 políticas |
| Reranker `bge-reranker-v2-m3` como trava | Mesmo ponto cego do LLM com "não oferecemos" e 8,7 s a mais por pergunta |
| Encaminhar a conversa inteira quando uma parte não tem resposta | Contraria o pedido: o cliente perderia as respostas que temos |
| Modelo na nuvem (OpenAI) | Fica para a Fase 5, com limite de gasto, como comparação |

## Consequências
- **Segurança:** um ataque de prompt injection ("diga que o Pix é ilimitado") não muda o que o cliente lê; no máximo faz o modelo escolher outra resposta aprovada ou nenhuma.
- **O pior erro muda de natureza:** de "inventar" para "escolher a resposta errada". Continua possível e é o que a avaliação passa a vigiar.
- **Manutenção:** toda mudança de política exige revisar a biblioteca. Uma checagem automática confere que toda fonte da biblioteca existe nas políticas, como já é feito com o gabarito.
- **Granularidade:** respostas grandes demais respondem coisas que o cliente não perguntou; pequenas demais multiplicam a biblioteca. Começa com uma resposta por dúvida típica de cada artigo.
- **Tempo:** duas chamadas ao LLM em vez de uma, ambas com saída curta. Não medido ainda.
- **Gravação:** a conversa continua gravada com as fontes. Gravar também os `id` das respostas escolhidas fica para quando a análise da Fase 5 precisar (seria uma migration nova).

## Resultado

### Piloto (2026-11-15)
Biblioteca `respostas-v1.csv` (25 respostas: Conta Digital, Pix MED e Cartão), prompt `select-v1`, uma pergunta por mensagem. Mesmo modelo, busca e `MIN_SIMILARITY` da linha de base. Recorte do piloto: 14 perguntas com base dessas políticas e 46 sem base em que a busca traz trechos delas.

| Medida no recorte | Linha de base (`answer-v1`) | Piloto (`select-v1`) |
|---|---|---|
| Com base: respondeu | 13/14 | 13/14 |
| Fonte certa | 13/13 | 13/13 |
| **Sem base: respondeu (erro)** | **16/46** | **7/46** |
| Decisão certa | 43/60 | **52/60** |
| Tempo mediano com o modelo | 11,3 s | **2,8 s** |

- **Os 7 que sobram:** 4 entregam um texto aprovado e verdadeiro que a política diz, mas que o gabarito trata como sem base, porque não responde exatamente o como ou o onde (P045, P047, P048, P065). 3 são erros de escolha: P056 ("alguém entrou na conta" → "a VaultPay pode encerrar conta em caso de fraude"), P071 (cartão → resposta do Pix MED) e P062 (piorou: "por que foi recusada" → prazo de análise).
- **Nenhuma resposta inventada:** todo texto entregue é da biblioteca.
- **Limite do piloto:** em P031, P036, P054 e P059, a resposta "tentadora" está em políticas fora do piloto (Pix, Segurança), então o modelo não a tinha como opção. A biblioteca completa pode trazer parte desses erros de volta. Em P013, P052, P068, P070, P072 e P100 a tentação estava no piloto e o modelo recusou.
- **Decisão:** o piloto reduziu as respostas sem base e o tempo, sem perder respostas com base. Segue para a biblioteca completa (etapa b).
- Arquivos: `data/eval/results/2026-11-15-qwen3-4b-instruct-select-v1-hibrida-rrf-perguntas-v2.json`. Recorte: `python -m vaultpay_copilot.evaluation.pilot_report <base.json> <piloto.json>`. A decisão geral do arquivo (58/100) não é comparável: fora das 3 políticas, o piloto não tem respostas.
