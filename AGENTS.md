# Instruções do projeto

- Mantenha o núcleo determinístico: toda aleatoriedade deve vir de `random.Random(seed)`.
- Não introduza interface gráfica, integração com DAWs ou recursos de IA sem pedido explícito.
- Execute `python -m pytest` com `PYTHONPATH=src` após alterações no código.
- Arquivos MIDI gerados devem ser gravados em `output/` e não versionados, exceto exemplos intencionais.
