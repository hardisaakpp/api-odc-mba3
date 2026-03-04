"""
Sistema de Migraciones para Producción
=======================================
Runner para ejecutar migraciones SQL de forma controlada, idempotente y trazable.

Uso:
    python scripts/migration_runner.py --help
    python scripts/migration_runner.py --dry-run
    python scripts/migration_runner.py --category base
    python scripts/migration_runner.py --up-to 101
    python scripts/migration_runner.py --status
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Optional, Set
import argparse
import logging
import hashlib
from datetime import datetime
import yaml

# Agregar src al path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db_connection

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class MigrationRunner:
    """Ejecutor de migraciones SQL con control de versiones."""
    
    def __init__(self, manifest_path: Path, scripts_dir: Path):
        self.manifest_path = manifest_path
        self.scripts_dir = scripts_dir
        self.migrations: List[Dict] = []
        self.applied_versions: Set[str] = set()
        self.conn = None
        self.cursor = None
        
    def load_manifest(self) -> None:
        """Cargar el manifest YAML de migraciones."""
        logger.info(f"📄 Cargando manifest: {self.manifest_path}")
        
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"No se encontró el manifest: {self.manifest_path}")
        
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        self.migrations = data.get('migrations', [])
        logger.info(f"✅ Cargadas {len(self.migrations)} migraciones del manifest")
        
    def connect_db(self) -> None:
        """Conectar a la base de datos."""
        logger.info("🔌 Conectando a la base de datos...")
        self.conn = get_db_connection()
        self.cursor = self.conn.cursor()
        logger.info("✅ Conexión establecida")
        
    def ensure_migration_table(self) -> None:
        """Asegurar que existe la tabla de control de migraciones."""
        assert self.cursor is not None, "Debe llamar connect_db() antes de ensure_migration_table()"
        logger.info("🔍 Verificando tabla schema_migrations...")
        
        # Verificar si existe la tabla
        self.cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_NAME = 'schema_migrations'
        """)
        row = self.cursor.fetchone()
        assert row is not None, "No se obtuvo resultado de COUNT(*)"
        exists = row[0] > 0
        
        if not exists:
            logger.warning("⚠️  Tabla schema_migrations no existe. Creándola...")
            init_script = self.scripts_dir / "migrations" / "000_create_schema_migrations.sql"
            
            if not init_script.exists():
                raise FileNotFoundError(
                    f"No se encontró el script de inicialización: {init_script}\n"
                    "Ejecuta primero: scripts/migrations/000_create_schema_migrations.sql"
                )
            # Usar autocommit para que el DDL (CREATE TABLE) persista de inmediato en SQL Server
            prev_autocommit = self.conn.autocommit
            try:
                self.conn.autocommit = True
                self._execute_script(init_script, version='000', name='create_schema_migrations')
            finally:
                self.conn.autocommit = prev_autocommit
            # Verificar que la tabla quedó creada
            self.cursor.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_NAME = 'schema_migrations'
            """)
            row = self.cursor.fetchone()
            if not row or row[0] == 0:
                raise RuntimeError(
                    "La tabla schema_migrations no existe después de ejecutar el script inicial. "
                    "Comprueba permisos y que el script 000_create_schema_migrations.sql se ejecutó sin errores."
                )
            logger.info("✅ Tabla schema_migrations creada")
        else:
            logger.info("✅ Tabla schema_migrations existe")
    
    def load_applied_migrations(self) -> None:
        """Cargar las migraciones ya aplicadas desde la BD."""
        assert self.cursor is not None, "Debe llamar connect_db() antes de load_applied_migrations()"
        logger.info("📋 Cargando migraciones aplicadas...")
        
        self.cursor.execute("""
            SELECT version, name, applied_at, execution_time_ms
            FROM schema_migrations
            ORDER BY applied_at
        """)
        
        rows = self.cursor.fetchall()
        self.applied_versions = {row[0] for row in rows}
        
        logger.info(f"✅ {len(self.applied_versions)} migraciones ya aplicadas")
        
        if rows and logger.level <= logging.DEBUG:
            logger.debug("Últimas 5 migraciones aplicadas:")
            for row in rows[-5:]:
                version, name, applied_at, exec_time = row
                logger.debug(f"  - {version}: {name} ({applied_at}, {exec_time}ms)")
    
    def get_pending_migrations(
        self, 
        category: Optional[str] = None,
        up_to: Optional[str] = None,
        skip_manual: bool = True
    ) -> List[Dict]:
        """
        Obtener lista de migraciones pendientes.
        
        Args:
            category: Filtrar por categoría (base, alter, data, etc)
            up_to: Ejecutar solo hasta esta versión (inclusive)
            skip_manual: Saltar migraciones marcadas como manual
        """
        pending = []
        
        for migration in self.migrations:
            version = migration['version']
            
            # Verificar si ya está aplicada
            if version in self.applied_versions:
                continue
            
            # Filtrar por categoría si se especifica
            if category and migration.get('category') != category:
                continue
            
            # Saltar si es manual y skip_manual=True
            if skip_manual and migration.get('manual', False):
                logger.info(f"⏭️  Saltando migración manual: {version} - {migration['name']}")
                continue
            
            # Saltar si tiene skip_by_default=True
            if migration.get('skip_by_default', False):
                logger.info(f"⏭️  Saltando migración opcional: {version} - {migration['name']}")
                continue
            
            pending.append(migration)
            
            # Si llegamos a up_to, detenerse
            if up_to and version == up_to:
                break
        
        return pending
    
    def validate_dependencies(self, migration: Dict) -> bool:
        """Validar que todas las dependencias estén aplicadas."""
        dependencies = migration.get('dependencies', [])
        
        if not dependencies:
            return True
        
        missing = [dep for dep in dependencies if dep not in self.applied_versions]
        
        if missing:
            logger.error(
                f"❌ Migración {migration['version']} tiene dependencias sin aplicar: {missing}"
            )
            return False
        
        return True
    
    def calculate_checksum(self, script_path: Path) -> str:
        """Calcular checksum SHA256 del script."""
        sha256 = hashlib.sha256()
        with open(script_path, 'rb') as f:
            sha256.update(f.read())
        return sha256.hexdigest()
    
    def _execute_script(
        self, 
        script_path: Path, 
        version: str, 
        name: str,
        dry_run: bool = False
    ) -> Optional[int]:
        """
        Ejecutar un script SQL dividido por GO statements.
        
        Returns:
            Tiempo de ejecución en ms, o None si es dry-run
        """
        assert self.conn is not None and self.cursor is not None, "Debe llamar connect_db() antes de _execute_script()"
        logger.info(f"📄 Leyendo script: {script_path.name}")
        
        with open(script_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # Dividir por GO statements (case insensitive)
        blocks = []
        current_block = []
        
        for line in sql_content.split('\n'):
            line_stripped = line.strip().upper()
            
            if line_stripped == 'GO':
                if current_block:
                    blocks.append('\n'.join(current_block))
                    current_block = []
            else:
                current_block.append(line)
        
        # Agregar último bloque
        if current_block:
            blocks.append('\n'.join(current_block))
        
        # Filtrar bloques vacíos
        blocks = [b.strip() for b in blocks if b.strip()]
        
        logger.info(f"   Bloques SQL a ejecutar: {len(blocks)}")
        
        if dry_run:
            logger.info(f"   🔍 [DRY-RUN] Se ejecutarían {len(blocks)} bloques")
            return None
        
        # Ejecutar cada bloque
        start_time = datetime.now()
        executed = 0
        
        try:
            for i, block in enumerate(blocks, 1):
                # Saltar solo bloques completamente vacíos (no saltar por comentarios al inicio)
                if not block:
                    continue
                
                try:
                    self.cursor.execute(block)
                    executed += 1
                    
                    # Obtener mensajes PRINT del servidor
                    while self.cursor.nextset():
                        pass
                    
                except Exception as e:
                    error_msg = str(e)
                    
                    # Algunos errores son esperables (columna ya existe, propiedad ya existe, etc)
                    if any(code in error_msg for code in ['4922', '1913', '1914', '2714', '2705', '15233']):
                        logger.debug(f"   ℹ️  Bloque {i}/{len(blocks)}: {error_msg[:100]}")
                        continue
                    else:
                        logger.error(f"   ❌ Error en bloque {i}/{len(blocks)}: {error_msg}")
                        raise
            
            if not self.conn.autocommit:
                self.conn.commit()
            
            execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.info(f"   ✅ Ejecutados {executed}/{len(blocks)} bloques ({execution_time_ms}ms)")
            
            return execution_time_ms
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"   ❌ Error ejecutando script, rollback realizado")
            raise
    
    def execute_migration(self, migration: Dict, dry_run: bool = False) -> bool:
        """
        Ejecutar una migración y registrarla.
        
        Returns:
            True si se ejecutó correctamente, False si falló
        """
        assert self.conn is not None and self.cursor is not None, "Debe llamar connect_db() antes de execute_migration()"
        version = migration['version']
        name = migration['name']
        filename = migration['file']
        description = migration.get('description', '')
        warning = migration.get('warning')
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🔄 Migración {version}: {name}")
        logger.info(f"   Archivo: {filename}")
        logger.info(f"   Descripción: {description}")
        
        if warning:
            logger.warning(f"   ⚠️  {warning}")
            if not dry_run:
                response = input(f"   ¿Continuar con esta migración? (y/N): ")
                if response.lower() != 'y':
                    logger.info("   ⏭️  Migración saltada por el usuario")
                    return False
        
        # Validar dependencias
        if not self.validate_dependencies(migration):
            return False
        
        # Construir ruta del script
        script_path = self.scripts_dir / filename
        
        if not script_path.exists():
            logger.error(f"❌ No se encontró el script: {script_path}")
            return False
        
        # Calcular checksum
        checksum = self.calculate_checksum(script_path)
        
        try:
            # Ejecutar el script
            execution_time_ms = self._execute_script(script_path, version, name, dry_run)
            
            if not dry_run:
                # Registrar en schema_migrations
                self.cursor.execute("""
                    INSERT INTO schema_migrations 
                    (version, name, applied_at, execution_time_ms, checksum, applied_by)
                    VALUES (?, ?, GETDATE(), ?, ?, SYSTEM_USER)
                """, (version, name, execution_time_ms, checksum))
                
                self.conn.commit()
                self.applied_versions.add(version)
                
                logger.info(f"✅ Migración {version} aplicada exitosamente")
            else:
                logger.info(f"🔍 [DRY-RUN] Migración {version} se ejecutaría correctamente")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error aplicando migración {version}: {e}", exc_info=True)
            return False
    
    def run(
        self, 
        dry_run: bool = False,
        category: Optional[str] = None,
        up_to: Optional[str] = None,
        skip_manual: bool = True
    ) -> bool:
        """
        Ejecutar migraciones pendientes.
        
        Returns:
            True si todas las migraciones se aplicaron correctamente
        """
        try:
            self.load_manifest()
            self.connect_db()
            self.ensure_migration_table()
            self.load_applied_migrations()
            
            # Obtener migraciones pendientes
            pending = self.get_pending_migrations(
                category=category, 
                up_to=up_to,
                skip_manual=skip_manual
            )
            
            if not pending:
                logger.info("\n✅ No hay migraciones pendientes")
                return True
            
            logger.info(f"\n📋 Migraciones pendientes: {len(pending)}")
            
            if dry_run:
                logger.info("\n🔍 [DRY-RUN] Las siguientes migraciones se ejecutarían:")
            
            for migration in pending:
                logger.info(f"   - {migration['version']}: {migration['name']} [{migration.get('category', 'N/A')}]")
            
            if dry_run:
                logger.info("\n🔍 [DRY-RUN] Ejecutando validación de scripts...\n")
            else:
                logger.info(f"\n🚀 Ejecutando {len(pending)} migraciones...\n")
            
            # Ejecutar migraciones
            success_count = 0
            failed = []
            
            for migration in pending:
                success = self.execute_migration(migration, dry_run)
                
                if success:
                    success_count += 1
                else:
                    failed.append(migration)
                    logger.error(f"\n❌ Migración {migration['version']} falló. Deteniendo ejecución.")
                    break
            
            # Resumen
            logger.info(f"\n{'='*80}")
            
            if dry_run:
                logger.info(f"🔍 [DRY-RUN] Resumen:")
                logger.info(f"   - Migraciones validadas: {success_count}/{len(pending)}")
                if not failed:
                    logger.info(f"   ✅ Todas las migraciones son válidas y están listas para aplicarse")
            else:
                logger.info(f"📊 Resumen de ejecución:")
                logger.info(f"   - Aplicadas: {success_count}/{len(pending)}")
                
                if failed:
                    logger.error(f"   - Fallidas: {len(failed)}")
                    for m in failed:
                        logger.error(f"     • {m['version']}: {m['name']}")
                else:
                    logger.info(f"   ✅ Todas las migraciones se aplicaron exitosamente")
            
            return len(failed) == 0
            
        except Exception as e:
            logger.error(f"❌ Error en el proceso de migración: {e}", exc_info=True)
            return False
        
        finally:
            if self.conn:
                self.conn.close()
                logger.debug("🔌 Conexión cerrada")
    
    def show_status(self) -> None:
        """Mostrar estado actual de migraciones."""
        try:
            self.load_manifest()
            self.connect_db()
            self.ensure_migration_table()
            self.load_applied_migrations()
            
            logger.info(f"\n{'='*80}")
            logger.info("📊 Estado de Migraciones")
            logger.info(f"{'='*80}\n")
            
            applied = []
            pending = []
            
            for migration in self.migrations:
                version = migration['version']
                name = migration['name']
                category = migration.get('category', 'N/A')
                
                if version in self.applied_versions:
                    applied.append(migration)
                else:
                    pending.append(migration)
            
            logger.info(f"✅ Aplicadas: {len(applied)}/{len(self.migrations)}")
            if applied:
                for m in applied[-10:]:  # Últimas 10
                    logger.info(f"   • {m['version']}: {m['name']} [{m.get('category')}]")
                if len(applied) > 10:
                    logger.info(f"   ... y {len(applied) - 10} más")
            
            logger.info(f"\n⏳ Pendientes: {len(pending)}")
            if pending:
                for m in pending:
                    status = "[MANUAL]" if m.get('manual') else ""
                    logger.info(f"   • {m['version']}: {m['name']} [{m.get('category')}] {status}")
            
            logger.info(f"\n{'='*80}\n")
            
        finally:
            if self.conn:
                self.conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Sistema de Migraciones para MBA3 Consultas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Ver estado actual
  python scripts/migration_runner.py --status
  
  # Dry-run (validar sin ejecutar)
  python scripts/migration_runner.py --dry-run
  
  # Ejecutar solo migraciones base
  python scripts/migration_runner.py --category base
  
  # Ejecutar hasta la versión 101
  python scripts/migration_runner.py --up-to 101
  
  # Ejecutar todas las pendientes (¡CUIDADO EN PRODUCCIÓN!)
  python scripts/migration_runner.py
  
  # Incluir migraciones manuales
  python scripts/migration_runner.py --include-manual --dry-run
        """
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validar migraciones sin ejecutarlas'
    )
    
    parser.add_argument(
        '--status',
        action='store_true',
        help='Mostrar estado de migraciones (aplicadas vs pendientes)'
    )
    
    parser.add_argument(
        '--category',
        type=str,
        choices=['base', 'alter', 'index', 'data', 'config', 'sap', 'rollback'],
        help='Ejecutar solo migraciones de una categoría específica'
    )
    
    parser.add_argument(
        '--up-to',
        type=str,
        help='Ejecutar solo hasta esta versión (inclusive)'
    )
    
    parser.add_argument(
        '--include-manual',
        action='store_true',
        help='Incluir migraciones marcadas como manual'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Mostrar logs detallados (DEBUG level)'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Rutas
    scripts_dir = Path(__file__).parent
    manifest_path = scripts_dir / "migrations_manifest.yaml"
    
    runner = MigrationRunner(manifest_path, scripts_dir)
    
    if args.status:
        runner.show_status()
    else:
        success = runner.run(
            dry_run=args.dry_run,
            category=args.category,
            up_to=args.up_to,
            skip_manual=not args.include_manual
        )
        
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
