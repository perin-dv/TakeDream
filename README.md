# TakeDream V0.1

Aplicação desktop Python 3.12 / PySide6. Execute a partir da raiz do repositório:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.main
```

FFmpeg **e FFprobe** devem estar instalados no `PATH`. Reinicie o terminal após
instalá-los. A biblioteca PyAV do Whisper não substitui esses executáveis para
extração, análise de vídeo e detecção de silêncios.

## Pipeline de áudio e transcrição

Abra um projeto e clique em **PROCESSAR ÁUDIO E TRANSCREVER**. O processamento
ocorre em `QThread`; os componentes de mídia/transcrição não dependem de Qt.

1. FFprobe confirma que há áudio; FFmpeg extrai a primeira faixa para
   `audio/extracted.wav` (PCM 16-bit, mono, 16 kHz).
2. faster-whisper transcreve com timestamps de segmentos e palavras em
   **milissegundos inteiros**; salva `transcription/transcript.json`.
3. FFmpeg `silencedetect` detecta silêncios de pelo menos 600 ms, com limiar de
   -35 dB; salva `analysis/silences.json`. Constantes em `media/silence_detector.py`.
4. `project.json` recebe os caminhos relativos e o status `transcribed`.

Cada etapa concluída atualiza o projeto (`audio_extracted`, `transcription_ready`,
`transcribed`). Arquivos JSON são publicados por substituição atômica; o WAV é
publicado somente após validação, sem sobrescrever um arquivo existente.
Um lock por projeto impede processamento concorrente entre janelas/instâncias.

Ao reabrir, o programa valida o WAV e os contratos JSON em segundo plano e mostra
os resultados existentes. Clicar novamente executa apenas as etapas ausentes.
Resultados válidos podem ser consultados mesmo sem o vídeo original ou sem
FFmpeg disponível. Não há reprocessamento automático ao mudar a configuração.

Arquivos corrompidos não são sobrescritos: a interface indica o arquivo e pede
que ele seja movido para um backup antes de tentar novamente. Se o WAV se perder,
restaure-o ou mova também os resultados associados antes de gerar novo áudio.
Não substitua manualmente o vídeo/WAV de um projeto já processado; crie um novo
projeto para outra mídia. A versão 0.1 não identifica alterações externas por hash.


## Primeira edição automática

Depois que o projeto possuir `transcription/transcript.json` e
`analysis/silences.json`, a tela libera **GERAR PRIMEIRA EDIÇÃO AUTOMÁTICA**.

A V0.1 ainda não usa IA semântica para decidir cortes. O primeiro planner é
determinístico e seguro:

- perfil `YouTube`;
- estilos `Dinâmico` e `Clean`;
- usa os silêncios detectados pelo FFmpeg;
- mantém uma margem antes/depois da fala;
- ignora pausas pequenas;
- protege o começo e o fim do vídeo;
- gera e valida `decisions/edit_plan.json` antes de renderizar;
- nunca manda um plano inválido diretamente ao FFmpeg.

O estilo **Dinâmico** remove mais pausas; o **Clean** é mais conservador. As regras
ficam em `profiles/youtube.py` e poderão ser substituídas/expandidas posteriormente
por decisões semânticas de IA sem acoplar o motor de renderização.

Fluxo:

```text
transcript.json + silences.json
        ↓
perfil YouTube + estilo
        ↓
decisions/edit_plan.json
        ↓
validador
        ↓
FFmpeg renderer
        ↓
