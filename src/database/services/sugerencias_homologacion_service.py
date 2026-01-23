"""
Servicio para generar sugerencias de homologación entre productos MBA3 y SAP.
"""

import logging
import re
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz  # type: ignore[reportMissingImports]
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logger.warning("⚠️ rapidfuzz no está disponible. El fuzzy matching estará deshabilitado.")


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
    
    # Configuración para fuzzy matching híbrido
    UMBRAL_SCORE_ALTA_CONFIANZA = 0.7  # Si el sistema actual encuentra score >= 0.7, no usar fuzzy
    UMBRAL_FUZZY_MATCHING = 0.85  # Umbral mínimo para sugerencias fuzzy (muy alto para evitar falsos positivos)
    MAX_SUGERENCIAS_FUZZY = 3  # Máximo de sugerencias fuzzy por producto
    
    def __init__(self, usar_fuzzy_matching: bool = True):
        """
        Inicializa el servicio.
        
        Args:
            usar_fuzzy_matching: Si True, habilita fuzzy matching como respaldo.
                                Requiere que rapidfuzz esté instalado.
        """
        self.usar_fuzzy_matching = usar_fuzzy_matching and RAPIDFUZZ_AVAILABLE
        if usar_fuzzy_matching and not RAPIDFUZZ_AVAILABLE:
            logger.warning(
                "⚠️ Fuzzy matching solicitado pero rapidfuzz no está disponible. "
                "Instale con: pip install rapidfuzz"
            )
    
    def normalizar_codigo_avanzado(self, codigo: str) -> str:
        """
        Normalización avanzada (wrapper para compatibilidad).
        
        IMPORTANTE: Ahora usa función centralizada que incluye TODOS los separadores:
        ., -, /, _, espacio
        
        DEPRECATED: Usar normalizar_codigo_producto de src.utils directamente.
        Este wrapper se mantiene por compatibilidad con código existente.
        
        Args:
            codigo: Código a normalizar
            
        Returns:
            Código normalizado
        """
        from src.utils import normalizar_codigo_producto
        return normalizar_codigo_producto(codigo)
    
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
        productos_ya_homologados: set,
        usar_fuzzy: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        Busca sugerencias de homologación para un producto MBA3 usando sistema híbrido.
        
        ESTRATEGIA HÍBRIDA:
        1. PRIMERA PASADA: Sistema actual (scoring por reglas)
           - Si encuentra sugerencias con score >= 0.7 → Retornar (alta confianza)
        2. SEGUNDA PASADA: Fuzzy matching (solo si primera pasada no encontró buenos resultados)
           - Si score actual < 0.7 o no hay sugerencias
           - Aplicar fuzzy matching con umbral alto (0.85+)
           - Combinar resultados y re-ordenar
        
        Args:
            producto_mba3: Producto MBA3 para el cual buscar sugerencias
            productos_sap: Lista completa de productos SAP
            productos_ya_homologados: Set de códigos SAP ya homologados
            usar_fuzzy: Si True, habilita fuzzy matching como respaldo.
                       Si None, usa la configuración del servicio (self.usar_fuzzy_matching)
            
        Returns:
            Lista de sugerencias ordenadas por score (máx 5)
        """
        # Determinar si usar fuzzy matching
        usar_fuzzy_final = usar_fuzzy if usar_fuzzy is not None else self.usar_fuzzy_matching
        
        # 1. PRIMERA PASADA: Sistema actual (scoring por reglas)
        sugerencias_actuales = self._buscar_sugerencias_sistema_actual(
            producto_mba3, productos_sap, productos_ya_homologados
        )
        
        # Si hay sugerencias con alta confianza, retornar directamente
        if sugerencias_actuales and sugerencias_actuales[0]["score"] >= self.UMBRAL_SCORE_ALTA_CONFIANZA:
            logger.debug(
                f"✅ Sugerencias con alta confianza encontradas (score: {sugerencias_actuales[0]['score']:.2f}). "
                f"Omitiendo fuzzy matching."
            )
            return sugerencias_actuales
        
        # 2. SEGUNDA PASADA: Fuzzy matching (solo si es necesario y está habilitado)
        if usar_fuzzy_final and (not sugerencias_actuales or len(sugerencias_actuales) < 3):
            logger.debug(
                f"🔍 Aplicando fuzzy matching como respaldo. "
                f"Sugerencias actuales: {len(sugerencias_actuales)}"
            )
            sugerencias_fuzzy = self._buscar_con_fuzzy_matching(
                producto_mba3, productos_sap, productos_ya_homologados
            )
            
            # Combinar y deduplicar sugerencias
            sugerencias_combinadas = self._combinar_sugerencias(
                sugerencias_actuales, sugerencias_fuzzy
            )
            
            return sugerencias_combinadas[:self.MAX_SUGERENCIAS_POR_PRODUCTO]
        
        # Retornar sugerencias del sistema actual (sin fuzzy)
        return sugerencias_actuales
    
    def _buscar_sugerencias_sistema_actual(
        self,
        producto_mba3: Dict[str, Any],
        productos_sap: List[Dict[str, Any]],
        productos_ya_homologados: set
    ) -> List[Dict[str, Any]]:
        """
        Busca sugerencias usando el sistema actual (scoring por reglas).
        
        Este es el método original, extraído para mantener la lógica separada.
        
        Args:
            producto_mba3: Producto MBA3 para el cual buscar sugerencias
            productos_sap: Lista completa de productos SAP
            productos_ya_homologados: Set de códigos SAP ya homologados
            
        Returns:
            Lista de sugerencias ordenadas por score
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
    
    def _buscar_con_fuzzy_matching(
        self,
        producto_mba3: Dict[str, Any],
        productos_sap: List[Dict[str, Any]],
        productos_ya_homologados: set
    ) -> List[Dict[str, Any]]:
        """
        Busca sugerencias usando fuzzy matching como respaldo.
        
        Solo se ejecuta si el sistema actual no encontró buenas coincidencias.
        Usa umbral alto (0.85+) para evitar falsos positivos.
        
        Args:
            producto_mba3: Producto MBA3 para el cual buscar sugerencias
            productos_sap: Lista completa de productos SAP
            productos_ya_homologados: Set de códigos SAP ya homologados
            
        Returns:
            Lista de sugerencias fuzzy ordenadas por score (máx 3)
        """
        if not RAPIDFUZZ_AVAILABLE:
            return []
        
        codigo_mba3 = producto_mba3.get("codigo_mba3", "")
        nombre_mba3 = producto_mba3.get("nombre_mba3", "")
        
        if not codigo_mba3:
            return []
        
        sugerencias_fuzzy = []
        
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
            
            # Fuzzy matching en código (prioritario)
            ratio_codigo = fuzz.ratio(codigo_mba3.upper(), codigo_sap.upper())
            partial_ratio_codigo = fuzz.partial_ratio(codigo_mba3.upper(), codigo_sap.upper())
            token_sort_ratio = fuzz.token_sort_ratio(codigo_mba3.upper(), codigo_sap.upper())
            
            # Fuzzy matching en nombre (si existe)
            ratio_nombre = 0.0
            if nombre_mba3 and nombre_sap:
                ratio_nombre = fuzz.ratio(nombre_mba3.upper(), nombre_sap.upper())
            
            # Score combinado (priorizar código sobre nombre)
            # Usar el máximo de los ratios de código para capturar diferentes tipos de similitud
            score_codigo = max(ratio_codigo, partial_ratio_codigo, token_sort_ratio) / 100.0
            score_nombre = ratio_nombre / 100.0
            
            # Score final: 70% código, 30% nombre
            score_fuzzy = (score_codigo * 0.7) + (score_nombre * 0.3)
            
            # Solo incluir si supera umbral alto (0.85) para evitar falsos positivos
            if score_fuzzy >= self.UMBRAL_FUZZY_MATCHING:
                motivos = []
                if ratio_codigo >= 85:
                    motivos.append(f"Similitud de código: {ratio_codigo:.0f}%")
                if partial_ratio_codigo >= 85 and partial_ratio_codigo != ratio_codigo:
                    motivos.append(f"Similitud parcial: {partial_ratio_codigo:.0f}%")
                if ratio_nombre >= 70:
                    motivos.append(f"Similitud de nombre: {ratio_nombre:.0f}%")
                
                # Si no hay motivos específicos, usar genérico
                if not motivos:
                    motivos.append(f"Similitud fuzzy: {score_fuzzy*100:.0f}%")
                
                sugerencias_fuzzy.append({
                    "codigo_sap": codigo_sap,
                    "nombre_sap": nombre_sap,
                    "pack_sap": producto_sap.get("pack", ""),
                    "score": score_fuzzy,  # Ya está en rango 0-1
                    "score_original": round(score_fuzzy, 2),
                    "motivos": motivos
                })
        
        # Ordenar por score descendente y limitar
        sugerencias_fuzzy.sort(key=lambda x: x["score"], reverse=True)
        return sugerencias_fuzzy[:self.MAX_SUGERENCIAS_FUZZY]
    
    def _combinar_sugerencias(
        self,
        sugerencias_actuales: List[Dict[str, Any]],
        sugerencias_fuzzy: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Combina sugerencias del sistema actual y fuzzy matching, deduplicando.
        
        Args:
            sugerencias_actuales: Sugerencias del sistema actual (scoring por reglas)
            sugerencias_fuzzy: Sugerencias de fuzzy matching
            
        Returns:
            Lista combinada y ordenada por score, sin duplicados
        """
        # Diccionario para deduplicar por código SAP
        sugerencias_dict: Dict[str, Dict[str, Any]] = {}
        
        # Agregar sugerencias actuales (tienen prioridad)
        for sug in sugerencias_actuales:
            codigo_sap = sug.get("codigo_sap", "")
            if codigo_sap:
                sugerencias_dict[codigo_sap] = sug
        
        # Agregar sugerencias fuzzy (solo si no están ya en el dict)
        for sug in sugerencias_fuzzy:
            codigo_sap = sug.get("codigo_sap", "")
            if codigo_sap and codigo_sap not in sugerencias_dict:
                # Marcar como sugerencia fuzzy para referencia
                sug["es_fuzzy"] = True
                sugerencias_dict[codigo_sap] = sug
        
        # Convertir a lista y ordenar por score
        sugerencias_combinadas = list(sugerencias_dict.values())
        sugerencias_combinadas.sort(key=lambda x: x["score"], reverse=True)
        
        return sugerencias_combinadas
    
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
