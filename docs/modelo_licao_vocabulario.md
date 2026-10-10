# Modelos de lição digital para aprender vocabulário — pesquisa e modelo adotado

Documento de trabalho do Русский тренажёр. Reúne o que a pesquisa em aquisição de segunda língua e em psicologia cognitiva diz sobre lições digitais de idiomas, compara os modelos dos aplicativos mais usados e descreve o modelo implementado na página **Vocabulário** (`data/vocab_lessons/*.json`).

---

## 1. O que a pesquisa diz (resumo operacional)

| Princípio | Evidência | Consequência de design |
|---|---|---|
| **Prática de recuperação** (testing effect) | Karpicke & Roediger (2008); Nakata (2011) com flashcards de L2 | Quase toda tela pede para *lembrar*, não para *reler*. |
| **Espaçamento** e intervalos crescentes | Cepeda et al. (2006); Pimsleur (1967, *graduated interval recall*); Nakata (2015): o espaçamento absoluto importa mais que a forma exata da curva | Dentro da lição, cada palavra volta 3–5 vezes com intervalos crescentes; fora dela, a revisão espaçada do app (10 min → 1, 3, 7, 14, 30… dias). |
| **Reaprendizagem sucessiva** (retrieval to criterion) | Rawson & Dunlosky (2022): melhora forte e duradoura em vocabulário de L2 | Um item errado volta cerca de cinco telas depois, antes da re-escuta e da escrita, com até duas novas tentativas (uma nas perguntas de diálogo); depois segue para a revisão espaçada. |
| **Pré-teste / erro produtivo** | Kornell, Hays & Bjork (2009): tentativas falhas seguidas de feedback imediato retêm mais que só apresentação | A lição começa com o diálogo *antes* do vocabulário: o aluno tenta entender, erra, e o erro prepara a atenção para a apresentação. |
| **Recuperação produtiva > receptiva** para uso ativo | Webb (2009); Nakata (2016): *recall* é superior a *recognition* para a forma escrita | Escada receptivo → produtivo: ouvir e reconhecer → escolher a forma russa a partir do português → montar a frase → escrever. |
| **Número de encontros** | Webb (2007): efeito a partir de 3 encontros; conhecimento amplo exige 10+ | Cada construção aparece ~8–10 vezes numa lição (diálogo, cartão, 4–5 tarefas, diálogo de novo, revisão). |
| **Involvement Load** (need, search, evaluation) | Laufer & Hulstijn (2001); meta-análises: prevê bem, mas não sempre | As tarefas obrigam a *avaliar* entre formas concorrentes (evaluation) e a *buscar* a forma no contexto (search). |
| **Technique Feature Analysis (TFA)** — 18 critérios | Nation & Webb (2011); Nakata & Webb (2017): flashcards 12/18, cloze 9/18, cloze melhorado até 13/18 | Cada tipo de tarefa foi pontuado (seção 4) e só entraram os que somam ≥ 9 ou que cobrem uma lacuna específica. |
| **Agrupamento temático, não semântico** | Tinkham (1997), Waring (1997), Erten & Tekin (2008): listas de sinônimos/antônimos geram interferência | As palavras de cada lição formam uma *cena* (mudança, entrevista de emprego, laboratório), não uma lista de sinônimos. |
| **TOPRA** (Barcroft) | Elaboração semântica pesada reduz o aprendizado da forma | Tarefas de forma (terminação, preposição) e de sentido (tradução, inferência) ficam em telas separadas. |
| **Risco da múltipla escolha** | Boers et al. (2014, 2017); Li (2025): distratores podem ser memorizados como se fossem corretos | Feedback imediato mostrando a forma certa; o item errado volta para ser acertado; a forma certa reaparece depois em montagem e no diálogo; distratores nunca são apresentados como *input* (não são lidos em voz alta). |
| **Quatro vertentes equilibradas** | Nation (2007): input com foco no sentido, output com foco no sentido, foco na forma, fluência | Diálogo = input; montagem/resposta/escrita = output; cartões e cloze = forma; re-escuta do diálogo inteiro = fluência. |
| **Ciclo metacognitivo de escuta** | Vandergrift (2003); Goh & Vandergrift: prever → ouvir → verificar → ouvir de novo → refletir | O diálogo abre a lição com uma pergunta de sentido geral e fecha com perguntas de detalhe, reconstrução e re-escuta com transcrição. |
| **Ditado parcial** para segmentação | Yu, Boers & Tremblay (2025); pesquisas sobre ditado | Tarefa "Ouça e identifique": o áudio decide qual terminação foi dita. É onde o aluno mais erra (terminações). |
| **Aprender a construção inteira** (chunks) | Abordagem lexical (Lewis); Boers & Lindstromberg | A unidade de ensino é `verbo + preposição + pergunta russa + colocação`, nunca a palavra isolada. |