output/video_editado.mp4
```

O renderer mantém somente os segmentos `keep` do plano, concatena áudio/vídeo e
gera H.264/AAC. O processamento ocorre no mesmo worker em background usado pelo
restante do pipeline, portanto a interface continua responsiva.

Nesta fase os cortes são somente por pausas. Erros de fala, repetições, importância,
legendas, zoom, B-roll e análise visual entram em milestones posteriores.

## Revisão na linha do tempo e exportação

Depois que a primeira edição automática termina, o TakeDream abre a tela de
**Revisão**. Ela usa o MP4 renderizado como prévia e mostra a timeline do vídeo
original:

- verde = trecho mantido;
- vermelho = corte automático;
- linha branca = posição atual da reprodução.

O usuário pode clicar em um trecho removido e usar **RESTAURAR CORTE SELECIONADO**.
Essas alterações ficam pendentes até **SALVAR E GERAR NOVA PRÉVIA**. A nova prévia
é renderizada a partir do vídeo original + `edit_plan.json`, evitando recompressões
em cascata.

Nesta primeira versão manual, a revisão permite restaurar cortes inteiros.
Ajuste fino com alças de entrada/saída, divisão de clipes e novos cortes manuais
fica para uma etapa posterior.

A tela também oferece:

- player interno;
- abrir a prévia no player padrão do Windows;
- abrir a pasta do projeto;
- exportação final em `Original`, `1080p`, `720p` ou `480p`.

Os arquivos finais ficam em:

```text
exports/
└── video_final_<perfil>.mp4
```

O export final sempre usa o vídeo original e o plano de edição atual. Se a resolução
escolhida for maior que a origem, o TakeDream mantém a resolução original em vez de
fazer upscale artificial.

## Aceleração de render e progresso

Quando uma etapa precisa recodificar vídeo, o TakeDream tenta automaticamente um
encoder H.264 por hardware antes de usar CPU. A ordem atual é:

1. NVIDIA NVENC;
2. Intel Quick Sync;
3. AMD AMF;
4. fallback seguro para `libx264` na CPU.

Não basta o encoder existir no build do FFmpeg: o TakeDream faz um pequeno teste
real antes de escolhê-lo. Se a GPU falhar durante o vídeo real, a renderização
recomeça automaticamente pela CPU.

As renderizações via FFmpeg também usam `-progress pipe:1`, então a barra passa a
mostrar progresso de 0 a 100 com base na duração estimada do vídeo final. O
cancelamento continua responsivo durante a leitura do progresso.

Exportações `Original` ou sem necessidade de reduzir resolução continuam usando
**Smart Copy** da prévia aprovada, sem recodificar novamente. O `project.json`
registra qual encoder ou modo foi usado na última renderização/exportação.

## Editor V2 e perfis

A revisão possui uma timeline editável antes da exportação final:

- zoom horizontal de 1x a 10x;
- waveform do áudio extraído;
- seleção precisa de trechos;
- dividir no cursor;
- remover/restaurar um trecho;
- marcar entrada/saída e remover um intervalo;
- ajustar início/fim de um corte em passos de 50 ms;
- desfazer/refazer com botões ou `Ctrl+Z` / `Ctrl+Y`;
- várias alterações podem ser acumuladas antes de gerar uma nova prévia.

Perfis registrados:

- YouTube: Dinâmico / Clean;
- Shorts / Reels / TikTok: Dinâmico / Clean;
- Podcast: Conversa / Clean;
- Gaming: Dinâmico / Highlights;
- Curso: Didático / Clean;
- VSL: Conversão / Clean;
- Institucional: Premium / Clean;
- Casamento: Highlight / Cinematográfico.

Todos usam a mesma infraestrutura de projeto, análise, timeline e render. Nesta fase,
os perfis não-YouTube usam regras iniciais de pausa adequadas ao ritmo esperado.
`Casamento` é deliberadamente conservador e não remove silêncio automaticamente;
a lógica de eventos, multicâmera, votos, beijo e seleção de câmera entra em um
milestone especializado.

Projetos novos também guardam orientação e proporção base (`16:9` ou `9:16`).
O perfil vertical já fica preparado para reframing futuro, mas ainda não faz crop
ou tracking automático.

Exportações disponíveis: `Original`, `1080p`, `720p`, `480p` e `360p`.

## Editor V3: formatos, análise de conteúdo e efeitos

O formato é independente do perfil. Todo projeto pode escolher:

- `16:9` horizontal;
- `9:16` vertical;
- `1:1` quadrado;
- `4:5` retrato.

O perfil apenas sugere um formato inicial. O usuário pode trocar o formato na
criação do projeto ou na tela de revisão. O renderer faz crop central + escala sem
esticar a imagem. O reframing inteligente por rosto/objeto ainda não está nesta
versão.

Na revisão, o usuário também pode ativar:

- legendas automáticas `Clean`, `Dinâmica` ou `Impacto`;
- zoom automático baseado nos momentos sugeridos pela análise de conteúdo;
- mudança de formato antes de gerar a nova prévia.

As legendas usam os word timestamps do Whisper, removem palavras que pertencem a
trechos cortados e são convertidas para a timeline editada antes de serem queimadas
no vídeo.

### Análise de conteúdo V1

O botão **ANALISAR CONTEÚDO / IA V1** usa um analisador local e determinístico.
Ele não é apresentado como substituto de um LLM/visão. Nesta fase ele gera:

- hesitações simples (`ah`, `hum`, etc.);
- palavras repetidas em sequência;
- frases consecutivas muito semelhantes;
- sugestões de B-roll por palavras-chave;
- momentos candidatos a punch zoom;
- thumbnails cacheadas para a timeline.

Arquivos gerados:

```text
analysis/
├── content_analysis.json
├── speech_suggestions.json
├── broll_suggestions.json
└── zoom_plan.json

cache/
└── thumbnails/
    ├── manifest.json
    └── thumb_*.jpg
