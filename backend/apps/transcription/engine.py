"""Transcription engines (AGENTS.md §7.2).

WhisperX is the preferred engine (whisper + forced alignment → word timestamps).
If it is not installed the pipeline falls back to plain `openai-whisper`; if
neither is available a clear, actionable error is raised (degradation, §5.4).
YouTube official subtitles can be used as a fast source (source=youtube_subs).
"""

import gc
import logging
import re

logger = logging.getLogger(__name__)


def _apply_safe_globals_hack():
    """Compat shim for PyTorch >= 2.4 + WhisperX (weights_only / omegaconf)."""
    try:
        import torch

        original_load = torch.load

        def safe_load(*args, **kwargs):
            kwargs["weights_only"] = False
            return original_load(*args, **kwargs)

        torch.load = safe_load
    except ImportError:
        pass


def transcribe_whisperx(audio_path: str, model_name: str, device: str, progress_cb=None) -> dict:
    import whisperx

    _apply_safe_globals_hack()
    compute_type = "float16" if device == "cuda" else "float32"
    if progress_cb:
        progress_cb(15, "Carregando modelo de transcrição...")

    audio = whisperx.load_audio(audio_path)
    model = whisperx.load_model(model_name, device, compute_type=compute_type)
    if progress_cb:
        progress_cb(30, "Transcrevendo áudio...")
    result = model.transcribe(audio, batch_size=16, chunk_size=10)
    language = result.get("language", "pt")

    if progress_cb:
        progress_cb(70, "Alinhando timestamps por palavra...")

    model_a, metadata = whisperx.load_align_model(language_code=language, device=device)
    aligned = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)
    result["segments"] = aligned["segments"]

    for m in (model, model_a):
        try:
            del m
        except Exception:
            pass
    gc.collect()
    if device == "cuda":
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception:
            pass

    if progress_cb:
        progress_cb(90, "Formatando resultados...")

    # Normalise segment structure to match the canonical schema (§8.1):
    # ensure each segment has an "id" and words have the expected fields.
    normalised = []
    for i, seg in enumerate(result["segments"]):
        words = []
        for w in seg.get("words") or []:
            words.append({
                "word": str(w.get("word", "")).strip(),
                "start": round(float(w.get("start", 0)), 3),
                "end": round(float(w.get("end", 0)), 3),
                "score": round(float(w.get("score", 0.0)), 3),
            })
        normalised.append({
            "id": i,
            "start": round(float(seg.get("start", 0)), 3),
            "end": round(float(seg.get("end", 0)), 3),
            "text": seg.get("text", "").strip(),
            "words": words,
        })

    return {"language": language, "segments": normalised}


def transcribe_whisper(audio_path: str, model_name: str, device: str, progress_cb=None) -> dict:
    import threading
    import time

    import whisper

    if progress_cb:
        progress_cb(15, "Carregando modelo de transcrição...")
    model = whisper.load_model(model_name, device=device)

    # openai-whisper não expõe progresso por segmento. Rodamos um heartbeat
    # em background para manter a UI viva durante a transcrição bloqueante.
    _result_holder: dict = {}
    _done = threading.Event()

    def _heartbeat():
        msgs = [
            "Transcrevendo áudio...",
            "Processando fala...",
            "Identificando palavras...",
            "Quase lá...",
        ]
        step = 0
        # progresso sintético entre 36% e 90% durante a transcrição
        prog = 36
        while not _done.wait(timeout=8.0):
            if progress_cb:
                progress_cb(min(prog, 90), msgs[step % len(msgs)])
            prog = min(prog + 6, 90)
            step += 1

    def _run_transcribe():
        _result_holder["result"] = model.transcribe(
            audio_path, word_timestamps=True, fp16=(device == "cuda")
        )
        _done.set()

    t_heartbeat = threading.Thread(target=_heartbeat, daemon=True)
    t_transcribe = threading.Thread(target=_run_transcribe, daemon=True)
    t_heartbeat.start()
    t_transcribe.start()
    t_transcribe.join()
    _done.set()  # garante que o heartbeat pare mesmo em caso de exceção
    t_heartbeat.join(timeout=2)

    result = _result_holder.get("result")
    if result is None:
        raise RuntimeError("Transcrição não produziu resultado.")

    language = result.get("language", "pt")
    segments = []
    for seg in result.get("segments", []):
        words = []
        for w in seg.get("words", []) or []:
            words.append({
                "word": w["word"].strip(),
                "start": round(w["start"], 3),
                "end": round(w["end"], 3),
                "score": round(w.get("probability", 0.0), 3),
            })
        segments.append({
            "id": len(segments),
            "start": round(seg["start"], 3),
            "end": round(seg["end"], 3),
            "text": seg["text"].strip(),
            "words": words,
        })
    if progress_cb:
        progress_cb(95, "Formatando resultados...")
    return {"language": language, "segments": segments}


