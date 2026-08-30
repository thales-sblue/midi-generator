"""Isolated, reproducible runner for the SkyTNT midi-model POC.

This module is intentionally outside ``src`` and has no relationship with the
application runtime. Run it with the dedicated environment documented in
``docs/POC_SKYTNT.md``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

import mido
import numpy as np
import psutil
import torch
from safetensors.torch import load_file


CODE_REVISION = "f504d5cb58f769ab0f2909c679238f6621034573"
MODEL_REVISION = "0f8f265d4330f4e46527ac2313200254c5757f5f"
MODEL_SHA256 = "82ac8b2217f8f66f79737e444fe60c686d3cbfee54b0c8ef717f701213bbbb83"
MODEL_SIZE_BYTES = 467_701_064
DEFAULT_BPM = 120
DEFAULT_TEMPERATURE = 1.0
DEFAULT_TOP_P = 0.98
DEFAULT_TOP_K = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        choices=("scratch", "prompt", "multitrack"),
        required=True,
    )
    parser.add_argument("--device", choices=("cuda", "cpu"), required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-new-events", type=int, default=32)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--top-p", type=float, default=DEFAULT_TOP_P)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--workspace", type=Path, default=Path("output/poc_skytnt"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    workspace = args.workspace.resolve()
    upstream = workspace / "upstream"
    model_dir = workspace / "model"
    output_dir = workspace / "runs" / args.run_id
    output_dir.mkdir(parents=True, exist_ok=False)

    cache_dir = workspace / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(cache_dir)
    os.environ["TRANSFORMERS_CACHE"] = str(cache_dir / "transformers")

    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available.")
    if args.max_new_events < 1:
        raise ValueError("max-new-events must be positive.")

    sys.path.insert(0, str(upstream))
    import MIDI  # type: ignore[import-not-found]
    from midi_model import MIDIModel, MIDIModelConfig  # type: ignore[import-not-found]

    process = psutil.Process()
    initial_rss = process.memory_info().rss
    if args.device == "cuda":
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

    load_started = time.perf_counter()
    config = MIDIModelConfig.from_json_file(model_dir / "config.json")
    model = MIDIModel(config=config)
    state_dict = load_file(model_dir / "model.safetensors", device="cpu")
    incompatible = model.load_state_dict(state_dict, strict=False)
    dtype = torch.bfloat16 if args.device == "cuda" else torch.float32
    model.to(args.device, dtype=dtype).eval()
    load_seconds = time.perf_counter() - load_started
    rss_after_load = process.memory_info().rss

    prompt_bytes = build_prompt_midi(args.case)
    prompt_path = None
    if prompt_bytes is None:
        prompt = build_scratch_tokens(model.tokenizer)
    else:
        prompt_path = output_dir / "prompt.mid"
        prompt_path.write_bytes(prompt_bytes)
        prompt = model.tokenizer.tokenize(MIDI.midi2score(prompt_bytes))
    prompt_array = np.asarray(prompt, dtype=np.int64)

    generator = torch.Generator(args.device).manual_seed(args.seed)
    generation_started = time.perf_counter()
    generated = model.generate(
        prompt=prompt_array,
        batch_size=1,
        max_len=len(prompt_array) + args.max_new_events,
        temp=args.temperature,
        top_p=args.top_p,
        top_k=args.top_k,
        generator=generator,
    )[0]
    if args.device == "cuda":
        torch.cuda.synchronize()
    generation_seconds = time.perf_counter() - generation_started

    score = model.tokenizer.detokenize(generated)
    midi_bytes = MIDI.score2midi(score)
    midi_path = output_dir / "generated.mid"
    midi_path.write_bytes(midi_bytes)
    analysis = analyze_midi(midi_bytes)
    event_hash = hashlib.sha256(generated.tobytes()).hexdigest()

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "case": args.case,
        "run_id": args.run_id,
        "device": args.device,
        "offline": args.offline,
        "seed": args.seed,
        "parameters": {
            "bpm": DEFAULT_BPM,
            "time_signature": "4/4",
            "key_signature": "C major",
            "temperature": args.temperature,
            "top_p": args.top_p,
            "top_k": args.top_k,
            "batch_size": 1,
            "max_new_events": args.max_new_events,
        },
        "provenance": {
            "code_repository": "https://github.com/SkyTNT/midi-model",
            "code_revision": CODE_REVISION,
            "code_license": "Apache-2.0",
            "model_repository": "https://huggingface.co/skytnt/midi-model-tv2o-medium",
            "model_revision": MODEL_REVISION,
            "model_sha256": MODEL_SHA256,
            "model_size_bytes": MODEL_SIZE_BYTES,
            "model_license": "Apache-2.0",
            "declared_datasets": [
                "projectlosangeles/Los-Angeles-MIDI-Dataset",
                "projectlosangeles/Monster-MIDI-Dataset",
                "SymphonyNet MIDI Dataset",
            ],
            "remote_inference_used": False,
        },
        "environment": environment_manifest(args.device),
        "measurements": {
            "model_load_seconds": round(load_seconds, 3),
            "generation_seconds": round(generation_seconds, 3),
            "rss_initial_bytes": initial_rss,
            "rss_after_load_bytes": rss_after_load,
            "rss_after_generation_bytes": process.memory_info().rss,
            "cuda_peak_allocated_bytes": (
                torch.cuda.max_memory_allocated() if args.device == "cuda" else None
            ),
            "cuda_peak_reserved_bytes": (
                torch.cuda.max_memory_reserved() if args.device == "cuda" else None
            ),
        },
        "model_load": {
            "missing_keys": list(incompatible.missing_keys),
            "unexpected_keys": list(incompatible.unexpected_keys),
        },
        "prompt": {
            "path": prompt_path.name if prompt_path else None,
            "sha256": hashlib.sha256(prompt_bytes).hexdigest() if prompt_bytes else None,
            "event_count": len(prompt_array),
            "prefix_preserved": bool(
                np.array_equal(generated[: len(prompt_array)], prompt_array)
            ),
        },
        "result": {
            "midi_path": midi_path.name,
            "midi_sha256": hashlib.sha256(midi_bytes).hexdigest(),
            "token_event_sha256": event_hash,
            "token_event_count": len(generated),
            **analysis,
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


def build_scratch_tokens(tokenizer: Any) -> list[list[int]]:
    events = [
        [tokenizer.bos_id] + [tokenizer.pad_id] * (tokenizer.max_token_seq - 1),
        tokenizer.event2tokens(["time_signature", 0, 0, 0, 3, 1]),
        tokenizer.event2tokens(["key_signature", 0, 0, 0, 7, 0]),
        tokenizer.event2tokens(["set_tempo", 0, 0, 0, DEFAULT_BPM]),
        tokenizer.event2tokens(["patch_change", 0, 0, 1, 0, 0]),
        tokenizer.event2tokens(["patch_change", 0, 0, 2, 1, 32]),
        tokenizer.event2tokens(["patch_change", 0, 0, 3, 2, 88]),
        tokenizer.event2tokens(["patch_change", 0, 0, 4, 9, 0]),
    ]
    return events


def build_prompt_midi(case: str) -> bytes | None:
    if case == "scratch":
        return None
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    meta = mido.MidiTrack()
    midi.tracks.append(meta)
    meta.append(mido.MetaMessage("track_name", name="POC prompt", time=0))
    meta.append(
        mido.MetaMessage(
            "set_tempo", tempo=mido.bpm2tempo(DEFAULT_BPM), time=0
        )
    )
    meta.append(
        mido.MetaMessage(
            "time_signature", numerator=4, denominator=4, time=0
        )
    )
    _append_note_track(midi, "Piano", 0, 0, (60, 64, 67, 72))
    if case == "multitrack":
        _append_note_track(midi, "Bass", 1, 32, (36, 36, 43, 36))
        _append_note_track(midi, "Pad", 2, 88, (48, 53, 55, 53))
        _append_note_track(midi, "Drums", 9, 0, (36, 38, 42, 38))
    buffer = io.BytesIO()
    midi.save(file=buffer)
    return buffer.getvalue()


def _append_note_track(
    midi: mido.MidiFile,
    name: str,
    channel: int,
    program: int,
    pitches: tuple[int, ...],
) -> None:
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name=name, time=0))
    if channel != 9:
        track.append(
            mido.Message(
                "program_change", channel=channel, program=program, time=0
            )
        )
    for pitch in pitches:
        track.append(
            mido.Message(
                "note_on", channel=channel, note=pitch, velocity=88, time=0
            )
        )
        track.append(
            mido.Message(
                "note_off", channel=channel, note=pitch, velocity=0, time=480
            )
        )


def analyze_midi(midi_bytes: bytes) -> dict[str, Any]:
    midi = mido.MidiFile(file=io.BytesIO(midi_bytes))
    note_count = 0
    out_of_range_count = 0
    channels: set[int] = set()
    programs: set[tuple[int, int]] = set()
    time_signatures: set[str] = set()
    key_signatures: set[str] = set()
    tempos: set[int] = set()
    velocities: list[int] = []
    active: dict[tuple[int, int], int] = {}
    maximum_tick = 0
    for track in midi.tracks:
        absolute_tick = 0
        for message in track:
            absolute_tick += message.time
            maximum_tick = max(maximum_tick, absolute_tick)
            if message.type == "time_signature":
                time_signatures.add(f"{message.numerator}/{message.denominator}")
            elif message.type == "key_signature":
                key_signatures.add(message.key)
            elif message.type == "set_tempo":
                tempos.add(round(mido.tempo2bpm(message.tempo)))
            elif message.type == "program_change":
                channels.add(message.channel)
                programs.add((message.channel, message.program))
            elif message.type == "note_on" and message.velocity > 0:
                note_count += 1
                velocities.append(message.velocity)
                channels.add(message.channel)
                out_of_range_count += int(not 0 <= message.note <= 127)
                key = (message.channel, message.note)
                active[key] = active.get(key, 0) + 1
            elif message.type in {"note_off", "note_on"}:
                key = (message.channel, message.note)
                if active.get(key, 0):
                    active[key] -= 1
    return {
        "valid_midi": True,
        "midi_type": midi.type,
        "ticks_per_beat": midi.ticks_per_beat,
        "track_count": len(midi.tracks),
        "note_count": note_count,
        "duration_ticks": maximum_tick,
        "channels": sorted(channels),
        "programs": [list(value) for value in sorted(programs)],
        "time_signatures": sorted(time_signatures),
        "key_signatures": sorted(key_signatures),
        "tempos_bpm": sorted(tempos),
        "minimum_velocity": min(velocities) if velocities else None,
        "maximum_velocity": max(velocities) if velocities else None,
        "out_of_range_note_count": out_of_range_count,
        "stuck_note_count": sum(active.values()),
    }


def environment_manifest(device: str) -> dict[str, Any]:
    gpu = None
    gpu_total_bytes = None
    if torch.cuda.is_available():
        gpu = torch.cuda.get_device_name(0)
        gpu_total_bytes = torch.cuda.get_device_properties(0).total_memory
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "logical_cpu_count": psutil.cpu_count(),
        "ram_total_bytes": psutil.virtual_memory().total,
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "transformers": __import__("transformers").__version__,
        "peft": __import__("peft").__version__,
        "numpy": np.__version__,
        "requested_device": device,
        "cuda_available": torch.cuda.is_available(),
        "gpu": gpu,
        "gpu_total_bytes": gpu_total_bytes,
    }


if __name__ == "__main__":
    main()
