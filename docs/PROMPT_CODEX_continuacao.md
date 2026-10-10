# Prompt para o Codex — continuar o módulo «Лексика в диалоге» + modo escuro padrão

Copie tudo abaixo da linha e envie ao Codex, com a pasta `/home/mx/Documents/Curso russo` aberta.

---

Você vai continuar um trabalho já começado no aplicativo local **Русский тренажёр / LinguaLab** (`russotrainer/`). Trabalhe **só no curso russo**; não crie nem altere conteúdo de romeno ou cazaque. Leia antes de mudar qualquer coisa:

1. `russotrainer/README.md` — arquitetura, tipos de exercício, convenções.
2. `russotrainer/docs/modelo_licao_vocabulario.md` — a pesquisa e o modelo pedagógico que você vai seguir (ordem da lição, regras de distratores, pontuação TFA).
3. `continuacao_curso_russo_TRKI_II_codex.txt` — perfil do aluno (brasileiro, B1→B2, ТРКИ-II). Regras que valem para tudo: regência sempre como `verbo + preposição + pergunta russa` (ex.: `зависеть от кого? чего?`), nome dos casos em russo (`дательный падеж`), feedback técnico e sem elogio vazio, vocabulário por combinações e não por tradução isolada, nunca repetir no exercício a frase exata do exemplo.
4. `russotrainer/vocab_lessons.py`, `russotrainer/data/vocab_lessons/v01_dativo.json` (lição-modelo) e `v02`–`v10`.

## O que já está pronto (não refaça)

- **Pesquisa** em `docs/modelo_licao_vocabulario.md`.
- **Backend** (`vocab_lessons.py` + `app.py`): cada arquivo `data/vocab_lessons/vNN_*.json` gera ~61 telas com IDs estáveis `vx-<lição>-<chave>-<papel>` (papéis: `card`, `mean`, `form`, `cloze`, `hear`, `build`, `gist-N`, `detail-N`, `rec-N`, `reply-N`, `match`, `review`, `write`). Endpoints: `GET /api/vocab/bootstrap`, `/api/vocab/lesson?id=`, `/api/vocab/session?id=&part=1|2|3|all`. As tentativas usam `unit_id = vocab_vNN` e entram em histórico, revisão espaçada, caderno de erros e cobertura lexical (`lexeme:`).
- **TTS de diálogo**: `GET /api/tts?voice=f|m|f2|m2` (Svetlana, Dmitry e variações de tom; `TTSService.DIALOGUE_VOICES`). Cache em `data/tts_cache`.
- **Frontend** (`static/app.js`, `index.html`, `styles.css`): página **Vocabulário** (menu lateral, só russo), player de diálogo sequencial com destaque da fala, tipos novos `vocab_card`, `dialogue`, `dialogue_review`, bloco extra em `sentence_order` (`extra_block`), áudio da forma correta depois da resposta (`after_audio`), reaprendizagem sucessiva (item errado volta ~5 telas depois, até 2 vezes; perguntas de diálogo 1 vez), resumo honesto da sessão (nota só da 1ª tentativa), atalho da lição dentro da aula de cada unidade.
- **Distratores do jogo de cobertura lexical** (Terminações → Cobertura lexical) agora vêm da mesma classe gramatical, com final parecido e sem sinônimos (`LexicalMinimumStore._vocabulary_options`).
- **Validador** `tools/validate_content.py` confere as lições (gabarito nas opções, blocos da montagem, pares repetidos, «или» em texto português) e avisa quando a resposta é visivelmente a alternativa mais longa/curta.
- **Lições prontas e validadas: v01–v10** (unidades 1–10).

## Tarefa 1 — escrever as lições v11 a v24

Crie um arquivo por unidade em `russotrainer/data/vocab_lessons/`, copiando **exatamente o esquema de `v01_dativo.json`**: `id`, `unit_id`, `order`, `title` (russo), `theme`, `description` (PT), `speakers` (nome → `f`/`m`/`f2`/`m2`), `dialogue` (`title`, `setting` em PT, 9–12 `lines` com `speaker`, `ru`, `pt`), `gist` (1–2), **8** `items`, `detail` (2), `reconstruct` (4), `match` (6 pares), `replies` (2), `writing`.

Cada item: `key`, `lemma` (forma do dicionário, para `lexeme:`), `tag`, `head`, `regency`, `case`, `pt`, `chunk`, `chunk_pt`, `chunk_wrong` (3), `form_note`, `trap` (armadilha de quem fala português), `example` (`ru`, `pt`, `extra` = uma palavra com terminação/preposição errada que **não** está na frase, `note`), `cloze` (`ru` com `___`, `answer`, `wrong` (3), `pt`, `note`), `hear` (`ru`, `pt`, `wrong` (3), `note`).

Plano de construções (já pensado para evitar repetir o que v01–v10 ensinam):

