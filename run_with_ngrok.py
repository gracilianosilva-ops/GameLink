import sys
import getpass

try:
    from pyngrok import ngrok
    
    # Pedir token ao usuário
    print("="*60)
    print("CONFIGURAR NGROK - ACESSO PÚBLICO")
    print("="*60)
    print("\n1. Acesse: https://dashboard.ngrok.com/get-started/your-authtoken")
    print("2. Copie seu token (começa com 'ngrok_')")
    print("3. Cole aqui:\n")
    
    token = getpass.getpass("Cole seu token ngrok: ").strip()
    
    if not token:
        print("❌ Token não fornecido!")
        sys.exit(1)
    
    # Configurar token
    print("\n⏳ Configurando ngrok...")
    ngrok.set_auth_token(token)
    
    port = 5000
    print(f"🚀 Conectando ao servidor local (porta {port})...")
    
    # Conectar ao servidor
    public_url = ngrok.connect(port)
    
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
    print(f"\n❌ Erro: {e}")
    sys.exit(1)
