# LinguaLab · Russo temático

Curso de russo para os níveis intermediário e avançado, organizado por **eixos temáticos**. A página inicial é um fichário de temas (Ciência, Política, Família, Viagem, Trabalho, Economia, Direito, Cultura e outros, 30 ao todo). Cada ficha abre uma gaveta com o progresso do tema por aspecto: verbos, substantivos, adjetivos, advérbios e outras palavras, estruturas gramaticais, expressões e construções. A gaveta mostra também a aula temática do eixo, o vocabulário por nível e as aulas de gramática ligadas ao tema.

Dentro de cada tema há dois modos:

- **Estudar**: apresenta palavras e construções ainda não vistas, na ordem de utilidade (frequência de uso), com áudio, tradução, gênero ou aspecto e a tabela de declinação ou conjugação. Em seguida vêm os exercícios de significado (russo → português e português → russo), de forma (caso, conjugação, concordância) e de estrutura.
- **Revisar**: revisão espaçada do que já foi estudado no tema. Um erro volta em cerca de dez minutos; os acertos avançam por intervalos de 1, 3, 7, 14, 30, 60, 120 e 240 dias, e o estágio sobe no máximo uma vez por dia. Um item conta como **dominado** depois de sobreviver às revisões de 7 e 14 dias.

O vocabulário é filtrado por nível mínimo (B1 por padrão; A2 a C2 nas preferências). Os níveis são estimados pela posição na lista de utilidade: até 1.200 (A2), 3.500 (B1), 8.000 (B2), 16.000 (C1) e o restante (C2).

## As aulas temáticas

Além dos dois modos, cada tema (exceto «Geral») tem uma **aula temática** completa, mostrada no topo da gaveta. São 29 aulas, de 50 a 60 minutos cada, em `data/lessons/*.json`, e todo o conteúdo delas pertence ao tema da aula. Cada aula tem cinco partes, que podem ser feitas separadamente:

1. **Vocabulário em contexto**: aquecimento com perguntas, apresentação de doze palavras e expressões com áudio e nota de uso, recuperação ativa (russo → português e português → russo), associação de pares e interpretação de frases no contexto.
2. **Escuta**: diálogo gravado com duas vozes, perguntas de compreensão, transcrição com tradução opcional, ditado corrigido palavra por palavra e sombreamento (*shadowing*) com gravação da própria voz.
3. **Leitura**: texto autêntico no gênero do tema (notícia, crítica, blog, texto de divulgação), questões de verdadeiro, falso ou não informado, perguntas em russo e exercício de lacunas sobre o próprio texto.
4. **Foco na forma**: um ponto gramatical ligado ao tema (por exemplo, particípios em Sociedade, voz passiva em Direito, aspecto verbal na narração em Guerra, discurso indireto em Mídia), com quadro explicativo, exemplos, armadilhas para falantes de português, múltipla escolha, correção de erros e montagem de frases.
5. **Uso real**: escuta de um gênero autêntico (aviso de estação, boletim de rádio, previsão do tempo, mensagem de voz, audioguia, menu telefônico), situações comunicativas e produção escrita e oral guiadas, com expressões úteis, texto modelo com tradução e lista de autoavaliação.

Os itens corrigíveis das aulas entram no progresso do tema nos aspectos **Expressões**, **Estruturas**, **Leitura**, **Escuta** e **Produção**, e os já vistos voltam no modo **Revisar** pela mesma revisão espaçada. A produção livre e o sombreamento não entram na revisão, porque dependem da autoavaliação.

## O curso de francês (B1 → C1)

O seletor **Русский | Français** no topo abre a página própria do curso de francês. O texto-base pedagógico, com método, fontes, trilha, erros e eixos, está na pasta `curso-frances/`, fora deste repositório. Aqui fica só a parte executável:

- **Trilha gramatical:** 42 unidades em três fases (Consolidar, Argumentar, Refinar) e 2 unidades extras (falsos cognatos; carta formal). Cada unidade tem a regra com exemplos e armadilhas para lusófonos e de 9 a 14 exercícios.
- **Dois modos por unidade:**
  - **Aprender**: regra seguida de exercícios, do reconhecimento à produção.
  - **Desafio**: todos os itens, sem aula. Dá até 3 estrelas pelo acerto de primeira, calculado no servidor.
- **Tipos de exercício:** múltipla escolha, lacuna digitada, caça ao erro (localizar e corrigir), montagem com uma palavra intrusa, transformação, pares, registro (familiar, neutro ou formal) e ditado. Há um teclado de acentos em todos os campos.
- **Eixos temáticos:** 28 eixos com 560 palavras e expressões, sempre com artigo, exemplo, tradução e áudio. Os exercícios são gerados: sentido, francês a partir do português, gênero, escuta, escrita com artigo e lacuna no exemplo.
- **Verbos:** 63 verbos prioritários, conjugados por `french.conjugate()` a partir do presente, do radical do futuro e do particípio. O **sprint** dá 90 segundos contra o relógio, e o recorde é contado no servidor.
- **Sem punição:**
  - Um erro abre a escada de ajuda (sinal → pista → resposta) e permite tentar de novo.
  - O acerto com ajuda vale menos XP, mas vale, e o XP nunca diminui.
  - O item errado volta algumas telas depois; recuperá-lo rende +5 XP.
  - Na revisão espaçada, o erro recua um só estágio, e o item recupera depressa o melhor estágio que já tinha alcançado.