---

## 2. Modelos de aplicativos — ranking

Critérios: (a) eficiência = aprendizado por minuto demonstrado; (b) aproveitamento pedagógico = quantas das condições da seção 1 o modelo realmente usa.

| # | Modelo | Como a lição funciona | Evidência | Eficiência | Aproveitamento | Pontos fracos |
|---|---|---|---|---|---|---|
| 1 | **SRS de recuperação (Anki, flashcards espaçados)** | Pares forma–sentido, recuperação ativa, intervalos crescentes | A mais forte em laboratório para forma–sentido (Nakata 2011; TFA 12/18) | ★★★★★ | ★★★☆☆ | Pouco contexto e pouco uso; não ensina regência sem frase |
| 2 | **Babbel** | Poucas palavras novas → prática → diálogo que reúne tudo → revisão dos erros ao fim → Review Manager espaçado | Loewen et al. (2020): +0,7 subnível ACTFL oral em 12 semanas; ganhos em gramática e vocabulário | ★★★★☆ | ★★★★☆ | Diálogos curtos; pouco controle sobre distratores |
| 3 | **Clozemaster / Lingvist** | Lacuna em frase real + SRS adaptativo | Cloze 9/18 na TFA, 13/18 com contexto e múltiplas recuperações | ★★★★☆ | ★★★☆☆ | Frases soltas, sem cena; pouco áudio |
| 4 | **Duolingo (lições + Stories + HLR)** | Micro-exercícios gamificados; histórias com áudio e perguntas; revisão por *half-life regression* | Jiang et al. (2021): leitura e escuta comparáveis a semestres universitários iniciais; Settles & Meeder (2016): HLR reduz erro de previsão ~16% | ★★★☆☆ | ★★★★☆ | Muito reconhecimento, pouca produção; respostas previsíveis |
| 5 | **Pimsleur** | Áudio: pergunta em L1, pausa, resposta em L2 (*anticipation*), recall em intervalos | Base clássica de intervalos; forte para fala | ★★★☆☆ | ★★★☆☆ | Vocabulário estreito; sem leitura/escrita |
| 6 | **Busuu** | Lições + produção corrigida pela comunidade | Output com feedback humano | ★★★☆☆ | ★★★☆☆ | Correção irregular |
| 7 | **LingQ / input extenso** | Muita leitura e escuta com glosa | Incidental: precisa de 10+ encontros (Webb 2007) | ★★☆☆☆ por palavra | ★★★☆☆ | Lento para vocabulário-alvo específico |
| 8 | **Rosetta Stone (imersão sem L1)** | Imagem ↔ palavra, sem tradução | Pouca evidência de eficiência para adultos | ★★☆☆☆ | ★★☆☆☆ | Ambiguidade, lento, não serve para vocabulário abstrato B2 |

**Conclusão:** nenhum modelo sozinho é o melhor. O ganho máximo vem de combinar a *cena com diálogo* do Babbel/Duolingo Stories (input com sentido, contexto, escuta), a *escada de recuperação com espaçamento* do SRS/Pimsleur (retenção) e a *reaprendizagem sucessiva* (acertar pelo menos uma vez antes de sair), com um limite explícito de tentativas por item e tarefas de alta pontuação na TFA e distratores construídos a partir dos erros reais do aluno.

---

## 3. O modelo adotado: «Лексика в диалоге»

Cada lição corresponde a uma unidade da trilha e ensina **8 construções** do vocabulário dessa unidade (regências + léxico temático), sempre como bloco `construção + pergunta russa + colocação`.

### 3.1 Sequência de uma lição (≈ 25 min, ~55 telas, ~40 corrigidas)

