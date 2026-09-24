# Validação do pipeline de transcrição — TakeDream V0.1

Branch: `feat/transcription-pipeline`. Checkout e `pull --ff-only` concluídos antes
da implementação, partindo de `1d06911fd31c6ec07d6bb83a7573dde2ef490fa8`.
Nenhuma alteração ou merge na `main`.

## Resultado

- 37 testes passaram, sem testes ignorados na execução com FFmpeg no PATH.
- Imports de todos os módulos de `app`, `core`, `media` e `transcription`: OK.
- `app.main.main()` iniciou a janela e o event loop; um timer de teste encerrou
  a aplicação após 500 ms, com código de saída 0.
- `compileall`, `pip check` e revisão do diff: OK.
- Pipeline real pela `ProjectWindow`, com FFmpeg/FFprobe 9.0.2, Python 3.12,
  PySide6 6.11.2, faster-whisper 1.2.1 e CTranslate2 4.8.2: OK.
- Modelo `base`, dispositivo `cpu`, computação `int8`, detecção automática de idioma.
- Vídeo local de 13,883 s contendo fala gerada pelo sintetizador do Windows em inglês:
  idioma `en` (probabilidade 0,9939), 4 segmentos, 25 palavras e 5 silêncios.
- Os arquivos `audio/extracted.wav`, `transcription/transcript.json` e
  `analysis/silences.json` foram criados; `project.json` terminou como `transcribed`.
- No segundo smoke real, um timer de 50 ms registrou 55 eventos durante a execução
  e as verificações. A janela foi reaberta e o processamento solicitado novamente;
  as datas de modificação dos três resultados permaneceram iguais.
- Os testes reais de FFmpeg verificaram silêncio inicial, intermediário, final,
  arquivo inteiramente silencioso e erro em vídeo corrompido.

Os vídeos, ferramentas portáteis, modelo baixado e projetos de teste ficaram em
`.venv/`, ignorado pelo Git. Nenhum modelo ou binário foi adicionado ao repositório.

## Comandos executados

Preparação da branch:

```powershell
git fetch origin feat/transcription-pipeline
git checkout -b feat/transcription-pipeline --track origin/feat/transcription-pipeline
git pull --ff-only origin feat/transcription-pipeline
git status --short --branch
```

Validação final (PATH temporário apenas para esta sessão):

```powershell
$env:PATH = (Join-Path (Get-Location) '.venv\tools\ffmpeg-9.0.2-essentials_build\bin') + ';' + $env:PATH
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe -m compileall -q app core media transcription tests tools
.\.venv\Scripts\python.exe -m pip check
git diff --check

$env:HF_HOME = (Join-Path (Get-Location) '.venv\huggingface')
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -u -m tools.smoke_transcription '.venv\smoke\source.mkv' --projects-root '.venv\smoke\projects'
```

Imports e inicialização foram verificados com este script via stdin do Python:

```python
import importlib
import pkgutil
for name in ('app', 'core', 'media', 'transcription'):
    package = importlib.import_module(name)
    for module in pkgutil.walk_packages(package.__path__, name + '.'):
        importlib.import_module(module.name)
import app.main as entry
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
OriginalWindow = entry.MainWindow
class StartupWindow(OriginalWindow):
    def __init__(self):
        super().__init__()
        QTimer.singleShot(500, QApplication.instance().quit)
entry.MainWindow = StartupWindow
entry.main()
```

## Dependências

Adicionada ao `requirements.txt`: **faster-whisper==1.2.1**, instalada e testada
com inferência real. Suas dependências transitivas são instaladas pelo pip.
As quatro versões PySide6/shiboken6 existentes foram mantidas.
Testes usam `unittest` da biblioteca padrão e PySide6 já existente.
FFmpeg/FFprobe continuam sendo ferramentas externas obrigatórias para processamento
de mídia; não foi alterado o PATH global do computador.

## Limitações

- O primeiro carregamento do modelo exige download. Falhas de download/carregamento
  retornam à interface; não há progresso percentual do download.
- Cancelamento do Whisper aguarda a chamada atual de download/carregamento/inferência
  retornar. Não há encerramento forçado da thread. FFmpeg/FFprobe são canceláveis.
- Timestamps são estimativas do modelo. O smoke de fala usou inglês sintetizado;
  qualidade de transcrição em português, vídeos longos e GPU não foi avaliada.
- Testes Qt de responsividade/reabertura e smoke do pipeline usaram a plataforma
  `offscreen`; a inicialização da janela principal também foi executada separadamente.
- Cache válido é reutilizado. Alterar variáveis de ambiente não reprocessa resultados
  existentes. Arquivos inválidos devem ser movidos para backup para permitir a retomada.
- Alterações externas no vídeo/WAV não são detectadas por hash nesta versão.
- `.env.example` documenta variáveis; não há carregamento automático de `.env`.

## Todos os arquivos criados/modificados

Modificados (4):

- `app/windows/project_window.py`
- `core/project_manager.py`
- `media/ffmpeg_tools.py`
- `requirements.txt`

Criados (21):

- `.env.example`
- `README.md`
- `app/processing_worker.py`
- `core/processing.py`
- `core/results.py`
- `core/storage.py`
- `core/transcription_pipeline.py`
- `docs/transcription-validation.md`
- `media/audio_extractor.py`
- `media/process.py`
- `media/silence_detector.py`
- `tests/__init__.py`
- `tests/helpers.py`
- `tests/test_ffmpeg_integration.py`
- `tests/test_pipeline.py`
- `tests/test_ui.py`
- `tools/__init__.py`
- `tools/smoke_transcription.py`
- `transcription/__init__.py`
- `transcription/base.py`
- `transcription/faster_whisper.py`
