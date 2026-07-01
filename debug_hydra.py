import os
import time

appdata = os.environ.get('APPDATA', '')
hydra_log = os.path.join(appdata, 'hydralauncher', 'logs', 'network.txt')
print(f'Caminho: {hydra_log}')
print(f'Existe: {os.path.isfile(hydra_log)}')

if os.path.isfile(hydra_log):
    stat = os.stat(hydra_log)
    print(f'Tamanho: {stat.st_size} bytes')
    print(f'Modificado há {time.time() - os.path.getmtime(hydra_log):.1f} segundos')
    with open(hydra_log, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    print(f'Conteúdo (primeiros 1000 caracteres):')
    print(content[:1000])
else:
    print('Arquivo não encontrado!')