1. **Ouvir antes de estudar** (pré-teste + escuta global) — o diálogo inteiro, com vozes diferentes (edge-tts: `ru-RU-SvetlanaNeural`, `ru-RU-DmitryNeural` e variantes de tom), sem transcrição. 1–2 perguntas de sentido geral. Errar aqui é esperado e útil.
2. **Apresentar e recuperar em intervalos crescentes** — para cada construção:
   - cartão de apresentação (áudio, regência, colocação, frase-exemplo, armadilha típica de quem fala português);
   - ~2 telas depois: *ouvir a construção → escolher o sentido* (receptivo);
   - ~5 telas depois: *ler o português → escolher a construção russa* entre formas concorrentes (produtivo por reconhecimento).
   Os cartões vão sendo intercalados com recuperações dos anteriores (como Pimsleur: 5 s, 25 s, 2 min…).
3. **Contexto e forma** (cada construção em frase nova, nunca a do cartão):
   - *Lacuna*: escolher a forma exata (preposição + caso + número) numa frase;
   - *Ouça e entenda*: ouvir uma frase e escolher a tradução — os distratores trocam **quem faz o quê** (papéis dos casos), aspecto ou negação;
   - *Montagem*: montar a frase com blocos, **com um bloco a mais** na forma errada (a terminação decide);
   - *Relacionar*: colocações verbo ↔ complemento.
4. **Voltar ao diálogo** (verificação final): perguntas de detalhe, reconstrução das falas com lacuna e *responder à fala*: ouve-se uma réplica e escolhe-se a resposta adequada e gramatical (princípio de antecipação do Pimsleur).
5. **Re-escuta com transcrição** (fluência): o diálogo inteiro com texto, tradução sob demanda e botão por fala.
6. **Produção escrita curta** (35–60 palavras) usando 3 construções da lição, salva para correção.
7. **Reaprendizagem sucessiva**: um item errado volta cerca de cinco telas depois (marcado ↻), antes da re-escuta e da escrita. Cada construção permite até duas novas tentativas; perguntas de diálogo permitem uma. O acerto interrompe a retomada, e os erros restantes seguem para a revisão espaçada. A nota da sessão usa apenas a primeira tentativa.

### 3.2 Regras para respostas não óbvias

1. Todas as alternativas têm a **mesma classe gramatical** e comprimento semelhante; a correta não pode ser sistematicamente a mais longa (o validador acusa).
2. Cada distrator corresponde a um **erro real de quem fala português**: preposição calcada no português (`зависеть из`), preposição certa com caso errado (`к стабильную работу`), caso certo com número/gênero errado, verbo vizinho com outra regência (`влиять на` × `оказывать влияние на`).
3. Nas traduções, os distratores usam **as mesmas palavras** com outro papel sintático (quem se adaptou a quem), outro aspecto (processo × resultado) ou outra polaridade — não há como acertar reconhecendo uma única palavra.
4. Nas tarefas de áudio, as alternativas **não são lidas** pelo TTS (seria resolver por comparação de som).
5. Nenhum distrator é uma palavra inexistente ou visivelmente malformada; todos são formas reais do russo.
6. Os distratores nunca são dados como *input* (não aparecem em cartões nem no diálogo) para não serem memorizados como corretos (Boers et al.).

### 3.3 Pontuação TFA das tarefas (0–18)

| Tarefa | Motivação (3) | Atenção/noticing (3) | Recuperação (5) | Uso criativo (3) | Retenção (4) | Total |
|---|---|---|---|---|---|---|
| Cartão de apresentação | 1 | 3 | 0 | 0 | 2 | 6 (só introduz; sem ele o resto perde base) |
| Ouvir construção → sentido | 1 | 2 | 3 | 0 | 2 | 8 |
| Português → construção russa (com formas concorrentes) | 1 | 3 | 4 | 0 | 3 | 11 |
| Lacuna em frase nova | 1 | 3 | 3 | 1 | 3 | 11 |
| Ouça e entenda (papéis dos casos) | 2 | 3 | 3 | 1 | 3 | 12 |
| Montagem com bloco a mais | 1 | 3 | 4 | 1 | 3 | 12 |
| Responder à fala | 2 | 2 | 4 | 2 | 3 | 13 |
| Reconstrução do diálogo | 2 | 3 | 4 | 1 | 3 | 13 |
| Produção escrita com 3 construções | 3 | 2 | 5 | 3 | 3 | 16 |
| **Sequência inteira** (espaçada, repetida, reaprendida) | | | | | | cobre os 18 critérios |

### 3.4 Onde fica no aplicativo

