# LinguaLab · Russo, Romeno e Cazaque

Aplicativo local de aprendizagem de idiomas com cursos independentes. O curso russo mantém a preparação ТРКИ-II/B2; o curso romeno começa no A1; o espaço do curso cazaque está preparado para receber unidades futuras. O estudo funciona localmente; a geração inicial de cada áudio usa internet e depois fica em cache.

O seletor no topo troca curso, identidade visual, unidades, referências, métricas, fila de revisão e produções pendentes. O progresso de um idioma não desbloqueia nem mistura exercícios de outro.

## Executar

Na pasta principal do curso:

```bash
./run.sh
```

Na primeira execução, o script cria um ambiente Python local, instala `edge-tts`, importa o índice morfológico do OpenRussian e indexa o PDF do `Лексический минимум ТРКИ-II`. O navegador abre em `http://127.0.0.1:8765`. Para iniciar sem abrir o navegador automaticamente:

```bash
./run.sh --no-browser
```

Para usar outra porta:

```bash
./run.sh --port 9000
```

Encerre com `Ctrl+C` no terminal.

## Onde ficam os dados

- `data/progress.sqlite3`: banco principal, tentativas e agenda de revisão;
- `exports/relatorio_atual.md`: resumo fácil de ler;
- `exports/analise_atual.json`: histórico completo para análise detalhada;
- `exports/respostas.csv`: todas as tentativas em formato de planilha.
- `exports/problemas_reportados.md`: exercícios sinalizados pelo botão “Notificar erro”.

Os arquivos de exportação são atualizados depois de cada resposta. Para uma análise futura do curso, basta ler principalmente `exports/relatorio_atual.md` e `exports/analise_atual.json`.

Cada tentativa registra:

- data e sessão;
- unidade e exercício;
- enunciado, resposta e forma esperada;
- acerto, erro ou produção pendente de correção;
- SC, C ou CC;
- tempo de resposta;
- categoria informada pelo aluno: regência, terminação, vocabulário, aspecto, digitação ou desconhecimento;
- etiquetas pedagógicas.

Respostas digitadas podem receber crédito parcial. Um erro mínimo de digitação não é contado do mesmo modo que uma regência errada; a resposta esperada continua sendo exibida e o item volta mais cedo na revisão.

## Revisão espaçada

Um erro volta aproximadamente em dez minutos. Acertos sem consulta avançam por intervalos de 1, 3, 7, 14, 30, 60 e 120 dias. Consultas reduzem o intervalo: um acerto consultado não é tratado como recuperação independente.

Respostas parcialmente corretas voltam em cerca de seis horas. Isso evita tratar uma terminação errada como domínio completo, mas preserva o crédito pelo que foi recuperado.

## Terminações e cobertura do TRKI-II

A página **Terminações** reúne mapas visuais dos casos, tabelas de substantivos e adjetivos, alertas para famílias especiais de nível B2, mnemônicos do plural e sessões configuráveis. A flexão pode ser treinada por múltipla escolha ou por produção digitada sem alternativas; depois da resposta, o feedback separa visualmente base e terminação. O inventário derivado do PDF contém:

- 5.006 lemas únicos para reconhecimento lexical;
- 2.845 lemas declináveis;
- 35.584 desafios de flexão gerados e validados;
- 5.006 cartões de cobertura lexical, incluindo verbos e palavras invariáveis.

O filtro “Só lemas inéditos” percorre o inventário sem repetir palavras já praticadas. Um lema passa a **visto** na primeira resposta e a **dominado** após dois acertos exatos sem consulta. Esses dados ficam na tabela `lexeme_progress` do banco principal e também aparecem no resumo exportado.

As glosas do léxico mínimo estão em inglês porque essa é a língua de tradução do PDF-fonte; cada palavra russa continua clicável no dicionário do aplicativo.

## Verbos com prefixo (só russo)

A página **Prefixos** é um módulo autônomo de múltipla escolha para assimilar o que cada prefixo verbal (при-, у-, вы-, до-, про-, пере-, за-, на-, раз-/рас-, с-/со-, о-/об-, вз-/вс-/воз-, по-…) acrescenta ao sentido do verbo. Nos blocos por família, **todas as 4 alternativas compartilham o prefixo** (bloco при-: `приложить / привезти / привыкнуть / приобрести`), portanto o aluno precisa conhecer o verbo inteiro. O bloco **Contrastes** faz o movimento inverso: mantém o radical e varia o prefixo (`дочитать / перечитать / прочитать / зачитать`) para tornar a nuance morfológica explícita. O vocabulário das frases é B1–B2 do `Лексический минимум ТРКИ-II`.

