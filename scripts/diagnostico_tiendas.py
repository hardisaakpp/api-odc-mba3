"""
Script de diagnóstico para la hoja "Tiendas" del Excel.
Muestra exactamente qué filas tienen celdas vacías o incompletas.
"""

import openpyxl
import sys
import os

# Agregar src al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def diagnosticar_tiendas(archivo_excel):
    """
    Lee la hoja Tiendas y reporta detalladamente qué filas tienen problemas.
    """
    print(f"\n📋 DIAGNÓSTICO: Hoja 'Tiendas' en {archivo_excel}\n")
    
    try:
        workbook = openpyxl.load_workbook(archivo_excel, data_only=True)
        
        # Buscar hoja Tiendas
        sheet_name = None
        for name in workbook.sheetnames:
            if name.lower() == "tiendas":
                sheet_name = name
                break
        
        if not sheet_name:
            print("❌ No se encontró hoja 'Tiendas'")
            print(f"   Hojas disponibles: {workbook.sheetnames}")
            return
        
        ws = workbook[sheet_name]
        print(f"✅ Hoja 'Tiendas' encontrada\n")
        
        # Leer headers
        print("📍 HEADERS (Fila 1):")
        for col_idx, cell in enumerate(ws[1]):
            print(f"   Columna {col_idx}: {cell.value}")
        
        # Detectar columnas
        col_codigo = None
        col_nombre = None
        col_activa = None
        
        for col_idx, cell in enumerate(ws[1]):
            if cell.value:
                header = str(cell.value).lower().replace(" ", "").replace("-", "")
                if any(x in header for x in ["id", "codigo", "code"]):
                    col_codigo = col_idx
                elif any(x in header for x in ["nombre", "tienda", "name"]):
                    col_nombre = col_idx
                elif any(x in header for x in ["activo", "active", "activa"]):
                    col_activa = col_idx
        
        print(f"\n📍 COLUMNAS DETECTADAS:")
        print(f"   ID TIENDA: Columna {col_codigo}")
        print(f"   NOMBRE TIENDA: Columna {col_nombre}")
        print(f"   ACTIVO: Columna {col_activa}")
        
        # Analizar filas
        print(f"\n📍 ANÁLISIS DE FILAS (desde fila 2 hasta {ws.max_row}):\n")
        
        filas_completas = []
        filas_incompletas = []
        filas_vacias = []
        
        for fila_idx in range(2, ws.max_row + 1):
            codigo = ws.cell(row=fila_idx, column=(col_codigo + 1)).value if col_codigo is not None else None
            nombre = ws.cell(row=fila_idx, column=(col_nombre + 1)).value if col_nombre is not None else None
            activa = ws.cell(row=fila_idx, column=(col_activa + 1)).value if col_activa is not None else None
            
            # Verificar si hay datos
            has_codigo = bool(codigo is not None and str(codigo).strip())
            has_nombre = bool(nombre is not None and str(nombre).strip())
            has_activa = bool(activa is not None and str(activa).strip())
            
            fila_tiene_datos = has_codigo or has_nombre or has_activa
            
            if not fila_tiene_datos:
                # Fila completamente vacía
                filas_vacias.append(fila_idx)
            else:
                # Fila con datos, verificar si está completa
                columnas_ok = has_codigo and has_nombre and (col_activa is None or has_activa)
                
                if columnas_ok:
                    filas_completas.append(fila_idx)
                else:
                    filas_incompletas.append({
                        "fila": fila_idx,
                        "ID TIENDA": codigo if has_codigo else "[VACÍO]",
                        "NOMBRE TIENDA": nombre if has_nombre else "[VACÍO]",
                        "ACTIVO": activa if has_activa else "[VACÍO]"
                    })
        
        # Reporte
        print(f"✅ FILAS COMPLETAS: {len(filas_completas)}")
        if filas_completas:
            print(f"   Filas: {filas_completas[:10]}{'...' if len(filas_completas) > 10 else ''}")
        
        print(f"\n❌ FILAS INCOMPLETAS: {len(filas_incompletas)}")
        if filas_incompletas:
            for item in filas_incompletas[:15]:
                print(f"\n   Fila {item['fila']}:")
                print(f"      ID TIENDA: {item['ID TIENDA']}")
                print(f"      NOMBRE TIENDA: {item['NOMBRE TIENDA']}")
                print(f"      ACTIVO: {item['ACTIVO']}")
            if len(filas_incompletas) > 15:
                print(f"\n   ... y {len(filas_incompletas) - 15} filas más incompletas")
        
        print(f"\n⚪ FILAS COMPLETAMENTE VACÍAS: {len(filas_vacias)}")
        if filas_vacias:
            print(f"   Filas: {filas_vacias[:20]}{'...' if len(filas_vacias) > 20 else ''}")
        
        # Resumen final
        print(f"\n{'='*70}")
        print(f"📊 RESUMEN:")
        print(f"{'='*70}")
        print(f"Total de filas en hoja: {ws.max_row}")
        print(f"  - Filas con datos completos: {len(filas_completas)}")
        print(f"  - Filas con datos incompletos: {len(filas_incompletas)} ❌ PROBLEMA")
        print(f"  - Filas completamente vacías: {len(filas_vacias)} (se ignoran)")
        
        if filas_incompletas:
            print(f"\n⚠️  ACCIÓN REQUERIDA:")
            print(f"   Las siguientes filas tienen columnas incompletas:")
            print(f"   Filas: {[item['fila'] for item in filas_incompletas]}")
            print(f"\n   OPCIONES:")
            print(f"   1️⃣  Completa los datos faltantes en esas filas")
            print(f"   2️⃣  O elimina completamente esas filas (todas las 3 columnas)")
        else:
            print(f"\n✅ NO HAY PROBLEMAS - Todas las filas están completas o vacías")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Buscar el archivo Excel más reciente
    import glob
    
    excel_files = glob.glob("*.xlsx") + glob.glob("**/*.xlsx", recursive=True)
    
    if not excel_files:
        print("❌ No se encontraron archivos .xlsx")
        print("   Uso: python diagnostico_tiendas.py [ruta_del_archivo.xlsx]")
        sys.exit(1)
    
    # Usar el archivo pasado como argumento o el más reciente
    if len(sys.argv) > 1:
        archivo = sys.argv[1]
    else:
        # Buscar un archivo que contenga "Plantilla" o "pedido"
        plantillas = [f for f in excel_files if "plantilla" in f.lower() or "pedido" in f.lower()]
        if plantillas:
            archivo = plantillas[0]
        else:
            archivo = excel_files[0]
    
    print(f"Leyendo: {archivo}")
    diagnosticar_tiendas(archivo)