- Página **Vocabulário** (menu lateral, só no curso russo): 24 lições, uma por unidade, com glossário audível, player do diálogo e progresso por lição.
- Cada unidade em **Estudar** mostra um atalho para a lição de vocabulário correspondente (pré-ensinar o léxico antes da gramática).
- As respostas entram no histórico, no painel, no caderno de erros, na cobertura do Лексический минимум (etiquetas `lexeme:`) e na revisão espaçada (`unit_id` interno `vocab_vNN`).
- Áudio: `GET /api/tts?voice=f|m|f2|m2&mode=dialogue` (cache em `data/tts_cache`); pré-geração: `./.venv/bin/python tools/pregenerate_audio.py --vocab`.

---

## 4. Fontes

- Nation, I.S.P. & Webb, S. (2011). *Researching and Analyzing Vocabulary* — Technique Feature Analysis. Avaliação aplicada: [Le, Coxhead & Bui (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5431462); [Nakata & Webb (2017)](https://www.academia.edu/42180185/Nakata_T_and_Webb_S_A_2017_Vocabulary_learning_exercises_Evaluating_a_selection_of_exercises_commonly_featured_in_language_learning_materials).
- Laufer, B. & Hulstijn, J. (2001). Involvement Load Hypothesis. [Hulstijn & Laufer (2001)](https://onlinelibrary.wiley.com/doi/abs/10.1111/0023-8333.00164); [revisão sistemática (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9598591/).
- Loewen, S. et al. (2020). Babbel e proficiência oral. [Foreign Language Annals](https://onlinelibrary.wiley.com/doi/abs/10.1111/flan.12454); [ScienceDaily](https://www.sciencedaily.com/releases/2020/06/200609095027.htm).
- Babbel — método e revisão: [The Babbel Method](https://www.babbel.com/the-babbel-method); [How Babbel Works](https://www.babbel.com/how-babbel-works).
- Jiang, X. et al. (2021). Duolingo: leitura e escuta. [Foreign Language Annals](https://onlinelibrary.wiley.com/doi/10.1111/flan.12600).
- Settles, B. & Meeder, B. (2016). Half-life regression. [ACL Anthology](https://aclanthology.org/P16-1174/).
- Pimsleur — graduated interval recall e anticipation: [Wikipedia](https://en.wikipedia.org/wiki/Pimsleur_Language_Programs).
- Webb, S. (2007). Repetição e conhecimento de vocabulário. [ResearchGate](https://www.researchgate.net/publication/31064743_The_Effects_of_Repetition_on_Vocabulary_Knowledge).
- Nakata, T. — formatos de recuperação e espaçamento: [Retrieval formats (IRAL)](https://www.degruyterbrill.com/document/doi/10.1515/iral-2015-0022/html); [Expanding vs equal spacing (SSLA)](https://www.cambridge.org/core/journals/studies-in-second-language-acquisition/article/abs/effects-of-expanding-and-equal-spacing-on-second-language-vocabulary-learning/D1D796306985C52F9BE7A1200AC50DB9).
- Rawson, K. & Dunlosky, J. (2022). Successive relearning. [Current Directions in Psych. Science](https://journals.sagepub.com/doi/full/10.1177/09637214221100484).
- Kornell, N., Hays, M. & Bjork, R. (2009). Unsuccessful retrieval attempts. [PDF](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/07/Hays_Kornell_RBjork_inpress.pdf).
- Tinkham, T. (1997). Agrupamento semântico × temático. [Second Language Research](https://journals.sagepub.com/doi/10.1191/026765897672376469).
- Barcroft, J. — TOPRA. [The TOPRA model](https://sites.wustl.edu/barcroft/the-topra-model/).
- Boers, F. et al. (2014). Exercícios de colocações e interferência de distratores. [Language Teaching Research](https://journals.sagepub.com/doi/10.1177/1362168813505389); [Li (2025)](https://onlinelibrary.wiley.com/doi/10.1111/ijal.12666).
- Nation, P. (2007). The Four Strands. [Taylor & Francis](https://www.tandfonline.com/doi/abs/10.2167/illt039.0).
- Vandergrift, L. — ciclo metacognitivo de escuta. [Goh & Vandergrift (Routledge)](https://www.routledge.com/Teaching-and-Learning-Second-Language-Listening-Metacognition-in-Action/Goh-Vandergrift/p/book/9780367254254).
- Yu, X., Boers, F. & Tremblay, P. (2025). Ditado e dictogloss. [Language Teaching Research](https://journals.sagepub.com/doi/10.1177/13621688221117242).