- Conteúdo em `data/prefix_verbs.json` (16 famílias + 1 bloco contrastivo, 76 exercícios `choice`). Não entra na trilha **Estudar** nem na cadeia de travamento: é acessível a qualquer momento, como **Terminações**.
- As respostas contam no histórico, na precisão do painel e na revisão espaçada (`unit_id` interno `prefix_verbs`).
- Endpoints: `GET /api/prefixes/bootstrap` (blocos, textos de apoio, domínio por prefixo) e `GET /api/prefixes/questions?stage=<id|all>&limit=<n>`.
- Inventário completo dos verbos prefixados A1–B2 extraído das fontes: `exports/verbos_prefixados.md` (895 lemas em 21 famílias, com aspecto e par aspectual do OpenRussian).

## Aula narrada de cada unidade

Ao escolher uma unidade em **Estudar**, antes dos exercícios aparece a aula da unidade. Ela tem quatro camadas:

1. **Roteiro de aprendizagem** (`lesson_flow`): as quatro fases da sessão — recuperar, compreender, praticar, transferir;
2. **Texto de gramática** (`grammar`): dois ou três blocos em português, cada um com um botão **🔊 Ouvir esta parte**;
3. **Exemplos audíveis** (`grammar[].examples`): frase russa + tradução + nota, cada uma com o seu botão de áudio em voz nativa;
4. **Erros típicos de quem fala português** (`grammar[].pitfalls`) e a **tabela de memorização** (`memory_table`).

No topo há o player **🔊 Ouvir a aula inteira**, com controles de reprodução, velocidade e barra de progresso do próprio navegador.

A narração é gerada por `edge-tts` com a voz multilíngue **`pt-BR-ThalitaMultilingualNeural`**: ela lê a explicação em português e pronuncia os exemplos russos com fonética nativa, sem trocar de motor no meio da frase. O roteiro falado fica em `grammar[].audio_script` — uma versão escrita para o ouvido, diferente do texto lido na tela (setas, barras e abreviações viram palavras). Sem esse campo, o servidor cai para o texto escrito, normalizado por `spoken_text()`.

Hoje são **126 minutos de aula narrada** em 25 unidades russas.

- Endpoint: `GET /api/lesson-audio?unit_id=<id>&block=<n|all>`;
- O primeiro clique gera o MP3 (uma aula inteira leva cerca de um minuto); depois ele fica em `data/tts_cache` e toca instantaneamente, inclusive offline.

Para não esperar nada na primeira vez, gere tudo de uma vez com internet:

```bash
./.venv/bin/python tools/pregenerate_audio.py            # todas as aulas
./.venv/bin/python tools/pregenerate_audio.py --blocks   # só os blocos (mais rápido)
./.venv/bin/python tools/pregenerate_audio.py u12 u13    # só estas unidades
```

## Áudio e dicionário

No curso russo, palavras do enunciado são clicáveis. Um clique:

1. lê a palavra com `edge-tts`;
2. abre o verbete morfológico local;
3. mostra lema, tradução, classe, forma/caso possível, aspecto e par aspectual;
4. mostra regência e tradução portuguesa quando o verbete pertence ao vocabulário do curso.

Ao clicar numa alternativa, o aplicativo lê a alternativa inteira. Áudios gerados ficam em `data/tts_cache`.

O TTS escolhe a voz pelo curso: `ru-RU-SvetlanaNeural` para russo, `ro-RO-AlinaNeural` para romeno e `kk-KZ-AigulNeural` para o futuro conteúdo cazaque. As aulas narradas usam uma voz separada, `pt-BR-ThalitaMultilingualNeural` (parâmetro `mode=lesson` em `/api/tts`). Exercícios de listening oferecem velocidade normal e lenta e só mostram a transcrição depois da resposta.

