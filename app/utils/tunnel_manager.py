"""
Módulo para gestionar túneles ngrok automáticamente
Permite exponer la API local al internet público de forma sencilla
"""

import os
import time
import webbrowser
import threading
from typing import Optional
from pyngrok import ngrok, conf
from pyngrok.exception import PyngrokNgrokError


class TunnelManager:
    """
    Gestor de túneles ngrok para exponer la API al público
    """
    
    def __init__(self, port: int = 8000):
        self.port = port
        self.tunnel = None
        self.public_url = None
        self.is_active = False
        
    def start_tunnel(self, open_dashboard: bool = True) -> Optional[str]:
        """
        Inicia el túnel ngrok y retorna la URL pública
        
        Args:
            open_dashboard: Si abrir el dashboard de ngrok automáticamente
            
        Returns:
            URL pública del túnel o None si hay error
        """
        try:
            print("[NGROK] Iniciando tunel ngrok...")
            
            # Configurar ngrok (busca authtoken automáticamente)
            try:
                # Intentar usar authtoken del archivo de configuración
                conf.get_default().auth_token
            except:
                print("[WARNING] No se encontro authtoken de ngrok.")
                print("          Ejecuta: ngrok config add-authtoken TU_TOKEN")
                return None
            
            # Crear túnel HTTP
            self.tunnel = ngrok.connect(self.port, "http")
            self.public_url = self.tunnel.public_url
            self.is_active = True
            
            print("=" * 60)
            print("TUNEL NGROK ACTIVO")
            print("=" * 60)
            print(f"URL Local:   http://localhost:{self.port}")
            print(f"URL Publica: {self.public_url}")
            print(f"Dashboard:   http://localhost:4040")
            print("=" * 60)
            print("Tip: La URL publica cambiara cuando reinicies ngrok")
            print("     Para URL fija, considera el plan pagado de ngrok")
            print("=" * 60)
            
            # Abrir dashboard de ngrok en navegador
            if open_dashboard:
                threading.Timer(2.0, lambda: webbrowser.open("http://localhost:4040")).start()
            
            return self.public_url
            
        except PyngrokNgrokError as e:
            print(f"[ERROR] Error de ngrok: {str(e)}")
            if "authtoken" in str(e).lower():
                print("[SOLUCION] Configura tu authtoken con:")
                print("           ngrok config add-authtoken TU_TOKEN")
            return None
        except Exception as e:
            print(f"[ERROR] Error iniciando tunel: {str(e)}")
            return None
    
    def stop_tunnel(self):
        """
        Detiene el túnel ngrok
        """
        if self.tunnel:
            try:
                ngrok.disconnect(self.tunnel.public_url)
                print("[STOP] Tunel ngrok desconectado")
            except:
                pass
            finally:
                self.tunnel = None
                self.public_url = None
                self.is_active = False
    
    def get_public_url(self) -> Optional[str]:
        """
        Obtiene la URL pública actual del túnel
        
        Returns:
            URL pública o None si no hay túnel activo
        """
        return self.public_url if self.is_active else None
    
    def get_tunnel_info(self) -> dict:
        """
        Obtiene información completa del túnel
        
        Returns:
            Diccionario con información del túnel
        """
        return {
            "is_active": self.is_active,
            "local_port": self.port,
            "local_url": f"http://localhost:{self.port}",
            "public_url": self.public_url,
            "dashboard_url": "http://localhost:4040" if self.is_active else None
        }
    
    def __del__(self):
        """
        Limpieza automática al destruir el objeto
        """
        self.stop_tunnel()


def create_tunnel_info_endpoint():
    """
    Crea un endpoint para obtener información del túnel
    Útil para debugging y monitoreo
    """
    return {
        "tunnel_active": tunnel_manager.is_active if 'tunnel_manager' in globals() else False,
        "public_url": tunnel_manager.get_public_url() if 'tunnel_manager' in globals() else None,
        "local_url": f"http://localhost:8000",
        "dashboard": "http://localhost:4040" if 'tunnel_manager' in globals() and tunnel_manager.is_active else None
    }


# Instancia global del gestor de túneles
tunnel_manager = TunnelManager()