- **Caderno de erros:** cada resposta é classificada em uma de dez categorias, de G1 (determinantes) a O (ortografia). O caderno mostra os cinco pontos fracos dos últimos 30 dias e permite treinar cada categoria.
- **Jogo:** XP, níveis com títulos (*Flâneur* → *Immortel*), meta diária, sequência de dias, fôlego dentro da sessão e conquistas.

Código e dados: `french.py` (motor, progresso nas tabelas `fr_*` do mesmo banco, rotas `/api/fr/*`), `static/french.js` e `static/french.css` (página), `data/fr/` (unidades, eixos e verbos). Formato do conteúdo e validação:

```powershell
python tools/validate_french.py
```

O áudio usa as vozes francesas do Edge (`fr-FR-DeniseNeural`). Sem internet, usa a voz francesa do Windows, se estiver instalada.

## O curso de cazaque (A1 → B1)

O botão **Қазақша** no seletor de cursos abre um curso de 40 aulas, do som das letras ao B1, para quem fala português. O plano pedagógico, com as fontes analisadas, fica na pasta `curso-cazaque/`, fora deste repositório.

- **Sequencial:** a trilha é um mapa, e cada aula abre quando a anterior é concluída, isto é, quando todos os exercícios dela foram respondidos. O **modo livre** (em "meta e modo livre") abre tudo de uma vez.
- **Módulos:**
  - Әліппе, aulas 1 a 6: o alfabeto, as vogais duras e brandas, қ e ғ, ң e һ, a harmonia vocálica, a assimilação e os números.
  - A1, aulas 7 a 20: pronomes, terminações de pessoa, perguntas, possessivos, casos locativo, dativo e ablativo, presente, imperativo, «quero» e passado.
  - A2, aulas 21 a 32: genitivo, acusativo, instrumental, futuro, comparação, posposições, «poder» e «dever», perfeito, votos e condicional.
  - B1, aulas 33 a 40: converbos e verbos compostos, particípios, vozes, orações complexas, discurso relatado, registro formal, uma leitura sobre o Cazaquistão e outra sobre Abai e os provérbios.
- **Cada aula** tem:
  - explicação com narração em português;
  - quadro de sons nas aulas 1 a 6;
  - de 12 a 13 palavras com áudio e um treino rápido de reconhecimento;
  - diálogo em duas vozes (Aigul e Daulet), que pode ser tocado inteiro ou fala por fala;
  - texto de leitura nas aulas 39 e 40;
  - de 11 a 14 exercícios: escolha, escuta, pares, montar a frase com uma palavra intrusa, lacuna, escrita, transformação e ditado.
- **Desafio:** todos os exercícios da aula, sem a explicação. Dá até 3 estrelas.
- **Sem punição:** o curso segue as mesmas regras do francês (escada de pistas, XP que nunca diminui, item errado que volta e revisão espaçada). Quando o aluno escreve uma letra russa no lugar da cazaque (к/қ, у/ү/ұ, и/і…), recebe uma pista específica em vez de um "errado". Um teclado com ә ғ қ ң ө ұ ү һ і aparece em todos os campos.
- **Alfabeto:** as 42 letras, com as 9 próprias do cazaque em destaque e uma palavra para ouvir em cada uma.

Código e dados: `kazakh.py` (motor; progresso nas tabelas `kz_*` do mesmo banco; rotas `/api/kz/*`), `static/kazakh.js` e `static/kazakh.css` (página; os exercícios usam o executor de sessão de `french.js`), `data/kz/lessons/*.json` (aulas). Para validar:

```powershell
python tools/validate_kazakh.py
```

O áudio usa as vozes cazaques do Edge (`kk-KZ-AigulNeural` e `kk-KZ-DauletNeural`), e a narração usa a voz `pt-BR-ThalitaMultilingualNeural`. O Windows não tem voz cazaque instalada, então sem internet só tocam os áudios que já estão no cache. Para gerar o curso inteiro de uma vez (cerca de 1.050 áudios):

```powershell
.venv\Scripts\python tools\pregenerate_kazakh_audio.py
```

## Executar a partir do código

No Windows, com Python 3.10 ou mais recente:

```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python app.py
```

Opções: `--browser` abre no navegador em vez da janela própria; `--port 8777` muda a porta; `--data-dir <pasta>` grava o progresso em outra pasta (útil para testar sem tocar no progresso do aplicativo instalado). Na primeira abertura, a base lexical é descompactada para `<pasta de dados>/data/cache` e o índice de formas do dicionário é montado em segundo plano.

