# Visão semântica e Ending Director

A análise em lote do perfil Casamento passa a executar CLIP em frames reais.
A montagem WeddingAssemblyPipeline valida/reutiliza a análise ao reabrir o
projeto, inclusive projetos antigos que ainda não possuem análise semântica.
Os outros perfis continuam com seu fluxo existente.

## Instalação local

No ambiente virtual do TakeDream, instale o PyTorch de CPU e as dependências:

```powershell
python -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements-vision.txt
```

Dependências diretas: PyTorch 2.8.0, Transformers 4.57.6 e Pillow >=10.4,<13.
São separadas de requirements.txt para manter o aplicativo e outros perfis
leves. Gerar a análise semântica de casamento requer essas dependências.
Ausência de dependências, falha de download ou falha de inferência produzem
erro explícito; não há modelo simulado nem tags inventadas como fallback.

O padrão é `openai/clip-vit-base-patch32`, na revisão fixada abaixo, com inferência em CPU. A primeira
execução baixa aproximadamente 600 MB de pesos; depois o Hugging Face usa seu
cache local. GPU não é necessária. O projeto guarda resultados, não os pesos.

Configuração opcional:

```powershell
$env:TAKEDREAM_VISION_MODEL = 'openai/clip-vit-base-patch32'
$env:TAKEDREAM_VISION_DEVICE = 'cpu'
$env:TAKEDREAM_VISION_REVISION = '3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268'
```

Modelos alternativos devem ser compatíveis com CLIPModel/CLIPProcessor.
Fixar a revisão torna a análise reproduzível. `HF_HOME` pode definir a pasta
de pesos. Código remoto de modelos não é executado.

## Dados e cache

`analysis/visual_semantics.json` contém o modelo/configuração, revisão resolvida,
shots identificados por mídia/cena/intervalo, tempos dos frames, tags com scores,
qualidade, roles e embeddings normalizados de 512 dimensões no modelo padrão.
São extraídos dois frames por shot, em 30% e 70% das margens seguras do Motion
Gate. Não há extração/inferência repetida para resultados válidos no cache.

O cache considera caminho, tamanho e mtime do vídeo, intervalo do shot,
modelo/revisão/device, descrições das classes, versão da amostragem/scoring e
os sinais técnicos de qualidade/movimento. Mudanças nesses dados invalidam
o resultado. Escritas são atômicas e concluídas por shot; cancelamento não
marca análise incompleta como concluída nem reduz o status do projeto.

Tags cobrem preparação, cerimônia, casal, festa, detalhes e restrições. Scores
são suporte relativo entre descrições CLIP, **não probabilidades calibradas**.
Não são reconhecimento de identidade, transcrição ou prova de uma ação.
Qualidade combina sinais visuais do modelo e medições existentes de nitidez/
Motion Gate. Shake/whip inferidos em frames isolados são indícios; a passagem
temporal do Motion Gate é a evidência técnica complementar.

## História, repetição e encerramento

Os slots semânticos são opening, preparation, details, anticipation, ceremony,
emotional_peak, couple_hero e closing. Com referência, o diretor já existente
usa esses sinais nas fases correspondentes. Sem referência, slots semânticos
organizam o material. A referência continua ensinando estilo; a lógica de
frases da música nova e o orçamento do projeto continuam controlando timing.

A seleção penaliza tags repetidas, embeddings próximos, mesma mídia/câmera e
trechos temporalmente próximos. Embeddings aproximam composição/assunto;
não identificam com certeza a câmera ou o mesmo momento em câmeras diferentes.

EndingDirector considera closing_score, casal/símbolos, qualidade e duração
segura. Crianças, convidados, celebrante, multidão/decor e movimento ruim são
excluídos do pool seguro quando há alternativa estável com casal/símbolo.
O último shot é reservado antes do corte por duração, não podendo desaparecer
porque o corpo do trailer já atingiu seu orçamento. O bloco final usa um shot
contínuo de até seis segundos, limitado pelo material real e pela última frase
musical quando disponível. Não há congelamento artificial ou novo fade.

Quando só há material inadequado, o plano registra
`ending_director.fallback=true` e `extreme_material_shortage`. Isso é falta de
material/classificação confiável, não inferência visual fabricada.

## Validação e limites conhecidos

```powershell
python -m unittest discover -v
python -m unittest tests.test_visual_semantics tests.test_semantic_story -v
python -m compileall -q app core editor media profiles renderer transcription tests tools
python -m pip check
python tools/smoke_semantic_vision.py caminho/video.mp4 --output .venv/semantic-smoke
```

O smoke é opt-in e executa extração real, modelo real e reuso de cache.
`--duration-ms` aceita uma duração previamente conhecida sem executar FFprobe.
Os testes unitários substituem apenas a camada pesada do modelo/frames; cobrem
persistência, cancelamento, invalidação, status, slots, diversidade, finais ruins,
closing_score e proteção do final contra truncamento.

Na validação deste commit, houve extração real com FFmpeg, inferência CLIP em CPU
e cache verificados no vídeo local de teste com imagem preta. Isso valida o
caminho técnico, não a precisão em casamentos. É necessário avaliar os thresholds
com filmagens reais de casamento: CLIP pode confundir convidados/casal, votos,
ações próximas e grupos com crianças. Não há garantia de classificação perfeita.

Dois testes existentes de integração falharam porque o Controle de Aplicativo
do Windows bloqueou FFprobe (WinError 4551). Não se alterou essa proteção.
O fluxo completo que exige probe/render/export não foi validado neste ambiente.
O fluxo automático de montagem continua sendo o casamento com múltiplas mídias;
a análise em lote pode analisar uma única mídia, mas a edição de fala em arquivo
único mantém seu caminho anterior.

Implementação baseada na documentação oficial:
[CLIP](https://huggingface.co/docs/transformers/v4.57.1/en/model_doc/clip) e
[modelo CLIP ViT-B/32](https://huggingface.co/openai/clip-vit-base-patch32).
