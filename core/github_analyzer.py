"""
GitHub Java Code Analyzer - Simplified Version
"""
import os
import requests
import subprocess
import time
import json
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
from .llm import LLMFactory, LLMProvider


class GitHubJavaAnalyzer:
    """
    Analizador simplificado de código Java para repositorios de GitHub
    """

    def __init__(self, owner: str, repo: str):
        """
        Inicializa el analizador
        
        Args:
            owner: Propietario del repositorio
            repo: Nombre del repositorio  
        """
        load_dotenv()
        
        self.owner = owner
        self.repo = repo
        
        # Configuración de directorios
        self.base_dir = Path("analysis")
        self.downloads_dir = self.base_dir / "downloads" / f"{owner}_{repo}"
        
        # Configuración de GitHub API
        self.github_token = os.getenv('GITHUB_PAT')
        self.headers = self._setup_headers()
        
        # LLM para análisis
        self.llm = None
        
        # Crear directorios necesarios
        self._setup_directories()
        
        # Estado del repositorio local
        self.repo_downloaded = False
        self.local_java_files = []

    def _setup_headers(self) -> dict:
        """Configura headers para API de GitHub"""
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    def _setup_directories(self):
        """Crea la estructura de directorios necesaria"""
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

    def _make_request(self, url: str) -> requests.Response:
        """Hace petición con manejo básico de errores"""
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response

    def get_latest_branch(self) -> str:
        """Obtiene la rama con el commit más reciente"""
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/branches"
        response = self._make_request(url)
        branches = response.json()
        
        # Obtener la rama con el commit más reciente
        latest_branch = None
        latest_date = None
        
        for branch in branches:
            commit_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/commits/{branch['commit']['sha']}"
            commit_response = self._make_request(commit_url)
            commit_date = commit_response.json()['commit']['committer']['date']
            
            if latest_date is None or commit_date > latest_date:
                latest_date = commit_date
                latest_branch = branch['name']
        
        return latest_branch or 'main'

    def get_repository_files(self, branch: str) -> list:
        """Obtiene lista de archivos Java del repositorio"""
        # Obtener SHA del árbol
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/branches/{branch}"
        response = self._make_request(url)
        tree_sha = response.json()["commit"]["commit"]["tree"]["sha"]
        
        # Obtener árbol recursivo
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/git/trees/{tree_sha}?recursive=1"
        response = self._make_request(url)
        tree = response.json()["tree"]
        
        # Filtrar archivos Java
        files = [item for item in tree 
                if item["type"] == "blob" and item["path"].endswith(".java")]
        
        return files

    def get_file_content(self, file_path: str, branch: str = None) -> str:
        """Obtiene el contenido de un archivo del repositorio"""
        if not branch:
            branch = self.get_latest_branch()
            
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/contents/{file_path}?ref={branch}"
        response = self._make_request(url)
        content = response.json()["content"]
        
        import base64
        return base64.b64decode(content).decode('utf-8')

    def download_repository(self) -> bool:
        """
        Descarga automáticamente el repositorio desde la rama más reciente
        
        Returns:
            bool: True si la descarga fue exitosa
        """
        # Verificar si el repositorio ya está descargado
        if self.repo_downloaded and self.local_java_files:
            print(f"✅ Repositorio {self.owner}/{self.repo} ya está descargado ({len(self.local_java_files)} archivos)")
            return True
        
        # Verificar si existe el directorio de descarga con archivos
        if self.downloads_dir.exists():
            existing_java_files = list(self.downloads_dir.glob("**/*.java"))
            if existing_java_files:
                print(f"📁 Encontrado repositorio previamente descargado ({len(existing_java_files)} archivos)")
                
                # Reconstruir la lista de archivos locales
                self.local_java_files = []
                for java_file in existing_java_files:
                    relative_path = java_file.relative_to(self.downloads_dir)
                    self.local_java_files.append({
                        'path': str(relative_path).replace('\\', '/'),  # Convertir a formato Unix
                        'local_path': str(java_file),
                        'size': java_file.stat().st_size
                    })
                
                self.repo_downloaded = True
                print(f"✅ Repositorio cargado desde cache local")
                return True
        
        try:
            print(f"🚀 Iniciando descarga del repositorio {self.owner}/{self.repo}")
            
            # Obtener la rama más reciente
            branch = self.get_latest_branch()
            print(f"📂 Rama seleccionada: {branch}")
            
            # Obtener lista de archivos Java
            all_files = self.get_repository_files(branch)
            
            if not all_files:
                print("❌ No se encontraron archivos Java en el repositorio")
                return False
            
            print(f"📁 Encontrados {len(all_files)} archivos Java")
            
            downloaded_files = []
            
            for i, file_info in enumerate(all_files, 1):
                file_path = file_info['path']
                print(f"📥 Descargando archivo {i}/{len(all_files)}: {file_path}")
                
                try:
                    # Crear directorio local si no existe
                    local_file_path = self.downloads_dir / file_path
                    local_file_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Obtener contenido del archivo
                    content = self.get_file_content(file_path, branch)
                    
                    # Guardar archivo localmente
                    with open(local_file_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    
                    downloaded_files.append({
                        'path': file_path,
                        'local_path': str(local_file_path),
                        'size': len(content)
                    })
                    
                    # Delay para evitar rate limiting
                    time.sleep(0.1)
                    
                except Exception:
                    continue
            
            # Actualizar estado
            self.local_java_files = downloaded_files
            self.repo_downloaded = True
            
            print(f"✅ Descarga completada: {len(downloaded_files)} archivos descargados")
            
            return len(downloaded_files) > 0
            
        except Exception as e:
            print(f"❌ Error durante la descarga: {e}")
            return False

    def run_checkstyle_analysis(self, xml_config_path: str, max_files: int = None) -> dict:
        """
        Ejecuta análisis de Checkstyle en archivos locales
        
        Args:
            xml_config_path: Ruta al archivo XML de configuración de Checkstyle
            max_files: Número máximo de archivos a analizar (None para todos)
            
        Returns:
            dict: Resultados del análisis en formato JSON
        """
        if not self.repo_downloaded:
            return {"error": "Repository not downloaded"}
        
        # Validar archivos necesarios
        jar_path = Path("analysis/tools/checkstyle-10.26.1-all.jar")
        config_path = Path(xml_config_path)
        
        if not jar_path.exists() or not config_path.exists():
            return {"error": "Checkstyle jar or config file not found"}
        
        # Seleccionar archivos a analizar
        files_to_analyze = self.local_java_files
        if max_files:
            files_to_analyze = files_to_analyze[:max_files]
        
        print(f"🔍 Iniciando análisis Checkstyle de {len(files_to_analyze)} archivos...")
        
        results = {
            'repository': {
                'owner': self.owner,
                'name': self.repo
            },
            'analysis_type': 'checkstyle',
            'config_file': xml_config_path,
            'summary': {
                'total_files': len(files_to_analyze),
                'total_errors': 0,
                'total_warnings': 0,
                'analysis_time': 0
            },
            'patterns': {}
        }
        
        start_time = time.time()
        
        for i, file_info in enumerate(files_to_analyze, 1):
            print(f"📄 Analizando archivo {i}/{len(files_to_analyze)}: {file_info['path']}")
            
            local_file_path = Path(file_info['local_path'])
            
            # Ejecutar Checkstyle
            result = subprocess.run([
                "java", "-jar", str(jar_path),
                "-c", str(config_path),
                "-f", "plain",
                str(local_file_path)
            ], capture_output=True, text=True)
            
            # Parsear resultados
            file_results = self._parse_checkstyle_output(result.stdout)
            
            # Agregar a totales
            results['summary']['total_errors'] += file_results['errors']
            results['summary']['total_warnings'] += file_results['warnings']
            
            # Agregar patrones
            for pattern in file_results['violations']:
                pattern_name = pattern['rule']
                if pattern_name not in results['patterns']:
                    results['patterns'][pattern_name] = {'count': 0, 'type': pattern['type']}
                results['patterns'][pattern_name]['count'] += 1
        
        results['summary']['analysis_time'] = time.time() - start_time
        results['timestamp'] = datetime.now().isoformat()
        
        print(f"✅ Análisis Checkstyle completado: {results['summary']['total_errors']} errores, {results['summary']['total_warnings']} warnings")
        
        return results

    def _parse_checkstyle_output(self, output: str) -> dict:
        """Parsea la salida de Checkstyle"""
        violations = []
        error_count = 0
        warning_count = 0
        
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if '[ERROR]' in line:
                error_count += 1
                rule = self._extract_rule_from_line(line)
                violations.append({
                    'type': 'ERROR',
                    'rule': rule,
                    'message': line
                })
            elif '[WARN]' in line:
                warning_count += 1
                rule = self._extract_rule_from_line(line)
                violations.append({
                    'type': 'WARN', 
                    'rule': rule,
                    'message': line
                })
        
        return {
            'errors': error_count,
            'warnings': warning_count,
            'violations': violations
        }

    def _extract_rule_from_line(self, line: str) -> str:
        """Extrae el nombre de la regla de una línea de Checkstyle"""
        if '[' in line and ']' in line:
            parts = line.split('[')
            if len(parts) > 1:
                rule_part = parts[-1]
                return rule_part.split(']')[0]
        return 'Unknown'

    def setup_llm(self, provider: LLMProvider = LLMProvider.DEEPSEEK, model: str = "deepseek-coder"):
        """Configura el LLM para análisis de código"""
        try:
            self.llm = LLMFactory.create_llm(
                provider=provider,
                model=model,
                temperature=0.1,
                timeout=120,
                max_retries=3
            )
            return True
        except Exception:
            return False

    def run_llm_analysis(self, max_files: int) -> dict:
        """
        Ejecuta análisis con LLM en archivos locales
        
        Args:
            max_files: Número de archivos locales a analizar
            
        Returns:
            dict: Resultados del análisis en formato JSON
        """
        if not self.repo_downloaded:
            return {"error": "Repository not downloaded"}
        
        if not self.llm and not self.setup_llm():
            return {"error": "LLM not configured"}
        
        # Seleccionar archivos a analizar
        files_to_analyze = self.local_java_files[:max_files]
        
        print(f"🤖 Iniciando análisis LLM de {len(files_to_analyze)} archivos...")
        
        results = {
            'repository': {
                'owner': self.owner,
                'name': self.repo
            },
            'analysis_type': 'llm',
            'summary': {
                'total_files': len(files_to_analyze),
                'total_error_types': 0,
                'total_warning_types': 0,
                'total_error_occurrences': 0,
                'total_warning_occurrences': 0,
                'analysis_time': 0,
                'quality_distribution': {}
            },
            'top_patterns': {
                'errors': [],
                'warnings': []
            }
        }
        
        start_time = time.time()
        global_error_patterns = {}
        global_warning_patterns = {}
        
        for i, file_info in enumerate(files_to_analyze, 1):
            file_path = file_info['path']
            print(f"🔍 Analizando archivo {i}/{len(files_to_analyze)}: {file_path}")
            
            # Leer contenido del archivo
            with open(file_info['local_path'], 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            # Analizar con LLM
            file_result = self._analyze_file_with_llm(file_path, file_content)
            
            if file_result:
                results['summary']['total_error_types'] += file_result.get('total_error_types', 0)
                results['summary']['total_warning_types'] += file_result.get('total_warning_types', 0)
                results['summary']['total_error_occurrences'] += file_result.get('total_error_occurrences', 0)
                results['summary']['total_warning_occurrences'] += file_result.get('total_warning_occurrences', 0)
                
                # Distribución de calidad
                quality = file_result.get('quality_level', 'Unknown')
                results['summary']['quality_distribution'][quality] = \
                    results['summary']['quality_distribution'].get(quality, 0) + 1
                
                # Agregar patrones globales
                for module, pattern_info in file_result.get('error_patterns', {}).items():
                    if module not in global_error_patterns:
                        global_error_patterns[module] = {'frequency': 0, 'files': set()}
                    global_error_patterns[module]['frequency'] += pattern_info['frequency']
                    global_error_patterns[module]['files'].add(file_path)
                
                for module, pattern_info in file_result.get('warning_patterns', {}).items():
                    if module not in global_warning_patterns:
                        global_warning_patterns[module] = {'frequency': 0, 'files': set()}
                    global_warning_patterns[module]['frequency'] += pattern_info['frequency']
                    global_warning_patterns[module]['files'].add(file_path)
        
        # Top patrones
        if global_error_patterns:
            sorted_errors = sorted(global_error_patterns.items(), 
                                 key=lambda x: x[1]['frequency'], reverse=True)
            for module, info in sorted_errors[:5]:
                results['top_patterns']['errors'].append({
                    'module': module,
                    'frequency': info['frequency'],
                    'affected_files': len(info['files'])
                })
        
        if global_warning_patterns:
            sorted_warnings = sorted(global_warning_patterns.items(), 
                                   key=lambda x: x[1]['frequency'], reverse=True)
            for module, info in sorted_warnings[:5]:
                results['top_patterns']['warnings'].append({
                    'module': module,
                    'frequency': info['frequency'],
                    'affected_files': len(info['files'])
                })
        
        results['summary']['analysis_time'] = time.time() - start_time
        results['timestamp'] = datetime.now().isoformat()
        
        print(f"✅ Análisis LLM completado: {results['summary']['total_error_occurrences']} errores, {results['summary']['total_warning_occurrences']} warnings")
        
        return results

    def _analyze_file_with_llm(self, file_path: str, file_content: str) -> dict:
        """Analiza un archivo Java usando LLM"""
        try:
            prompt = self._create_checkstyle_prompt(file_content, file_path)
            response = self.llm.invoke(prompt)
            return self._parse_llm_response(response.content, file_path)
        except Exception:
            return {}

    def _create_checkstyle_prompt(self, file_content: str, file_name: str) -> str:
        """Creates a prompt based on Sun Checkstyle rules"""
        return f"""
            You are an expert Java code analyzer that applies Sun Code Conventions (sun_checks.xml from Checkstyle).

            Analyze this Java file: {file_name}

            FOCUS ON PATTERNS AND FREQUENCIES, NOT LINE-BY-LINE DETAILS.

            RULES TO VERIFY:
            - Javadoc: InvalidJavadocPosition, JavadocMethod, JavadocType, JavadocVariable, JavadocStyle, MissingJavadocMethod
            - Naming: ConstantName, LocalFinalVariableName, LocalVariableName, MemberName, MethodName, PackageName, ParameterName, StaticVariableName, TypeName
            - Imports: AvoidStarImport, IllegalImport, RedundantImport, UnusedImports
            - Whitespace: EmptyForIteratorPad, GenericWhitespace, MethodParamPad, NoWhitespaceAfter, NoWhitespaceBefore, OperatorWrap, ParenPad, TypecastParenPad, WhitespaceAfter, WhitespaceAround
            - Modifiers: ModifierOrder, RedundantModifier
            - Blocks: AvoidNestedBlocks, EmptyBlock, LeftCurly, NeedBraces, RightCurly
            - Coding: EmptyStatement, EqualsHashCode, HiddenField, IllegalInstantiation, InnerAssignment, MagicNumber, MissingSwitchDefault, MultipleVariableDeclarations, SimplifyBooleanExpression, SimplifyBooleanReturn
            - Design: DesignForExtension, FinalClass, HideUtilityClassConstructor, InterfaceIsType, VisibilityModifier
            - Size: FileLength, LineLength, MethodLength, ParameterNumber
            - Misc: ArrayTypeStyle, FinalParameters, TodoComment, UpperEll, NewlineAtEndOfFile, FileTabCharacter

            CODE:
            ```java
            {file_content}
            ```

            RESPONSE FORMAT:
            **ERROR PATTERNS:**
            - [MODULE_NAME]: Brief description - Found X times
            - [MODULE_NAME]: Brief description - Found X times

            **WARNING PATTERNS:**  
            - [MODULE_NAME]: Brief description - Found X times
            - [MODULE_NAME]: Brief description - Found X times

            **FILE SUMMARY:**
            - Total error types: X
            - Total warning types: X
            - Most critical issues: List the 3 most frequent/important patterns
            - Code quality level: Excellent/Good/Fair/Poor

            Focus on FREQUENCY and PATTERNS. Use exact module names from sun_checks.xml.
            """

    def _parse_llm_response(self, response_content: str, file_name: str) -> dict:
        """Parses LLM response focused on patterns and frequencies"""
        lines = response_content.split('\n')
        error_patterns = {}
        warning_patterns = {}
        current_section = None
        quality_level = "Unknown"
        
        # Known checkstyle modules
        checkstyle_modules = {
            'InvalidJavadocPosition', 'JavadocMethod', 'JavadocType', 'JavadocVariable', 
            'JavadocStyle', 'MissingJavadocMethod', 'ConstantName', 'LocalFinalVariableName', 
            'LocalVariableName', 'MemberName', 'MethodName', 'PackageName', 'ParameterName', 
            'StaticVariableName', 'TypeName', 'AvoidStarImport', 'IllegalImport', 
            'RedundantImport', 'UnusedImports', 'EmptyForIteratorPad', 'GenericWhitespace', 
            'MethodParamPad', 'NoWhitespaceAfter', 'NoWhitespaceBefore', 'OperatorWrap', 
            'ParenPad', 'TypecastParenPad', 'WhitespaceAfter', 'WhitespaceAround', 
            'ModifierOrder', 'RedundantModifier', 'AvoidNestedBlocks', 'EmptyBlock', 
            'LeftCurly', 'NeedBraces', 'RightCurly', 'EmptyStatement', 'EqualsHashCode', 
            'HiddenField', 'IllegalInstantiation', 'InnerAssignment', 'MagicNumber', 
            'MissingSwitchDefault', 'MultipleVariableDeclarations', 'SimplifyBooleanExpression', 
            'SimplifyBooleanReturn', 'DesignForExtension', 'FinalClass', 
            'HideUtilityClassConstructor', 'InterfaceIsType', 'VisibilityModifier', 
            'FileLength', 'LineLength', 'MethodLength', 'ParameterNumber', 
            'ArrayTypeStyle', 'FinalParameters', 'TodoComment', 'UpperEll', 
            'NewlineAtEndOfFile', 'FileTabCharacter'
        }
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if '**ERROR PATTERNS:**' in line:
                current_section = 'errors'
                continue
            elif '**WARNING PATTERNS:**' in line:
                current_section = 'warnings'
                continue
            elif '**FILE SUMMARY:**' in line:
                current_section = 'summary'
                continue
            
            # Parse patterns
            if (current_section in ['errors', 'warnings'] and line.startswith('- ') and 
                any(module in line for module in checkstyle_modules)):
                
                # Find module name
                module = None
                for mod in checkstyle_modules:
                    if mod in line:
                        module = mod
                        break
                
                if module:
                    # Extract frequency
                    frequency = 1
                    if 'Found' in line and ('time' in line or 'veces' in line):
                        try:
                            freq_part = line.split('Found')[1].split('time')[0].strip()
                            frequency = int(freq_part)
                        except:
                            frequency = 1
                    
                    # Extract description
                    description = f"{module} violation"
                    if ':' in line:
                        desc_part = line.split(':', 1)[1]
                        if ' - Found' in desc_part:
                            description = desc_part.split(' - Found')[0].strip()
                        else:
                            description = desc_part.strip()
                    
                    pattern_info = {'frequency': frequency, 'description': description}
                    
                    if current_section == 'errors':
                        error_patterns[module] = pattern_info
                    else:
                        warning_patterns[module] = pattern_info
            
            # Parse summary
            elif current_section == 'summary':
                if 'Code quality level:' in line or 'quality level:' in line:
                    quality_level = line.split('level:')[1].strip()
        
        return {
            'file': file_name,
            'error_patterns': error_patterns,
            'warning_patterns': warning_patterns,
            'total_error_types': len(error_patterns),
            'total_warning_types': len(warning_patterns),
            'total_error_occurrences': sum(p['frequency'] for p in error_patterns.values()),
            'total_warning_occurrences': sum(p['frequency'] for p in warning_patterns.values()),
            'quality_level': quality_level
        }