O dicionário contém 58.825 verbetes e 837.609 formas importadas de [OpenRussian](https://en.openrussian.org). Os dados do repositório `Badestrand/russian-dictionary` são licenciados sob CC BY-SA 4.0. Esse conjunto fornece traduções em inglês e alemão; o aplicativo acrescenta um glossário português próprio para o vocabulário estudado. Veja `third_party/OpenRussian-NOTICE.md`.

## Trilha do curso russo

A trilha cobre a gramática de nível B1–B2 em 25 unidades, na ordem em que devem ser feitas. As unidades 1–11 partem de «Время обсуждать» e dos capítulos de Kagan/Kudyma/Miller já usados no curso; as unidades 12–24 completam o programa gramatical de «Russian Grammar in Tables» (Кузьмина), de «Russian cases» (Red Kalinka) e da coluna «Лексика и грамматика» dos dez capítulos de Kagan.

| # | Unidade | Gramática central | Fonte principal |
|---|---------|-------------------|-----------------|
| ◆ | Diagnóstico cumulativo | mede regência, terminação, léxico e aspecto | itens próprios |
| 1 | Дательный падеж | dativo · к, благодаря · где/куда/откуда | Время обсуждать, урок 1 |
| 2 | Творительный падеж | instrumental com e sem preposição | Время обсуждать, урок 2 |
| 3 | Contrastes de regência | о que o português engana: от/в/на/к | urok 1–2 + Кузьмина |
| 4 | Aspecto e movimento | pares aspectuais · при-/у-/пере- | Кузьмина, Виды глагола |
| 5 | Integração B2 | conectores argumentativos · abertura de texto | В мире людей (письмо) |
| 6 | Recuperação intercalada | os cinco grupos de regência misturados | interleaving |
| 7 | Образование | движение com при-/у-/вы- · regência escolar | Kagan, гл. 1 |
| 8 | Работа | который: concordância, caso e «cujo» | Kagan, гл. 2 |
| 9 | Наука | из-за/благодаря/несмотря на то что · passivo | Kagan, гл. 7–8 |
| 10 | СМИ | discurso indireto · ли · чтобы + passado | Kagan, гл. 1 |
| 11 | Мультикультурализм | деепричастие e причастие | Kagan, гл. 7 e 9 |
| 12 | Родительный падеж | as seis funções · genitivo plural · numerais | Red Kalinka + Кузьмина |
| 13 | Винительный падеж | animacidade · tempo · aspecto no imperativo | Kagan, гл. 3 |
| 14 | Предложный падеж | quatro funções · locativo em -у́ · advérbios | Kagan, гл. 7 |
| 15 | Глаголы движения | идти × ходить · passado · usos figurados | Kagan, гл. 4 |
| 16 | Prefixos de movimento | os 11 prefixos e suas preposições · чтобы, для, за | Kagan, гл. 5 |
| 17 | Возвратные глаголы | os sete valores de -ся · начинать × начинаться | Kagan, гл. 6 |
| 18 | Условное наклонение | если × если бы · бы cortês · aspecto no infinitivo | Kagan, гл. 2 |
| 19 | Comparação | comparativo, superlativo e adjetivo curto | Кузьмина |
| 20 | Числительные | declinação · datas · percentuais e coletivos | Kagan, гл. 9 |
| 21 | Местоимения | -то × -нибудь · dupla negação · сам/самый/себя/свой | Kagan, гл. 8 |
| 22 | Выражение времени | o sistema temporal completo · за…до, через…после | Кузьмина |
| 23 | Sintaxe | conjunções por função · ordem tema-rema | Kagan, гл. 8 e 10 |
| 24 | Словообразование | famílias de raiz · sufixos · prefixos · compostas | Kagan, todos |

Cobertura: os seis casos com todas as funções, aspecto nos quatro contextos (passado/presente, infinitivo, imperativo, movimento), verbos de movimento com e sem prefixo, particípios, gerúndios, voz passiva, verbos em -ся, condicionais, comparação, adjetivos curtos, numerais, pronomes indefinidos e negativos, expressão de tempo, causa, concessão, condição e finalidade, discurso indireto, ordem das palavras e formação de palavras.

## Acrescentar unidades

Cada unidade é um arquivo JSON independente em `data/units` e declara `course_id` (`russian`, `romanian` ou `kazakh`). Arquivos antigos sem esse campo continuam pertencendo ao curso russo. O servidor lê todos os arquivos `*.json` ao iniciar. Depois de editar ou acrescentar conteúdo, reinicie o aplicativo ou use o endpoint interno de recarga.

Tipos disponíveis:

- `choice`: múltipla escolha (tipo principal do curso russo);
- `sentence_order`: montagem com blocos;
- `flashcard`: recuperação ativa e autoavaliação;
- `open_text`: produção salva para correção posterior;
- `match_pairs`: relacionar pares (ex.: verbo ↔ pergunta russa da regência). Use `pairs: [{"left": ..., "right": ...}]`; o servidor embaralha o lado direito e oculta o gabarito.
- `reading`: compreensão de texto com inferência e alternativas embaralhadas;
- `listening`: compreensão oral gerada por TTS. Use `audio_text` para o texto oculto; com `response_type: "input"`, o item vira ditado e recebe crédito parcial.
- `input` e `correction`: **tipos legados**. O motor ainda os aceita, mas o curso russo não os usa mais — resposta digitada livre e reescrita de frase inteira eram punitivas e foram convertidas em `choice` equivalentes, que testam o mesmo ponto gramatical com o erro original entre as alternativas. Não use em conteúdo novo do curso russo.

Nas unidades novas, a sessão segue quatro fases: recuperação sem pistas, compreensão por leitura/listening, prática guiada com análise de erro e transferência para escrita ou fala. As alternativas objetivas são preparadas no servidor: em cada bloco de N questões com N opções, o gabarito ocupa cada posição uma vez em ordem aleatória. Isso evita tanto a posição fixa do JSON quanto sequências acidentais longas na mesma coluna.

Veja `data/modelo_unidade.json.example` para o esquema mínimo. IDs de exercício precisam ser únicos em todo o aplicativo. Para respostas digitadas, `valid_answers` permite registrar variantes realmente aceitáveis; a correção ignora caixa, espaços extras, pontuação final e a diferença entre `е` e `ё`, mas não ignora terminações gramaticais.

Cada unidade também pode trazer, além de `reference` (cards de regência mostrados na página **Referência**):

- `grammar`: lista de blocos com a aula da unidade, exibida ao selecionar a unidade em **Estudar**. Cada bloco aceita:
  - `title` e `paragraphs`: o texto lido na tela;
  - `audio_script`: o mesmo conteúdo reescrito **para o ouvido** — frases curtas, exemplos russos lidos por extenso, sem setas nem barras. É o que o player narra;
  - `examples`: `[{"ru", "pt", "note"}]`, cada exemplo com botão de áudio próprio em voz russa nativa;
  - `pitfalls`: lista de erros típicos de quem fala português, destacada em vermelho;
- `memory_table`: uma tabela `{"title", "columns": [...], "rows": [[...]], "note"}` para memorização de paradigmas, exibida junto com `grammar`. `memory_tables` (plural) aceita várias;
- `lesson_flow`: `[{"title", "description"}]` com as fases da sessão;
- `source_note`: a origem pedagógica da unidade, exibida ao pé da aula.

## Interromper e continuar (progresso pergunta a pergunta)

Nenhuma sessão precisa ser feita do início ao fim. Em todos os modos — unidade da trilha, lição de vocabulário (partes 1–3 ou completa), prefixos, jogos de terminações, revisão, diagnóstico, flashcards e produção escrita — o aplicativo guarda **onde você parou** depois de cada pergunta e a cada mudança de tela. Fechar a aba, o navegador ou o computador no meio não perde nada.

- **Visão geral → «Continuar de onde parou»** lista as sessões abertas (título, pergunta atual, respostas dadas, há quanto tempo). **Continuar** reabre na mesma tela, com as alternativas na mesma ordem, os itens de reforço ainda na fila e o resumo da sessão intacto. **Descartar** remove só a posição salva.
- Ao iniciar algo que já tem sessão salva, um diálogo oferece **Continuar de onde parou**, **Recomeçar do início** ou **Cancelar**. Recomeçar não apaga respostas: o histórico, o caderno de erros e a revisão espaçada continuam como estão.
- Cartões de unidade e a trilha mostram **▶ Continuar N/Total**; as partes da lição de vocabulário mostram «em andamento».
- Dentro da sessão, **▦ Mapa** abre a grade das perguntas (✓ acertou, ◐ em parte, ✕ errou, … produção aguardando correção, · vista, ↻ volta para recuperar, tracejada = ainda não respondida). Tocar numa pergunta pula direto para ela, e é possível responder fora de ordem. **← Sair** guarda a posição; o indicador «✓ progresso salvo» confirma a gravação.
- **Registro pergunta por pergunta** (na aula de cada unidade e em cada lição de vocabulário) mostra o último resultado de todas as perguntas, quais já estão dominadas e quantas tentativas cada uma teve. Tocar numa pergunta abre a sessão já nela (retomando a sessão salva, se houver).
- Uma sessão termina (e deixa de ser oferecida) quando se chega ao fim da fila; o resumo final continua mostrando a nota da 1ª tentativa.

Implementação: tabela `session_state` em `progress.sqlite3` (módulo `sessions.py`); a fila é guardada só como IDs + ordem das alternativas, e o servidor reconstrói as telas **sem o gabarito** ao retomar. Perguntas que saíram do conteúdo desde a última vez são ignoradas e o ponto de retomada é recalculado. Endpoints: `POST /api/session/save|complete|discard`, `GET /api/session/active|get`, `GET /api/progress/map?scope=unit:<id>|vocab:<id>`. As sessões abertas aparecem também em `exports/relatorio_atual.md`.

## Segurança e privacidade

O servidor escuta somente em `127.0.0.1` por padrão. Todo o histórico permanece nesta pasta. Não há conta, telemetria ou envio para serviços externos.

## Vocabulário (Лексика в диалоге)

O curso russo tem 24 lições, uma por unidade da trilha, com oito construções cada (192 no total). Cada lição começa com um diálogo, apresenta regência e sentido, intercala recuperação, lacunas, compreensão oral e montagem, volta ao diálogo e termina com escrita. O módulo fica disponível independentemente do bloqueio da trilha. Erros reaparecem cerca de cinco telas depois, antes da re-escuta e da escrita, até duas vezes por construção e uma vez por pergunta de diálogo. A nota conta apenas a primeira resposta.

O JSON de `data/vocab_lessons/vNN_*.json` segue a lição-modelo `v01_dativo.json`: `id`, `unit_id`, `order`, `title`, `theme`, `description`, `speakers`, `dialogue` (cenário e 9–12 falas traduzidas), `gist`, oito `items`, `detail`, quatro `reconstruct`, `match` com seis pares, duas `replies` e `writing`. Cada item contém lema, regência, caso, construção, distratores, armadilha, exemplo, lacuna e escuta. IDs gerados são estáveis, com prefixo `vx-vNN-`; tentativas usam `vocab_vNN` e etiquetas `lexeme:` no histórico, caderno e revisão espaçada.

Endpoints: `GET /api/vocab/bootstrap`, `GET /api/vocab/lesson?id=vNN`, `GET /api/vocab/session?id=vNN&part=1|2|3|all`. O endpoint `/api/tts` recebe `voice=f|m|f2|m2`: Svetlana, Dmitry e variações de tom. Os arquivos de áudio ficam em `data/tts_cache`.

```bash
./.venv/bin/python tools/validate_content.py
./.venv/bin/python tools/pregenerate_audio.py --vocab
./.venv/bin/python tools/pregenerate_audio.py --vocab v11 v12 --workers 2
```

A geração exige internet na primeira vez. O comando cobre falas, construções, exemplos, lacunas, escutas, reconstruções e os dois lados das réplicas, com as mesmas vozes e chaves de cache usadas pela interface. Erros de rede são reportados e produzem código de saída 1; arquivos já gerados são reutilizados ao repetir o comando.

## Interface e temas

O tema escuro é o padrão. O seletor no topo oferece **Escuro**, **Claro** e **Sistema**, guarda a escolha em `lingualab-theme` e aplica o tema antes da primeira pintura. O app continua funcionando quando o navegador bloqueia o armazenamento local. Os três cursos têm cores de identidade nos dois temas, com superfícies e textos definidos por tokens.

Nas alternativas, use **1–4** para escolher, **↑/↓** para mover o foco e **Enter** para confirmar ou avançar. Campos de escrita conservam suas teclas normais. O foco é visível, o feedback combina ícone e texto, e a interface respeita redução de movimento. O player indica carregamento, reprodução ou parada e conta apenas audições completas.

Para testar sem tocar no progresso real, use `RUSSO_DB_PATH` e `RUSSO_EXPORT_DIR` apontando para locais temporários. Não use `data/progress.sqlite3` em testes.
