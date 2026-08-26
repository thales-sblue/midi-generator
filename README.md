# midi-generator

MVP em Python para gerar melodias MIDI determinísticas para produção musical.

## Instalação

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Uso

```powershell
$env:PYTHONPATH = "src"
python -m midi_generator --bpm 124 --root A --scale minor --bars 8 --seed 2026 --output output/example.mid
```

Os parâmetros são BPM, nota raiz, escala (`major` ou `minor`), número de compassos e seed. A mesma configuração produz exatamente os mesmos eventos MIDI.

O gerador usa uma grade de colcheias em 4/4, inclui pausas, varia velocity e limita todas as alturas à escala escolhida. O projeto não inclui interface gráfica, integração com Ableton ou IA generativa.

## Testes

```powershell
$env:PYTHONPATH = "src"
python -m pytest
```
