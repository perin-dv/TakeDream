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
