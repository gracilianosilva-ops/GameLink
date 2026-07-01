import os
import json

appdata = os.environ.get('APPDATA', '')
hydra_dir = os.path.join(appdata, 'hydralauncher')

print(f"Procurando em: {hydra_dir}")
print(f"Existe: {os.path.isdir(hydra_dir)}\n")

# Listar os 30 primeiros arquivos/diretórios
count = 0
for root, dirs, files in os.walk(hydra_dir):
    for name in dirs + files:
        if count < 30:
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, hydra_dir)
            print(rel_path)
            count += 1
        else:
            break
    if count >= 30:
        break

print(f"\n=== Procurando por arquivos JSON e .db ===")
for root, dirs, files in os.walk(hydra_dir):
    for file in files:
        if file.endswith(('.json', '.db', '.ldb', '.log')):
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, hydra_dir)
            tamanho = os.path.getsize(full_path)
            print(f"{rel_path} ({tamanho} bytes)")
