"""
Script de Validación del Sistema de Migraciones
================================================
Verifica que el sistema de migraciones está correctamente configurado
y puede ejecutarse sin errores.

Uso:
    python scripts/test_migration_system.py
"""

import sys
import os
from pathlib import Path
from typing import List, Tuple

# Configurar codificación UTF-8 para Windows
if sys.platform == 'win32':
    # Intentar establecer UTF-8 para la consola
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Agregar src al path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Colores para la terminal
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_test(name: str, result: bool, details: str = "") -> None:
    """Imprimir resultado de un test."""
    # Usar caracteres ASCII si UTF-8 no está disponible
    try:
        symbol = f"{Colors.GREEN}✓{Colors.RESET}" if result else f"{Colors.RED}✗{Colors.RESET}"
        status = f"{Colors.GREEN}OK{Colors.RESET}" if result else f"{Colors.RED}FALLO{Colors.RESET}"
        print(f"  {symbol} {name}: {status}")
    except UnicodeEncodeError:
        # Fallback a ASCII
        symbol = "[OK]" if result else "[X]"
        status = "OK" if result else "FALLO"
        print(f"  {symbol} {name}: {status}")
    
    if details:
        try:
            print(f"      {details}")
        except UnicodeEncodeError:
            print(f"      {details.encode('ascii', 'replace').decode('ascii')}")


def check_dependencies() -> Tuple[bool, str]:
    """Verificar que las dependencias están instaladas."""
    try:
        import yaml
        return True, f"PyYAML {yaml.__version__}"
    except ImportError:
        return False, "PyYAML no está instalado. Ejecutar: pip install PyYAML>=6.0.1"


def check_files() -> List[Tuple[str, bool, str]]:
    """Verificar que existen los archivos necesarios."""
    scripts_dir = Path(__file__).parent
    
    files_to_check = [
        ("migration_runner.py", scripts_dir / "migration_runner.py"),
        ("migrations_manifest.yaml", scripts_dir / "migrations_manifest.yaml"),
        ("000_create_schema_migrations.sql", scripts_dir / "migrations" / "000_create_schema_migrations.sql"),
    ]
    
    results = []
    for name, path in files_to_check:
        exists = path.exists()
        detail = str(path) if exists else f"No encontrado: {path}"
        results.append((name, exists, detail))
    
    return results


