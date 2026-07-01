import sys
import getpass
import re
from pathlib import Path

from pyngrok.conf import PyngrokConfig


def limpar_token_ngrok(token_bruto: str) -> str:
    token_bruto = (token_bruto or "").strip()
    correspondencia = re.search(r"([A-Za-z0-9_-]{20,})", token_bruto)
    if correspondencia:
        return correspondencia.group(1)
    return token_bruto

try:
    from pyngrok import ngrok
    
    # Pedir token ao usuário
    print("="*60)
    print("CONFIGURAR NGROK - ACESSO PÚBLICO")
    print("="*60)
    print("\n1. Acesse: https://dashboard.ngrok.com/get-started/your-authtoken")
    print("2. Copie seu token (começa com 'ngrok_')")
    print("3. Cole aqui:\n")
    
    token = limpar_token_ngrok(getpass.getpass("Cole seu token ngrok: "))
    
    if not token:
        print("❌ Token não fornecido!")
        sys.exit(1)

    # Usar o binário local do ngrok que já vem na .venv
    ngrok_exe = Path(__file__).with_name(".venv").joinpath("Scripts", "ngrok.exe")
    pyngrok_config = PyngrokConfig(ngrok_path=str(ngrok_exe) if ngrok_exe.exists() else None)

    # Configurar token
    print("\n⏳ Configurando ngrok...")
    ngrok.set_auth_token(token, pyngrok_config=pyngrok_config)
    
    port = 5000
    print(f"🚀 Conectando ao servidor local (porta {port})...")
    
    # Conectar ao servidor
    public_url = ngrok.connect(port, pyngrok_config=pyngrok_config)
    
    print(f"\n{'='*60}")
    print(f"✅ NGROK ATIVADO COM SUCESSO!")
    print(f"{'='*60}")
    print(f"\n🌐 LINK DE ACESSO PÚBLICO:")
    print(f"   {public_url}")
    print(f"\n   Copie este link e compartilhe com pessoas!")
    print(f"   Elas podem acessar de qualquer lugar do mundo!\n")
    print(f"   Status: Rodando até você fechar este terminal...")
    print(f"{'='*60}\n")
    
    # Manter ngrok rodando
    try:
        ngrok.get_ngrok_process().proc.wait()
    except KeyboardInterrupt:
        print("\n⛔ ngrok encerrado (Ctrl+C)")
        
except Exception as e:
    if isinstance(e, ModuleNotFoundError) and e.name == "pyngrok":
        print("\n❌ Dependência ausente: instale pyngrok antes de executar este script.")
        sys.exit(1)
    print(f"\n❌ Erro: {e}")
    sys.exit(1)
