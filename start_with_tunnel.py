#!/usr/bin/env python3
"""
Script de inicio rápido para Medicar AI API con túnel ngrok
Uso: python start_with_tunnel.py
"""

import sys
import subprocess
import os
from pathlib import Path


def check_requirements():
    """
    Verifica que las dependencias estén instaladas
    """
    try:
        import pyngrok
        import fastapi
        import uvicorn
        print("[OK] Dependencias verificadas")
        return True
    except ImportError as e:
        print(f"[ERROR] Falta dependencia: {e}")
        print("[TIP] Ejecuta: pip install -r requirements.txt")
        return False


def check_ngrok_auth():
    """
    Verifica que ngrok esté configurado con authtoken
    """
    try:
        from pyngrok import conf
        conf.get_default().auth_token
        print("[OK] Authtoken de ngrok configurado")
        return True
    except:
        print("[ERROR] Authtoken de ngrok no configurado")
        print("[PASOS] Para configurar:")
        print("        1. Ve a https://ngrok.com/signup")
        print("        2. Obten tu authtoken")
        print("        3. Ejecuta: ngrok config add-authtoken TU_TOKEN")
        return False


def main():
    """
    Función principal
    """
    print("[INICIO] Iniciando Medicar AI API con tunel publico...")
    print("=" * 50)
    
    # Verificar dependencias
    if not check_requirements():
        return 1
    
    # Verificar configuración de ngrok
    if not check_ngrok_auth():
        return 1
    
    print("=" * 50)
    print("[NGROK] Iniciando servidor con tunel ngrok...")
    print("[TIP] Presiona Ctrl+C para detener")
    print("=" * 50)
    
    # Ejecutar main.py con túnel
    try:
        subprocess.run([sys.executable, "main.py", "--tunnel"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Error ejecutando servidor: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n[BYE] Servidor detenido!")
        return 0
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