def check_manifest() -> Tuple[bool, str]:
    """Verificar que el manifest es válido."""
    try:
        import yaml
        
        manifest_path = Path(__file__).parent / "migrations_manifest.yaml"
        
        with open(manifest_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        migrations = data.get('migrations', [])
        
        if not migrations:
            return False, "El manifest no contiene migraciones"
        
        # Verificar que cada migración tiene los campos requeridos
        required_fields = ['version', 'name', 'file', 'description', 'category']
        
        for i, migration in enumerate(migrations):
            for field in required_fields:
                if field not in migration:
                    return False, f"Migración {i} ({migration.get('name', 'desconocida')}) no tiene campo '{field}'"
        
        return True, f"{len(migrations)} migraciones definidas correctamente"
        
    except Exception as e:
        return False, f"Error al leer manifest: {str(e)}"


def check_scripts_exist() -> Tuple[bool, str, List[str]]:
    """Verificar que existen todos los scripts SQL referenciados en el manifest."""
    try:
        import yaml
        
        manifest_path = Path(__file__).parent / "migrations_manifest.yaml"
        scripts_dir = Path(__file__).parent
        
        with open(manifest_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        migrations = data.get('migrations', [])
        missing = []
        
        for migration in migrations:
            script_file = migration.get('file')
            if script_file:
                script_path = scripts_dir / script_file
                if not script_path.exists():
                    missing.append(f"{migration['version']}: {script_file}")
        
        if missing:
            return False, f"{len(missing)} scripts no encontrados", missing
        
        return True, f"Todos los {len(migrations)} scripts existen", []
        
    except Exception as e:
        return False, f"Error verificando scripts: {str(e)}", []


def check_database_connection() -> Tuple[bool, str]:
    """Verificar conexión a la base de datos."""
    try:
        from src.database.connection import get_db_connection
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar versión de SQL Server
        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()[0]
        
        conn.close()
        
        # Obtener solo la primera línea de la versión
        version_line = version.split('\n')[0][:80]
        
        return True, f"Conectado: {version_line}"
        
    except Exception as e:
        return False, f"Error de conexión: {str(e)}"


def check_migration_table() -> Tuple[bool, str]:
    """Verificar si existe la tabla schema_migrations."""
    try:
        from src.database.connection import get_db_connection
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_NAME = 'schema_migrations'
        """)
        
        exists = cursor.fetchone()[0] > 0
        
        if exists:
            # Contar migraciones aplicadas
            cursor.execute("SELECT COUNT(*) FROM schema_migrations")
            count = cursor.fetchone()[0]
            detail = f"Tabla existe, {count} migraciones aplicadas"
        else:
            detail = "Tabla no existe (se creará en primera ejecución)"
        
        conn.close()
        
        return True, detail
        
    except Exception as e:
        return False, f"Error verificando tabla: {str(e)}"


def main():
    """Ejecutar todas las validaciones."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}Sistema de Migraciones - Validación{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    all_passed = True
    
    # 1. Dependencias
    print(f"{Colors.BOLD}1. Dependencias de Python{Colors.RESET}")
    result, details = check_dependencies()
    print_test("PyYAML", result, details)
    all_passed = all_passed and result
    print()
    
    # 2. Archivos del sistema
    print(f"{Colors.BOLD}2. Archivos del Sistema{Colors.RESET}")
    file_results = check_files()
    for name, result, details in file_results:
        print_test(name, result, details if not result else "")
        all_passed = all_passed and result
    print()
    
    # 3. Manifest
    print(f"{Colors.BOLD}3. Manifest de Migraciones{Colors.RESET}")
    result, details = check_manifest()
    print_test("migrations_manifest.yaml", result, details)
    all_passed = all_passed and result
    print()
    
    # 4. Scripts SQL
    print(f"{Colors.BOLD}4. Scripts SQL{Colors.RESET}")
    result, details, missing = check_scripts_exist()
    print_test("Archivos SQL", result, details)
    if missing:
        for script in missing[:5]:  # Mostrar solo los primeros 5
            print(f"      {Colors.YELLOW}→ Falta: {script}{Colors.RESET}")
        if len(missing) > 5:
            print(f"      {Colors.YELLOW}→ ... y {len(missing) - 5} más{Colors.RESET}")
    all_passed = all_passed and result
    print()
    
    # 5. Conexión a BD
    print(f"{Colors.BOLD}5. Base de Datos{Colors.RESET}")
    result, details = check_database_connection()
    print_test("Conexión a BD", result, details)
    
    if result:
        # Solo verificar la tabla si hay conexión
        result2, details2 = check_migration_table()
        print_test("Tabla schema_migrations", result2, details2)
        all_passed = all_passed and result2
    else:
        all_passed = False
    
    print()
    
    # Resumen final
    print(f"{Colors.BOLD}{'='*70}{Colors.RESET}")
    
    try:
        if all_passed:
            print(f"{Colors.GREEN}{Colors.BOLD}✓ Todas las validaciones pasaron{Colors.RESET}")
            print(f"\n{Colors.GREEN}El sistema de migraciones está listo para usarse.{Colors.RESET}")
            print(f"\nPróximos pasos:")
            print(f"  1. Ver estado: {Colors.BLUE}python scripts/migration_runner.py --status{Colors.RESET}")
            print(f"  2. Dry-run:    {Colors.BLUE}python scripts/migration_runner.py --dry-run{Colors.RESET}")
            print(f"  3. Ejecutar:   {Colors.BLUE}python scripts/migration_runner.py{Colors.RESET}")
            sys.exit(0)
        else:
            print(f"{Colors.RED}{Colors.BOLD}✗ Algunas validaciones fallaron{Colors.RESET}")
            print(f"\n{Colors.RED}Corrige los errores antes de usar el sistema de migraciones.{Colors.RESET}")
            print(f"\nAyuda:")
            print(f"  - Instalar dependencias: {Colors.BLUE}pip install -r requirements.txt{Colors.RESET}")
            print(f"  - Verificar .env:        {Colors.BLUE}docs/CONFIGURACION.md{Colors.RESET}")
            print(f"  - Documentación:         {Colors.BLUE}docs/DEPLOY_MIGRATIONS.md{Colors.RESET}")
            sys.exit(1)
    except UnicodeEncodeError:
        # Fallback a ASCII sin colores
        if all_passed:
            print("[OK] Todas las validaciones pasaron")
            print("\nEl sistema de migraciones esta listo para usarse.")
            print("\nProximos pasos:")
            print("  1. Ver estado: python scripts/migration_runner.py --status")
            print("  2. Dry-run:    python scripts/migration_runner.py --dry-run")
            print("  3. Ejecutar:   python scripts/migration_runner.py")
            sys.exit(0)
        else:
            print("[ERROR] Algunas validaciones fallaron")
            print("\nCorrige los errores antes de usar el sistema de migraciones.")
            print("\nAyuda:")
            print("  - Instalar dependencias: pip install -r requirements.txt")
            print("  - Verificar .env:        docs/CONFIGURACION.md")
            print("  - Documentacion:         docs/DEPLOY_MIGRATIONS.md")
            sys.exit(1)


if __name__ == "__main__":
    main()
