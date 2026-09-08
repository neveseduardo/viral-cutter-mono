"""Human-readable, centralized user-facing messages (job.message).

May be swapped for real i18n in the future; keys live here so the frontend can
map them to locale files.
"""

MESSAGES = {
    "job.ingest.started": "Baixando e normalizando vídeo...",
    "job.ingest.progress": "Ingerindo vídeo ({pct}%)",
    "job.ingest.done": "Vídeo ingerido com sucesso.",
    "job.ingest.failed": "Falha ao ingerir vídeo.",
    "job.transcribe.started": "Transcrevendo áudio...",
    "job.transcribe.progress": "Transcrevendo... ({pct}%)",
    "job.transcribe.done": "Transcrição concluída.",
    "job.transcribe.failed": "Falha na transcrição.",
    "job.analyze.started": "Analisando conteúdo para segmentos virais...",
    "job.analyze.progress": "Analisando ({pct}%)",
    "job.analyze.done": "Segmentos virais identificados.",
    "job.analyze.failed": "Falha na análise de IA.",
    "job.align.started": "Alinhando timestamps dos segmentos...",
    "job.align.done": "Segmentos alinhados.",
    "job.cut.started": "Cortando segmentos...",
    "job.cut.progress": "Cortando segmento {seg} de {total}",
    "job.cut.done": "Cortes concluídos.",
    "job.cut.failed": "Falha ao cortar os segmentos.",
    "job.edit.started": "Enquadrando vídeo 9:16...",
    "job.edit.progress": "Enquadrando segmento {seg} de {total}",
    "job.edit.done": "Vídeos enquadrados.",
    "job.edit.failed": "Falha ao enquadrar os vídeos.",
    "job.subtitles.started": "Gerando legendas dinâmicas...",
    "job.subtitles.done": "Legendas geradas.",
    "job.translate.started": "Traduzindo legendas...",
    "job.translate.done": "Legendas traduzidas.",
    "job.render.started": "Renderizando vídeo final...",
    "job.render.progress": "Renderizando segmento {seg} de {total}",
    "job.render.done": "Renderização concluída.",
    "job.render.failed": "Falha ao renderizar os vídeos.",
}