def has_whisperx() -> bool:
    try:
        import whisperx  # noqa: F401

        return True
    except ImportError:
        return False


def has_whisper() -> bool:
    try:
        import whisper  # noqa: F401

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# YouTube official subtitles as transcript source
# ---------------------------------------------------------------------------


def _time_to_seconds(t_str: str) -> float:
    t_str = t_str.strip().replace(",", ".")
    parts = t_str.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(t_str or 0)


def parse_srt_file(path: str) -> list[dict]:
    """srt → [{'start', 'end', 'text'}]."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().replace("\r\n", "\n")
    blocks = content.strip().split("\n\n")
    out = []
    for block in blocks:
        lines = block.split("\n")
        for i, line in enumerate(lines):
            if "-->" in line:
                start_s, end_s = line.split("-->")
                text = " ".join(lines[i + 1:]).strip()
                text = re.sub(r"<[^>]+>", "", text)
                if text:
                    out.append({
                        "start": _time_to_seconds(start_s),
                        "end": _time_to_seconds(end_s.split(" ")[0]),
                        "text": text,
                    })
                break
    return out


def parse_vtt_or_srt(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        head = f.read(256)
    if "WEBVTT" in head:
        return parse_vtt_file(path)
    return parse_srt_file(path)


def parse_vtt_file(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f]
    out = []
    current = {}
    for line in lines:
        if not line:
            if "start" in current and current.get("text"):
                current["text"] = re.sub(r"<[^>]+>", "", " ".join(current["text"]))
                current["text"] = re.sub(r"&[^;]+;", "", current["text"]).strip()
                if current["text"]:
                    out.append(current)
            current = {}
            continue
        if line.startswith("WEBVTT") or line.startswith("X-TIMESTAMP") or line.startswith("NOTE"):
            continue
        if "-->" in line:
            start_s, rest = line.split("-->")
            current["start"] = _time_to_seconds(start_s)
            current["end"] = _time_to_seconds(rest.split(" ")[0])
            current["text"] = []
        elif current.get("start") is not None:
            current.setdefault("text", []).append(line)
    if "start" in current and current.get("text"):
        out.append({
            "start": current["start"],
            "end": current["end"],
            "text": " ".join(current["text"]).strip(),
        })
    return out


def youtube_subs_to_transcript(srt_path: str, language: str = "pt") -> dict:
    """Converts an SRT/VTT into the canonical transcript (word-level estimates)."""
    raw = parse_vtt_or_srt(srt_path)
    segments = []
    for i, seg in enumerate(raw):
        text = seg["text"]
        words = [w for w in re.split(r"\s+", text) if w]
        duration = max(seg["end"] - seg["start"], 0.001)
        per = duration / max(len(words), 1)
        word_items = []
        for j, w in enumerate(words):
            word_items.append({
                "word": w,
                "start": round(seg["start"] + j * per, 3),
                "end": round(seg["start"] + (j + 1) * per, 3),
                "score": 1.0,
            })
        segments.append({
            "id": i,
            "start": round(seg["start"], 3),
            "end": round(seg["end"], 3),
            "text": text,
            "words": word_items,
        })
    return {"language": language, "segments": segments}