## A base lexical

`data/lexicon.sqlite3.gz` contém **todos os 58.825 verbetes do OpenRussian**, com acento, formas flexionadas, gênero, aspecto e par aspectual. Ela é gerada por `tools/build_lexicon.py` a partir de:

| Fonte | Uso | Licença |
|---|---|---|
| OpenRussian (Badestrand/russian-dictionary) | lemas, acento, formas, gênero, aspecto | CC BY-SA 4.0 |
| FrequencyWords (Hermit Dave, OpenSubtitles 2018) | frequência de cada forma, somada por lema | CC BY-SA 4.0 |
| Tabelas de tradução do Wiktionary (Open DSL Dictionary Project) | russo ↔ português pela mesma acepção inglesa; expressões | CC BY-SA 3.0 |
| Princeton WordNet 3.0 e OpenWN-PT | hierarquia semântica para os temas; traduções de reserva | WordNet License; CC BY-SA |

**Prioridade por utilidade.** A posição de cada palavra combina duas opiniões: a frequência na fala (legendas) e a posição que o OpenRussian lhe dá na sua classe gramatical, vinda de um corpus geral. A média geométrica das duas impede que o vocabulário de seriado passe à frente do vocabulário de jornal e de livro.

**Temas não excludentes.** Cada palavra recebe até três temas. A classificação automática soma sinais de quatro origens: a hierarquia do WordNet (a palavra entra em Saúde se o sentido descende de *disease*, *body part*, *medicine*…), os domínios temáticos do WordNet, os radicais-chave em inglês definidos em `data/themes.json` e a herança pela raiz russa (учительница herda o tema de учитель). Palavras gramaticais e muito frequentes formam o eixo **Essencial**; o que não tem sinal temático vai para **Outras palavras**.

**Curadoria.** `data/curation/core_lexicon.tsv` traz a tradução em português do Brasil e os temas revistos à mão para as palavras mais úteis (hoje, as primeiras 4.750 da lista, até o meio do nível B2). Essa revisão tem prioridade sobre tudo o que é automático. Abaixo dessa faixa, tradução e temas são automáticos. Para ampliar a revisão, acrescente linhas ao arquivo (`lema<TAB>classe<TAB>tradução; tradução<TAB>tema,tema`, com `x` para tirar o verbete das sessões) e reconstrua:

```powershell
pip install nltk
python tools/build_lexicon.py
python tools/validate_content.py
```

Ficam fora das sessões (mas continuam no dicionário): nomes próprios, palavrões e verbetes sem tradução para o português.

**Conteúdo reaproveitado.** Os exercícios de gramática das antigas unidades (`data/units`), o módulo de verbos com prefixo (`data/prefix_verbs.json`) e as 192 construções das lições de vocabulário (`data/vocab_lessons`) são distribuídos pelos temas conforme o vocabulário que usam, e aparecem como **Estruturas** e **Expressões e construções**. As aulas narradas dessas unidades ficam ligadas aos temas na gaveta.

## Onde ficam os dados do aluno

- `data/lingualab.sqlite3`: estado de cada item (estágio da revisão espaçada, próxima revisão, acertos e erros), todas as respostas e as preferências;
- `data/tts_cache`: áudios gerados (voz russa do Edge; no Windows, sem internet, a voz russa instalada no sistema).

No aplicativo instalado, essa pasta é `%APPDATA%\RussoTrainer`. O progresso das versões anteriores (`progress.sqlite3`) não é usado pelo curso temático.

## Segurança e privacidade

O servidor escuta somente em `127.0.0.1`. Não há conta, telemetria ou envio de dados; a internet só é usada para gerar áudio e verificar atualizações.

## Publicar uma nova versão

Os releases são gerados pelo GitHub Actions (`.github/workflows/release.yml`). Quando uma tag `vX.Y.Z` chega ao GitHub, o workflow valida o conteúdo, gera o dicionário OpenRussian, compila o `.exe` com PyInstaller num servidor Windows e publica `RussoTrainer-vX.Y.Z-windows.zip` como release. O atualizador do app encontra esse arquivo e oferece a atualização.

O jeito mais simples é o `publicar_alteracoes.bat` (fora do repositório, na pasta acima): ele faz o commit, pergunta se é uma nova versão e, nesse caso, atualiza `APP_VERSION` com `packaging/bump_version.ps1`, cria a tag e envia tudo. Manualmente:

```powershell
powershell -File packaging\bump_version.ps1 -Version 1.6.1
git commit -am "v1.6.1: descrição"
git tag -a v1.6.1 -m "descrição"
git push origin main --follow-tags
```

A tag precisa coincidir com `APP_VERSION`; caso contrário, o workflow para sem publicar. Um release também pode ser refeito na aba **Actions** (botão *Run workflow*, informando a tag).
