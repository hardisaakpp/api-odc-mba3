"""
Servicio para generar sugerencias de homologación entre productos MBA3 y SAP.
"""

import logging
import re
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class SugerenciasHomologacionService:
    """
    Servicio para generar sugerencias de homologación.
    
    IMPORTANTE: Este servicio NO homologa automáticamente.
    Solo SUGIERE posibles coincidencias para revisión humana.
    """
    
    # Pesos para scoring
    PESO_CODIGO_NORMALIZADO_IGUAL = 1.0
    PESO_PREFIJO_COMPARTIDO = 0.7
    PESO_CONTENCION_NUMERICA = 0.6
    PESO_COINCIDENCIA_NOMBRE = 0.4
    
    # Límites y umbrales
    MAX_SUGERENCIAS_POR_PRODUCTO = 5
    MIN_SCORE_SUGERENCIA = 0.5  # Umbral mínimo de score
    SCORE_MAX_TEORICO = 2.7  # Score máximo teórico (1.0 + 0.7 + 0.6 + 0.4)
    
    def __init__(self):
        """Inicializa el servicio."""
        pass
    
    def normalizar_codigo_avanzado(self, codigo: str) -> str:
        """
        Normalización avanzada: elimina puntos, guiones y espacios.
        
        Args:
            codigo: Código a normalizar
            
        Returns:
            Código normalizado
        """
        if not codigo:
            return ""
        # Eliminar puntos, guiones y espacios, convertir a mayúsculas
        return re.sub(r'[.\-\s]', '', codigo.strip().upper())
    
    def extraer_bloques_numericos(self, texto: str) -> List[str]:
        """
        Extrae bloques numéricos relevantes de un texto.
        
        Ejemplo:
            "C03.6794.9" -> ["6794"]
            "8040.1012-281" -> ["8040", "1012", "281"]
        
        Args:
            texto: Texto del cual extraer números
            
        Returns:
            Lista de bloques numéricos (como strings)
        """
        if not texto:
            return []
        
        # Buscar secuencias de dígitos (mínimo 3 dígitos para ser relevante)
        numeros = re.findall(r'\d{3,}', texto)
        return numeros
    
    def extraer_prefijo(self, codigo: str) -> str:
        """
        Extrae el prefijo de un código (parte antes del primer punto o guión).
        
        Ejemplo:
            "8040.10" -> "8040"
            "C03.6794.9" -> "C03"
        
        Args:
            codigo: Código del cual extraer prefijo
            
        Returns:
            Prefijo del código
        """
        if not codigo:
            return ""
        
        # Buscar prefijo (hasta primer punto, guión o espacio)
        match = re.match(r'^([^.\-\s]+)', codigo)
        return match.group(1).upper() if match else ""
    
    def calcular_similitud_nombre(self, nombre1: str, nombre2: str) -> Tuple[float, List[str]]:
        """
        Calcula similitud entre dos nombres basado en palabras comunes y referencias numéricas.
        
        Args:
            nombre1: Primer nombre
            nombre2: Segundo nombre
            
        Returns:
            Tupla (score, lista_motivos)
        """
        if not nombre1 or not nombre2:
            return 0.0, []
        
        nombre1_upper = nombre1.upper()
        nombre2_upper = nombre2.upper()
        
        motivos = []
        score = 0.0
        
        # Extraer palabras (tokens) de ambos nombres
        palabras1 = set(re.findall(r'\b\w+\b', nombre1_upper))
        palabras2 = set(re.findall(r'\b\w+\b', nombre2_upper))
        
        # Palabras comunes (excluyendo palabras muy cortas)
        palabras_comunes = palabras1.intersection(palabras2)
        palabras_comunes = {p for p in palabras_comunes if len(p) >= 3}
        
        if palabras_comunes:
            score += self.PESO_COINCIDENCIA_NOMBRE * 0.5
            motivos.append(f"Palabras comunes: {', '.join(list(palabras_comunes)[:3])}")
        
        # Referencias numéricas compartidas
        numeros1 = self.extraer_bloques_numericos(nombre1)
        numeros2 = self.extraer_bloques_numericos(nombre2)
        numeros_comunes = set(numeros1).intersection(set(numeros2))
        
        if numeros_comunes:
            score += self.PESO_COINCIDENCIA_NOMBRE * 0.5
            motivos.append(f"Referencia numérica compartida: {', '.join(list(numeros_comunes)[:2])}")
        
        return min(score, self.PESO_COINCIDENCIA_NOMBRE), motivos
    
    def normalizar_score(self, score: float) -> float:
        """
        Normaliza el score a rango 0-1.
        
        Args:
            score: Score original
            
        Returns:
            Score normalizado entre 0 y 1
        """
        return min(score / self.SCORE_MAX_TEORICO, 1.0)
    
    def buscar_sugerencias_para_producto(
        self,
        producto_mba3: Dict[str, Any],
        productos_sap: List[Dict[str, Any]],
        productos_ya_homologados: set
    ) -> List[Dict[str, Any]]:
        """
        Busca sugerencias de homologación para un producto MBA3.
        
        Args:
            producto_mba3: Producto MBA3 para el cual buscar sugerencias
            productos_sap: Lista completa de productos SAP
            productos_ya_homologados: Set de códigos SAP ya homologados
            
        Returns:
            Lista de sugerencias ordenadas por score (máx 5)
        """
        codigo_mba3 = producto_mba3.get("codigo_mba3", "")
        nombre_mba3 = producto_mba3.get("nombre_mba3", "")
        
        if not codigo_mba3:
            return []
        
        # Normalización y extracción de características del producto MBA3
        codigo_normalizado_mba3 = self.normalizar_codigo_avanzado(codigo_mba3)
        prefijo_mba3 = self.extraer_prefijo(codigo_mba3)
        numeros_mba3 = self.extraer_bloques_numericos(codigo_mba3)
        numeros_nombre_mba3 = self.extraer_bloques_numericos(nombre_mba3)
        todos_numeros_mba3 = set(numeros_mba3 + numeros_nombre_mba3)
        
        sugerencias = []
        
        # Evaluar cada producto SAP
        for producto_sap in productos_sap:
            codigo_sap = producto_sap.get("item_code", "")
            nombre_sap = producto_sap.get("item_name", "")
            active = producto_sap.get("active", True)
            
            # REGLA: No sugerir productos SAP inactivos
            if not active:
                continue
            
            # REGLA: No sugerir productos ya homologados
            if codigo_sap in productos_ya_homologados:
                continue
            
            if not codigo_sap:
                continue
            
            # Normalización y extracción de características del producto SAP
            codigo_normalizado_sap = self.normalizar_codigo_avanzado(codigo_sap)
            prefijo_sap = self.extraer_prefijo(codigo_sap)
            numeros_sap = self.extraer_bloques_numericos(codigo_sap)
            numeros_nombre_sap = self.extraer_bloques_numericos(nombre_sap)
            todos_numeros_sap = set(numeros_sap + numeros_nombre_sap)
            
            # Calcular score y motivos
            score = 0.0
            motivos = []
            tiene_coincidencia_numerica = False
            tiene_similitud_nombre = False
            
            # REGLA A: Código normalizado igual
            if codigo_normalizado_mba3 == codigo_normalizado_sap:
                score += self.PESO_CODIGO_NORMALIZADO_IGUAL
                motivos.append("Código normalizado idéntico")
            
            # REGLA C: Contención numérica (calcular primero para usar en prefijo)
            numeros_en_sap = todos_numeros_sap
            numeros_comunes = todos_numeros_mba3.intersection(numeros_en_sap)
            
            if numeros_comunes:
                tiene_coincidencia_numerica = True
                # Priorizar números más largos
                numero_mas_largo = max(numeros_comunes, key=len)
                score += self.PESO_CONTENCION_NUMERICA
                motivos.append(f"Coincidencia por referencia numérica {numero_mas_largo}")
            
            # REGLA B: Prefijo compartido (solo si hay coincidencia numérica o similitud nombre)
            if prefijo_mba3 and prefijo_sap and prefijo_mba3 == prefijo_sap:
                # Verificar si hay coincidencia numérica o similitud de nombre
                if tiene_coincidencia_numerica:
                    score += self.PESO_PREFIJO_COMPARTIDO
                    motivos.append(f"Prefijo compartido: {prefijo_mba3}")
                else:
                    # Verificar similitud de nombre antes de agregar prefijo
                    similitud_nombre, _ = self.calcular_similitud_nombre(nombre_mba3, nombre_sap)
                    if similitud_nombre > 0:
                        tiene_similitud_nombre = True
                        score += self.PESO_PREFIJO_COMPARTIDO
                        motivos.append(f"Prefijo compartido: {prefijo_mba3}")
            
            # REGLA D: Similitud de nombre
            similitud_nombre, motivos_nombre = self.calcular_similitud_nombre(nombre_mba3, nombre_sap)
            if similitud_nombre > 0:
                tiene_similitud_nombre = True
                score += similitud_nombre
                motivos.extend(motivos_nombre)
            
            # Solo agregar si supera umbral mínimo
            if score >= self.MIN_SCORE_SUGERENCIA:
                # Normalizar score
                score_normalizado = self.normalizar_score(score)
                score_original = round(score, 2)  # Mantener score original para referencia
                
                sugerencias.append({
                    "codigo_sap": codigo_sap,
                    "nombre_sap": nombre_sap,
                    "pack_sap": producto_sap.get("pack", ""),
                    "score": score_normalizado,  # Score normalizado 0-1 para frontend
                    "score_original": score_original,  # Score original para debugging
                    "motivos": motivos
                })
        
        # Ordenar por score descendente y limitar
        sugerencias.sort(key=lambda x: x["score"], reverse=True)
        return sugerencias[:self.MAX_SUGERENCIAS_POR_PRODUCTO]
    
    def obtener_sugerencias(
        self,
        productos_solo_mba3: List[Dict[str, Any]],
        productos_sap: List[Dict[str, Any]],
        productos_ya_homologados: set
    ) -> List[Dict[str, Any]]:
        """
        Obtiene sugerencias de homologación para productos solo_en_mba3.
        
        Recibe parámetros directamente en lugar de recalcular el cruce.
        
        Args:
            productos_solo_mba3: Lista de productos que solo están en MBA3
            productos_sap: Lista completa de productos SAP
            productos_ya_homologados: Set de códigos SAP ya homologados
            
        Returns:
            Lista de productos MBA3 con sus sugerencias
        """
        logger.info(f"📊 Generando sugerencias para {len(productos_solo_mba3)} productos sin match...")
        logger.info(f"📊 Excluyendo {len(productos_ya_homologados)} productos SAP ya homologados")
        
        resultado = []
        
        for producto_mba3 in productos_solo_mba3:
            sugerencias = self.buscar_sugerencias_para_producto(
                producto_mba3,
                productos_sap,
                productos_ya_homologados
            )
            
            resultado.append({
                "codigo_mba3": producto_mba3.get("codigo_mba3"),
                "nombre_mba3": producto_mba3.get("nombre_mba3"),
                "corp": producto_mba3.get("corp", ""),
                "grupo_prenda": producto_mba3.get("grupo_prenda", ""),
                "talla": producto_mba3.get("talla", ""),
                "presentacion": producto_mba3.get("presentacion", ""),
                "sugerencias": sugerencias
            })
        
        total_con_sugerencias = sum(1 for r in resultado if r["sugerencias"])
        logger.info(
            f"✅ Sugerencias generadas: {total_con_sugerencias} productos con sugerencias "
            f"de {len(resultado)} productos procesados"
        )
        
        return resultado