```

Na timeline, os marcadores são:

- laranja: possível problema/repetição de fala;
- azul: sugestão de B-roll;
- roxo: sugestão de zoom.

As sugestões de fala e B-roll são revisáveis. A V3 não remove automaticamente
frases apenas porque o analisador marcou uma possível repetição.

O zoom automático é aplicado no render dividindo apenas os trechos necessários
da timeline e preservando sincronismo de áudio.

A exportação final mantém os perfis de qualidade `Original`, `1080p`, `720p`,
`480p` e `360p`, respeitando o formato salvo na última prévia aprovada.

## Redesign global TakeDream

A interface desktop usa agora um único sistema visual reutilizável em
`app/ui/`, com identidade navy/roxo, cards, sidebar, botões principais,
seletores e estados consistentes.

O redesign cobre:

- Home/dashboard;
- Novo Projeto;
- Projetos;
- workspace de processamento do projeto;
- Revisão;
- Exportações;
- Configurações.

A tela inicial antiga com apenas `Novo Projeto` e `Abrir Projeto` não é mais
a experiência principal.

### Navegação em janela única

O fluxo principal usa uma única janela nativa do TakeDream. Home, Novo Projeto,
workspace, Revisão, Projetos, Exportações e Configurações são páginas internas
trocadas no mesmo shell. O aplicativo não abre uma nova janela para cada etapa.

Somente diálogos pontuais, como seletor de arquivo, confirmação, aviso ou erro,
podem aparecer sobre a janela principal.

### Home

O dashboard mostra:

- ação principal para novo projeto;
- fluxo rápido Transcrever → Cortar → Revisar → Exportar;
- projetos recentes;
- exportações recentes.

### Novo Projeto

A criação do projeto permite escolher visualmente:

- perfil;
- estilo;
- formato `16:9`, `9:16`, `1:1` ou `4:5`;
- qualidade preferida `Original`, `1080p`, `720p`, `480p` ou `360p`;
- legendas automáticas;
- zoom automático;
- preview do vídeo escolhido.

Essas preferências são persistidas no `project.json`.

### Workspace do projeto

O processamento foi reorganizado visualmente em quatro etapas:

1. analisar vídeo;
2. transcrever/analisar áudio;
3. gerar primeira edição;
4. revisar na timeline.

Toda a lógica de processamento continua sendo a mesma; o redesign troca a
experiência visual sem criar mocks de processamento.

## Configuração Whisper

Dependência testada: `faster-whisper==1.2.1`, Python 3.12, CPU/int8 no Windows.
Padrões: modelo `base`, dispositivo `cpu`, computação `int8`, idioma automático.
O primeiro uso baixa o modelo para o cache do Hugging Face e precisa de internet
e espaço em disco. Depois, o modelo em cache pode ser reutilizado.

As variáveis estão documentadas em `.env.example`. Defina-as no ambiente antes de
iniciar a aplicação, por exemplo:

```powershell
$env:TAKEDREAM_WHISPER_MODEL = 'base'
$env:TAKEDREAM_WHISPER_DEVICE = 'cpu'
$env:TAKEDREAM_WHISPER_COMPUTE_TYPE = 'int8'
$env:TAKEDREAM_WHISPER_LANGUAGE = ''
.\.venv\Scripts\python.exe -m app.main
```

O arquivo `.env` não é carregado automaticamente. Para forçar português, use `pt`.
GPU é opcional e não foi validada neste milestone.

## Progresso e interrupção

Extração, análise e download/carregamento exibem progresso indeterminado.
Durante a transcrição, a porcentagem estima a posição temporal do último segmento,
não o tempo restante. O cancelamento encerra FFmpeg/FFprobe e preserva os resultados
concluídos. No Whisper, ele é cooperativo: aguarda o download/carregamento ou a
inferência atual retornar. Fechar a janela solicita cancelamento e aguarda a thread
terminar, mantendo a interface responsiva. Encerramento forçado do processo pode
deixar arquivos temporários, que não são usados como resultados na próxima abertura.

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe -m compileall -q app core editor media profiles renderer transcription tests tools
.\.venv\Scripts\python.exe -m pip check
```

A suíte não baixa modelos nem transcreve vídeos reais. Usa fakes para Whisper,
testa persistência, contratos, erros, cancelamento e o event loop Qt. Os testes
de integração FFmpeg geram tons/silêncio localmente e são ignorados quando os dois
executáveis não estão no `PATH`.

Validação real **opt-in**, com vídeo contendo fala (pode baixar o modelo `base`):

```powershell
.\.venv\Scripts\python.exe -m tools.smoke_transcription 'C:\caminho\video.mp4' --projects-root '.venv\smoke\projects'
```

Esse comando cria um projeto isolado, executa o pipeline pela `ProjectWindow`,
verifica atividade do event loop, reabre o projeto e verifica reutilização sem
alterar os três arquivos. Não faz parte de `unittest discover`.

Documentação dos motores: [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
e [FFmpeg silencedetect](https://ffmpeg.org/ffmpeg-filters.html#silencedetect).
