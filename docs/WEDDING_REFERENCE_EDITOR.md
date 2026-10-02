# Wedding Reference Editor — requisito central do TakeDream

Este documento registra como requisito de produto o modo **Editar por vídeo de referência**, com foco inicial em casamento.

## Objetivo

Permitir que o usuário forneça:

1. um vídeo de casamento usado como referência de linguagem de edição;
2. uma biblioteca inteira de vídeos brutos do novo casamento;
3. uma música diferente da referência;
4. um tipo de entrega e duração alvo.

O TakeDream deve analisar a linguagem da referência e gerar uma primeira timeline editada com a mesma lógica narrativa e de ritmo, sem copiar o conteúdo quadro a quadro.

## Biblioteca de mídia / Media Bin

Projetos de casamento não podem depender de um único arquivo-fonte. O projeto deve aceitar dezenas ou centenas de vídeos vindos de câmeras, drone e pastas diferentes.

A biblioteca usa referências aos arquivos originais; os vídeos grandes não são copiados para dentro do projeto. Isso evita importações lentas e duplicação de dezenas ou centenas de gigabytes.

Cada mídia recebe um fingerprint rápido baseado em caminho, tamanho e data de modificação. Scene Detection e Quality Scoring são armazenados por mídia. Se o arquivo não mudou, a análise é reutilizada em novas entregas.

Exemplo:

```text
CASAMENTO/
├─ CAM01/
├─ CAM02/
├─ DRONE/
├─ MAKING_OF/
├─ CERIMONIA/
├─ CASAL/
└─ FESTA/
```

## Tipos de entrega

O mesmo material bruto pode gerar produtos diferentes sem reanalisar tudo.

### Teaser

- aproximadamente 30–90 segundos;
- padrão inicial: 60 segundos;
- seleção concentrada nos momentos de maior impacto;
- takes mais curtos;
- menos fala;
- festa/casal têm peso proporcional maior.

### Trailer / Highlight

- aproximadamente 2m30–5 minutos;
- padrão inicial: 3m30;
- narrativa emocional;
- votos e falas entram como fio condutor;
- making of, cerimônia, casal e festa formam arco com crescimento e clímax.

### Filme completo

- aproximadamente 15–30 minutos;
- padrão inicial: 20 minutos;
- preserva falas, cerimônia e acontecimentos longos importantes;
- takes médios mais longos;
- prioridade para continuidade narrativa, não apenas melhores imagens isoladas.

### Personalizado

Permite duração definida pelo usuário, mantendo a estratégia adaptativa.

O TakeDream guarda um **story budget** para cada entrega, definindo quanto tempo aproximado deve ser reservado para making of, cerimônia, votos/falas, casal, recepção, festa e encerramento. Assim, mudar de Teaser para Filme não significa apenas esticar a mesma montagem.

## O que aprender da referência

- estrutura narrativa (intro, preparação, cerimônia, casal, festa, encerramento);
- duração média e distribuição dos takes;
- intensidade dos cortes ao longo do vídeo;
- alternância entre fala, B-roll e áudio ambiente;
- momentos de música baixa para entrada de voz;
- uso de slow motion, planos longos e cortes rápidos;
- relação entre mudanças musicais e cortes;
- frequência e tipo de B-roll;
- progressão emocional e clímax.

## O que analisar nos vídeos brutos

- scene detection;
- qualidade técnica de cada take;
- nitidez/desfoque;
- exposição;
- duração útil;
- estabilidade (etapa futura);
- pessoas/rostos e tracking (etapa futura);
- classificação de momentos de casamento;
- duplicidade e takes muito semelhantes;
- presença e qualidade de fala;
- melhores momentos por categoria.

## Classificação de casamento desejada

Exemplos de categorias futuras:

- detalhes / decoração;
- making of da noiva;
- making of do noivo;
- vestido / maquiagem;
- entrada;
- reação do noivo;
- votos;
- alianças;
- beijo;
- saída;
- ensaio do casal;
- recepção;
- brinde / discursos;
- primeira dança;
- convidados;
- festa;
- encerramento.

## Música

A música do novo projeto pode ser diferente da referência. O TakeDream deve analisar a nova faixa para detectar estrutura, energia e pontos de mudança, e adaptar o estilo aprendido da referência aos melhores momentos da nova música.

O objetivo não é reproduzir cortes nos mesmos timestamps, e sim reproduzir a **linguagem da edição**.

## Resultado esperado

Ao final, o TakeDream deve abrir a revisão com uma timeline já montada, contendo vídeo principal, B-roll, falas, música e decisões automáticas visíveis/editáveis pelo usuário.

Uma única biblioteca analisada poderá alimentar várias entregas do mesmo casamento, por exemplo:

```text
Teaser 60s
Trailer 3m30
Filme 22min
```

sem repetir Scene Detection e Quality Scoring nos arquivos que não mudaram.

## Roadmap técnico

1. Media Bin / múltiplas mídias — fundação iniciada.
2. Scene Detection — V1 iniciado.
3. Quality Scoring — V1 iniciado.
4. Análise visual em lote + cache por mídia — fundação iniciada.
5. Tracking de pessoas/rostos.
6. Detecção de estabilidade/movimento e enquadramento.
7. Classificador de cenas de casamento.
8. Analisador de música/batidas/energia.
9. Reference Video Analyzer.
10. Wedding Story Builder usando tipo de entrega e story budget.
11. Best Shot Selector para grandes lotes de mídia.
12. Montagem automática de teaser/trailer/filme.
13. Timeline V2 exibindo as decisões do editor automático.

## Princípio

**IA = cérebro; motor = execução.**

A análise decide quais cenas, falas, momentos e ritmos fazem sentido. O renderer/timeline executa essas decisões de forma reproduzível e editável.
