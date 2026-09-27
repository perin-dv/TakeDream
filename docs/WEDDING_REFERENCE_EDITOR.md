# Wedding Reference Editor — requisito central do TakeDream

Este documento registra como requisito de produto o modo **Editar por vídeo de referência**, com foco inicial em casamento.

## Objetivo

Permitir que o usuário forneça:

1. um vídeo de casamento usado como referência de linguagem de edição;
2. os vídeos brutos do novo casamento;
3. uma música diferente da referência;
4. uma duração alvo (ex.: trailer de 3 minutos).

O TakeDream deve analisar a linguagem da referência e gerar uma primeira timeline editada com a mesma lógica narrativa e de ritmo, sem copiar o conteúdo quadro a quadro.

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

## Roadmap técnico

1. Scene Detection — V1 iniciado.
2. Quality Scoring — V1 iniciado.
3. Tracking de pessoas/rostos.
4. Detecção de estabilidade/movimento e enquadramento.
5. Classificador de cenas de casamento.
6. Analisador de música/batidas/energia.
7. Reference Video Analyzer.
8. Wedding Story Builder.
9. Best Shot Selector para grandes lotes de mídia.
10. Montagem automática de trailer/teaser/highlight.
11. Timeline V2 exibindo as decisões do editor automático.

## Princípio

**IA = cérebro; motor = execução.**

A análise decide quais cenas, falas, momentos e ritmos fazem sentido. O renderer/timeline executa essas decisões de forma reproduzível e editável.