| Lição | Unidade | Cena sugerida | 8 construções |
|---|---|---|---|
| v11 | u11_multikulturalizm | festival de culturas na universidade (Алина f, Мурад m) | уважение к, относиться к, гордиться, придерживаться (род.), соблюдать, принадлежать к (× принадлежать кому), сосуществовать с, подвергаться (дат.) |
| v12 | u12_roditelnyi | casal planeja férias e orçamento | нет / не было (род.), много / несколько (род. pl), бояться, достигать / достичь (род.), избегать / избежать, во время × в течение, не хватать кому? чего?, касаться (что касается…) |
| v13 | u13_vinitelnyi | amigos combinam o fim de semana | за + вин. (tempo gasto), через + вин., на + вин. (prazo planejado), приглашать / пригласить куда?, посещать / посетить, проводить / провести время, ждать (кого? что? × чего?), встречать / встретить |
| v14 | u14_predlozhnyi | consulta médica | заботиться о, думать о, сомневаться в, участвовать в, отказываться от (hábitos), лечиться от, болеть чем? (творительный!), мечтать о |
| v15 | u15_dvizhenie | sábado de família (mãe f, filho m) | ходил / ездил (ida e volta), шёл / ехал (a caminho), вести к (consequência), носить (roupa), везти (везёт кому?), ухаживать за (× заботиться о), водить (детей в школу), возить |
| v16 | u16_pristavki_dvizheniya | vizinhos de subúrbio | чтобы + инфинитив, чтобы + прошедшее, для, за (ir buscar: пойти за хлебом), ради, переехать из … в …, зайти к / в, доехать до |
| v17 | u17_vozvratnye | jovens e família | отличаться от, договориться с … о …, пользоваться (твор.), начинать × начинаться, стараться, встречаться с, обижаться на, относиться к (outra frase) |
| v18 | u18_uslovie | amiga pensa em pedir demissão | если бы …, … бы, Не могли бы вы …?, успеть + сов. вид, устроиться на работу (кем?), уволиться с, нельзя + вид (proibido × impossível), соглашаться / согласиться на, подать заявление на |
| v19 | u19_sravnenie | amigos comparam cidades e apartamentos | уверен в, доволен (твор.), способен к, похож на, готов к, рад (дат.), сравнивать / сравнить с, знаком с |
| v20 | u20_chislitelnye | noticiário econômico (m) + economista (f) | составлять / составить, достигать / достичь (nível), увеличиться на (× до), снизиться до (× на), в … раза / раз, приходиться на (долю), тратить на, в среднем |
| v21 | u21_mestoimeniya | estudante e avô antes da eleição | участвовать в выборах, голосовать за / против, выступать за / против, взять на себя (ответственность), чувствовать себя, поддерживать (кого? что?), обещать (кому? что?), ни от кого не зависеть (dupla negação) |
| v22 | u22_vremya | chefe e funcionário planejam um prazo | к + prazo (к пятнице), перед, за … до, через … после, с … по, пока не, накануне (род.), по + дат. pl (по понедельникам) |
| v23 | u23_sintaksis | debate na TV sobre clima | согласно (дат.), по данным, по мнению, в связи с, в результате (род.), в отличие от, с целью (род.), за счёт (род.) |
| v24 | u24_slovoobrazovanie | seminário universitário | недооценивать, переоценивать, противоречить (дат.), сотрудничать с, предшествовать (дат.), злоупотреблять (твор.), превосходить (вин.), недоверие к |

### Regras de qualidade (obrigatórias — o aluno pediu «respostas não óbvias»)

1. Todas as alternativas têm a **mesma classe gramatical e comprimento parecido**; a certa não pode ser a mais longa nem a mais curta de forma visível.
2. Cada distrator é um **erro real de quem fala português**: preposição calcada (`зависеть из`, `рассчитывать с`), preposição certa com caso errado (`к новую школу`), caso certo com número/gênero errado, verbo vizinho com outro sentido (`сдавать × сдать`, `снимать × сдавать`, `уволить × уволиться`).
3. Distratores são **formas reais** do russo (nada inventado), mas **agramaticais ou com outro sentido naquele contexto**. Se um distrator puder ser defendido como correto por um nativo, troque-o (ex.: `добраться в центр`, `отвечать за жизни` são aceitáveis — não use).
4. Nas traduções de `hear`, os distratores usam as mesmas palavras trocando **quem faz o quê**, o aspecto/tempo ou a polaridade. Não pode ser possível acertar reconhecendo uma só palavra.
5. Frases novas em cada tarefa: `example`, `cloze` e `hear` diferentes entre si e diferentes das frases das unidades em `data/units/` e do diálogo.
6. `match`: cada complemento deve servir a **um só** verbo da lista (em sentido e regência). Confira todos os cruzamentos.
7. `reconstruct.gap` precisa ser substring exata da fala (`line` é índice a partir de 0).
8. Todo texto em português: nada de «или», «и» etc. russos no meio. Português do Brasil.
9. Aspecto e russo revisados com cuidado: stress não é marcado; use `ё` onde é obrigatório.

