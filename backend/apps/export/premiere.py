"""Premiere Pro XML export (FCP7-compatible, 🎁 bônus §7.12).

Repositions the source clip to approximate the 9:16 crop as Scale/Position,
with keyframes when a face timeline exists. Known limitation: split-screen is
not represented (documented bug in the spec).
"""

import xml.etree.ElementTree as ET
from pathlib import Path

TIME_BASE = 30  # timecode 29.97 ≈ 30000/1001


def _frames(seconds: float) -> int:
    return int(round(seconds * TIME_BASE))


def _tc(seconds: float) -> str:
    total_frames = _frames(seconds)
    hh = total_frames // (TIME_BASE * 3600)
    mm = (total_frames // (TIME_BASE * 60)) % 60
    ss = (total_frames // TIME_BASE) % 60
    ff = total_frames % TIME_BASE
    return f"{hh:02}:{mm:02}:{ss:02}:{ff:02}"


def build_premiere_xml(*, video_path: str, duration: float, start_offset: float,
                       source_width: int, source_height: int,
                       timeline: dict | None = None,
                       vertical_width: int = 1080, vertical_height: int = 1920) -> bytes:
    """Builds an FCP7 XML approximating the crop as scale/position keyframes."""
    root = ET.Element("xmeml", version="5")
    sequence = ET.SubElement(root, "sequence")
    ET.SubElement(sequence, "name").text = "ViralCutter Segment"
    ET.SubElement(sequence, "duration").text = str(_frames(duration))
    ET.SubElement(sequence, "rate").text = str(TIME_BASE)
    ET.SubElement(sequence, "in").text = "0"
    ET.SubElement(sequence, "out").text = str(_frames(duration))

    timecode = ET.SubElement(sequence, "timecode")
    ET.SubElement(timecode, "rate").text = str(TIME_BASE)
    ET.SubElement(timecode, "string").text = "00:00:00:00"

    media = ET.SubElement(sequence, "media")
    video = ET.SubElement(media, "video")
    fmt = ET.SubElement(ET.SubElement(video, "format"), "samplecharacteristics")
    ET.SubElement(fmt, "width").text = str(vertical_width)
    ET.SubElement(fmt, "height").text = str(vertical_height)
    ET.SubElement(fmt, "rate").text = str(TIME_BASE)

    track = ET.SubElement(video, "track")
    clipitem = ET.SubElement(track, "clipitem")
    ET.SubElement(clipitem, "name").text = Path(video_path).name
    ET.SubElement(clipitem, "enabled").text = "TRUE"
    ET.SubElement(clipitem, "in").text = "0"
    ET.SubElement(clipitem, "out").text = str(_frames(duration))
    ET.SubElement(clipitem, "start").text = "0"
    ET.SubElement(clipitem, "end").text = str(_frames(duration))
    ET.SubElement(clipitem, "rate").text = str(TIME_BASE)

    _add_filters(clipitem, source_width, source_height, duration,
                 vertical_width, vertical_height, timeline, start_offset)

    file_ref = ET.SubElement(ET.SubElement(clipitem, "file"), "file")
    ET.SubElement(file_ref, "pathurl").text = f"file://localhost/viralcutter/{video_path}"

    ET.SubElement(sequence, "audio").tag = "audio"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _add_filters(clipitem, src_w, src_h, duration, out_w, out_h, timeline, start_offset):
    motion = ET.SubElement(clipitem, "motion")
    # scale to cover 9:16 (from a center crop)
    cover_scale = max(out_w / src_w, out_h / src_h) * 100.0

    def _channel(tag, value):
        c = ET.SubElement(motion, tag)
        ET.SubElement(c, "value").text = str(value)
        return c

    _channel("scale", f"{cover_scale:.6f}")

    if timeline and timeline.get("frames"):
        frames = [f for f in timeline["frames"] if f.get("center") is not None]
        if frames:
            # map source center → offset relative to center crop (already scaled)
            scale = cover_scale / 100.0
            cx_range = (src_w - (out_w / scale)) / 2
            cy_range = (src_h - (out_h / scale)) / 2
            # keyframe center on "scale" of the centered crop
            pos = ET.SubElement(motion, "center")
            for frame in frames:
                kf = ET.SubElement(pos, "keyframe")
                ET.SubElement(kf, "when").text = str(max(0, _frames(frame["t"] - start_offset)))
                x, y = frame["center"]
                dx = (x - src_w / 2) / cx_range if cx_range else 0
                dy = (y - src_h / 2) / cy_range if cy_range else 0
                ET.SubElement(kf, "xoffset").text = f"{dx * cover_scale:.6f}"
                ET.SubElement(kf, "yoffset").text = f"{dy * cover_scale:.6f}"


def export_zip(project_id: int, segment_index: int, *, items: list[tuple[str, bytes]]) -> bytes:
    """Packages XML + sidecar data into a .zip (used by export task)."""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in items:
            zf.writestr(name, data)
    return buffer.getvalue()