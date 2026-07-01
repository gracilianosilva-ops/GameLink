import zipfile, os, sys
pz = os.path.join(os.path.dirname(__file__), '..', 'build', 'app', 'PYZ-00.pyz')
if not os.path.exists(pz):
    print('PYZ not found:', pz)
    sys.exit(1)
z = zipfile.ZipFile(pz)
py_files = [n for n in z.namelist() if n.endswith('.py')]
print('Found', len(py_files), 'py files')
for n in py_files:
    if n.endswith('app.py') or n.endswith('servicos/game_activity_service.py') or n.endswith('templates/_perfil_steam_status.py') or n.endswith('tests/test_game_activity_service.py'):
        print('match', n)
# extract the specific files
targets = ['app.py', 'servicos/game_activity_service.py', 'templates/_perfil_steam_status.html', 'tests/test_game_activity_service.py']
for t in targets:
    matches = [n for n in z.namelist() if n.endswith(t)]
    if not matches:
        print('no match for', t)
        continue
    match = matches[-1]
    out_path = os.path.join(os.path.dirname(__file__), 'extracted', t.replace('/', os.sep))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'wb') as f:
        f.write(z.read(match))
    print('extracted', match, '->', out_path)
print('done')