Depois de cada arquivo rode:

```bash
cd russotrainer && python3 tools/validate_content.py
```

e resolva erros **e avisos** antes de passar para o próximo.

## Tarefa 2 — modo escuro como padrão + melhorias visuais

Hoje `index.html` tem `<meta name="color-scheme" content="light">` e `styles.css` tem tokens só claros em `:root` (+ variações por curso em `body[data-course="romanian"|"kazakh"]`) e muitas cores fixas (`#fff`, `#fffefa`, `#faf8f1`, `#ece9df`, `#cbd3cc`, `#f1dfb9`…).

1. **Tokens**: substitua toda cor fixa de superfície, borda e texto por variáveis (`--surface`, `--surface-2`, `--surface-3`, `--border`, `--ink`, `--muted`, `--accent`, `--accent-soft`, `--warn`, `--warn-soft`, `--danger`, `--danger-soft`, `--focus`…). Nenhum `#fff` solto deve sobrar fora das definições de tema.
2. **Escuro por padrão**: `<html data-theme="dark">`, `<meta name="color-scheme" content="dark light">`. Paleta escura com contraste AA (texto ≥ 4.5:1): fundo verde-petróleo muito escuro (coerente com a sidebar `#12382d`), painéis um tom acima, acento âmbar/verde. Defina também as versões escuras para `romanian` e `kazakh`.
3. **Alternador de tema** no topo (ao lado de «Consulta»): escuro / claro / sistema; guardar em `localStorage` (`lingualab-theme`) com try/catch; aplicar antes da primeira pintura (script inline no `<head>`) para não piscar.
4. **Revisar todas as telas nos dois temas**: painéis, cartões de unidade, trilha, tabelas de terminações (`.word-build` base × terminação precisa continuar legível), mapa de casos (cada `.case-*` com cor própria), feedback (correto/parcial/errado/pendente), diálogos (`.v-f`, `.v-m`, `.v-f2`, `.v-m2`, `.dlg-line.playing`, `.target-word`), cartão `.vocab-card` e `.vc-trap`, botões `.option` (hover/selecionado/desabilitado), `dialog` do dicionário, toast, inputs/selects/textarea, barras de progresso, `result-ring`.
5. **Melhorias visuais** (sem mudar a lógica):
   - estados de foco visíveis (`:focus-visible`) em todos os botões e opções; navegação completa pelo teclado nas alternativas (teclas 1–4 escolhem, Enter confirma/avança — implementar no `bindResponseEvents` sem quebrar os campos de texto);
   - feedback de resposta com ícone e cor além do texto (acessível para daltonismo);
   - `prefers-reduced-motion` desliga transições;
   - layout do exercício com largura máxima de leitura (~760px) e tipografia maior para o texto russo (≥ 20px em prompts e falas);
   - responsivo em 375px sem rolagem horizontal (testar sidebar, topo com seletor de curso + consulta + tema, tabelas com `.table-scroll`);
   - player de diálogo com indicação clara de carregamento/tocando/parado e contador de audições.
6. Não use bibliotecas externas; é tudo HTML/CSS/JS puro servido pelo `app.py`.

## Tarefa 3 — acabamento

1. `docs/modelo_licao_vocabulario.md`, passo 7: o texto diz que os erros voltam «no fim da sessão»; o código devolve o item ~5 telas depois (antes da re-escuta e da escrita). Ajuste o texto para refletir o comportamento real.
2. README: adicione uma seção **Vocabulário (Лексика в диалоге)** (esquema do JSON, endpoints, vozes, como validar) e mencione o tema escuro.
3. `tools/pregenerate_audio.py`: acrescente `--vocab` para pré-gerar todas as falas dos diálogos (com a voz de cada falante via `tts.audio_for(texto, "russian", speaker=voz)`), as construções (`chunk`, voz `f`), os exemplos e as frases de `hear` (vozes alternadas `f`/`m` como em `vocab_lessons.py`) e as réplicas. Depois rode-o (precisa de internet).
4. Suba `APP_VERSION` em `app.py` para `1.5.0`.

## Como testar sem estragar o progresso real do aluno

Nunca teste com `data/progress.sqlite3`. Use banco e exportações temporários:

```bash
cd "/home/mx/Documents/Curso russo" && RUSSO_DB_PATH=/tmp/rt_test.sqlite3 RUSSO_EXPORT_DIR=/tmp/rt_exports ./russotrainer/.venv/bin/python russotrainer/app.py --no-browser --port 8766
```

Teste no navegador, nos dois temas e em 375px: página Vocabulário → abrir cada lição → Parte 1, 2 e 3 (inclusive errar de propósito para ver o item voltar, a montagem com bloco extra, o `match`, a re-escuta e a escrita). Confira o console sem erros. Rode o validador no final e reporte o resultado real (se algo falhar, diga o que falhou).

Ao terminar, liste: lições criadas, avisos restantes do validador, arquivos alterados e o que não foi possível testar.
