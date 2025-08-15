from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Dict, Any, Union, Optional, List
from datetime import datetime
from decimal import Decimal
import re
import shutil
import json
from pathlib import Path
from core.github_analyzer import GitHubJavaAnalyzer

app = FastAPI(
    title="GitHub Java Code Analyzer API",
    description="API para análisis de código Java en repositorios de GitHub usando Checkstyle y LLM",
    version="1.0.0"
)

class SubmissionDTO(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "assignmentId": 123,
                "assignmentTitle": "Proyecto Gomoku",
                "teamId": 456,
                "teamName": "TeamAlpha",
                "submittedAt": "2025-08-02T10:30:00",
                "fileUrl": "https://github.com/owner/repository",
                "classId": 789,
                "className": "Programación Orientada a Objetos"
            }
        }
    )
    
    id: int
    assignmentId: int
    assignmentTitle: str
    teamId: int
    teamName: str
    submittedAt: Union[datetime, List[int]]
    fileUrl: str
    classId: int
    className: str
    
    @field_validator('submittedAt', mode='before')
    @classmethod
    def parse_submitted_at(cls, v):
        """
        Convierte formatos de fecha desde array o string a datetime
        Acepta: [2025,7,22,16,56,20,950000000] o "2025-08-02T10:30:00"
        """
        if isinstance(v, list) and len(v) >= 6:
            # Formato: [year, month, day, hour, minute, second, microsecond]
            year, month, day, hour, minute, second = v[:6]
            microsecond = v[6] // 1000 if len(v) > 6 else 0  # Convertir nanosegundos a microsegundos
            return datetime(year, month, day, hour, minute, second, microsecond)
        elif isinstance(v, str):
            # Intentar parsear string ISO format
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                return datetime.fromisoformat(v)
        elif isinstance(v, datetime):
            return v
        else:
            raise ValueError(f"Formato de fecha no soportado: {v}")

class EvaluationDTO(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": None,
                "submissionId": 1,
                "evaluatorId": 1,
                "evaluatorName": "GitHub Code Analyzer",
                "evaluationType": "checkstyle",
                "score": 4.25,
                "criteriaJson": "{\"total_errors\": 5, \"total_warnings\": 12, \"patterns\": {...}}",
                "createdAt": "2025-08-02T12:00:00",
                "evaluationDate": "2025-08-02T12:00:00",
                "teamName": "TeamAlpha",
                "assignmentTitle": "Proyecto Gomoku",
                "classId": 789,
                "className": "Programación Orientada a Objetos"
            }
        }
    )
    
    id: Optional[int] = None
    submissionId: int
    evaluatorId: int = 1  # ID fijo para el sistema automatizado
    evaluatorName: str = "GitHub Code Analyzer"
    evaluationType: str
    score: Decimal
    criteriaJson: str
    createdAt: datetime
    evaluationDate: datetime
    teamName: str
    assignmentTitle: str
    classId: int
    className: str

def parse_github_url(url: str) -> tuple[str, str]:
    """
    Extrae owner y repo de una URL de GitHub
    
    Args:
        url: URL del repositorio de GitHub
        
    Returns:
        tuple: (owner, repo)
    """
    pattern = r'https?://github\.com/([^/]+)/([^/]+)/?'
    match = re.match(pattern, url)
    
    if not match:
        raise HTTPException(status_code=400, detail="URL de GitHub inválida")
    
    owner, repo = match.groups()
    # Remover .git si está presente
    if repo.endswith('.git'):
        repo = repo[:-4]
    
    return owner, repo

def calculate_score(analysis_results: Dict[str, Any], analysis_type: str) -> Decimal:
    """
    Calcula un score basado en los resultados del análisis
    
    Args:
        analysis_results: Resultados del análisis
        analysis_type: Tipo de análisis ('checkstyle' o 'llm')
        
    Returns:
        Decimal: Score calculado (0-5)
    """
    if analysis_type == "checkstyle":
        total_files = analysis_results.get('summary', {}).get('total_files', 1)
        total_errors = analysis_results.get('summary', {}).get('total_errors', 0)
        total_warnings = analysis_results.get('summary', {}).get('total_warnings', 0)
        
        # Fórmula: 5 - (errores * 0.1 + warnings * 0.05) / archivos
        penalty = (total_errors * 0.05 + total_warnings * 0.025) / total_files
        score = max(0, 5 - penalty)
        
    elif analysis_type == "llm":
        total_files = analysis_results.get('summary', {}).get('total_files', 1)
        total_errors = analysis_results.get('summary', {}).get('total_error_occurrences', 0)
        total_warnings = analysis_results.get('summary', {}).get('total_warning_occurrences', 0)
        
        # Fórmula: 5 - (errores * 0.075 + warnings * 0.025) / archivos
        penalty = (total_errors * 0.075 + total_warnings * 0.025) / total_files
        score = max(0, 5 - penalty)
        
    else:
        score = 0
    
    return Decimal(str(round(score, 2)))

def clean_downloads_folder() -> Dict[str, Any]:
    """
    Limpia la carpeta analysis/downloads eliminando todos los repositorios descargados
    
    Returns:
        Dict[str, Any]: Resultado de la operación de limpieza
    """
    downloads_path = Path("analysis/downloads")
    
    try:
        if not downloads_path.exists():
            return {
                "success": True,
                "message": "La carpeta de descargas no existe",
                "deleted_repos": 0,
                "freed_space": 0
            }
        
        # Contar repositorios y calcular espacio antes de eliminar
        repo_folders = [folder for folder in downloads_path.iterdir() if folder.is_dir()]
        total_size = 0
        
        for repo_folder in repo_folders:
            for file in repo_folder.rglob("*"):
                if file.is_file():
                    total_size += file.stat().st_size
        
        # Eliminar la carpeta completa y recrearla
        if downloads_path.exists():
            shutil.rmtree(downloads_path)
        
        downloads_path.mkdir(parents=True, exist_ok=True)
        
        return {
            "success": True,
            "message": "Carpeta de descargas limpiada exitosamente",
            "deleted_repos": len(repo_folders),
            "freed_space": total_size,
            "freed_space_mb": round(total_size / (1024 * 1024), 2)
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error al limpiar la carpeta de descargas: {str(e)}",
            "deleted_repos": 0,
            "freed_space": 0
        }

@app.get("/")
async def root():
    """Endpoint de salud de la API"""
    return {
        "message": "GitHub Java Code Analyzer API",
        "status": "active",
        "endpoints": [
            "/checkstyle-analysis",
            "/llm-analysis",
            "/clean"
        ]
    }

@app.delete("/clean")
async def clean_downloads() -> Dict[str, Any]:
    """
    Endpoint para limpiar la carpeta de descargas
    
    Returns:
        Dict[str, Any]: Resultado de la operación de limpieza
    """
    try:
        result = clean_downloads_folder()
        
        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=result["message"]
            )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )

@app.post("/checkstyle-analysis")
async def checkstyle_analysis(request: SubmissionDTO) -> EvaluationDTO:
    """
    Endpoint para análisis con Checkstyle
    
    Args:
        request: Submission DTO con información de la entrega
        
    Returns:
        EvaluationDTO: Resultado de la evaluación con Checkstyle
    """
    try:
        # Parsear URL de GitHub
        owner, repo = parse_github_url(str(request.fileUrl))
        
        # Crear analizador
        analyzer = GitHubJavaAnalyzer(owner, repo)
        
        # Descargar repositorio
        download_success = analyzer.download_repository()
        if not download_success:
            raise HTTPException(
                status_code=500, 
                detail="Error al descargar el repositorio"
            )
        
        # Ejecutar análisis Checkstyle
        results = analyzer.run_checkstyle_analysis(
            xml_config_path="analysis/tools/sun_checks.xml",  # Valor fijo
            submission_id=request.id,  # Usar ID de la entrega
            max_files=100  # Valor fijo
        )
        
        if "error" in results:
            raise HTTPException(
                status_code=500,
                detail=f"Error en análisis Checkstyle: {results['error']}"
            )
        
        # Calcular score
        score = calculate_score(results, "checkstyle")
        
        # Crear EvaluationDTO
        current_time = datetime.now()
        evaluation = EvaluationDTO(
            submissionId=request.id,
            evaluationType="checkstyle",
            score=score,
            criteriaJson=json.dumps(results, default=str),
            createdAt=current_time,
            evaluationDate=current_time,
            teamName=request.teamName,
            assignmentTitle=request.assignmentTitle,
            classId=request.classId,
            className=request.className
        )
        
        return evaluation
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )

@app.post("/llm-analysis")
async def llm_analysis(request: SubmissionDTO) -> EvaluationDTO:
    """
    Endpoint para análisis con LLM
    
    Args:
        request: Submission DTO con información de la entrega
        
    Returns:
        EvaluationDTO: Resultado de la evaluación con LLM
    """
    try:
        # Parsear URL de GitHub
        owner, repo = parse_github_url(str(request.fileUrl))
        
        # Crear analizador
        analyzer = GitHubJavaAnalyzer(owner, repo)
        
        # Descargar repositorio
        download_success = analyzer.download_repository()
        if not download_success:
            raise HTTPException(
                status_code=500,
                detail="Error al descargar el repositorio"
            )
        
        # Ejecutar análisis LLM
        results = analyzer.run_llm_analysis(max_files=100)  # Valor fijo
        
        if "error" in results:
            raise HTTPException(
                status_code=500,
                detail=f"Error en análisis LLM: {results['error']}"
            )
        
        # Calcular score
        score = calculate_score(results, "llm")
        
        # Crear EvaluationDTO
        current_time = datetime.now()
        evaluation = EvaluationDTO(
            submissionId=request.id,
            evaluationType="llm",
            score=score,
            criteriaJson=json.dumps(results, default=str),
            createdAt=current_time,
            evaluationDate=current_time,
            teamName=request.teamName,
            assignmentTitle=request.assignmentTitle,
            classId=request.classId,
            className=request.className
        )
        
        return evaluation
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )

@app.get("/report/{submission_id}", response_class=HTMLResponse)
async def get_html_report(submission_id: str):
    """
    Endpoint para servir reportes HTML de Checkstyle por submission_id
    """
    try:
        # Construir ruta del archivo HTML
        report_path = Path("analysis/reports") / f"{submission_id}_checkstyle_report.html"
        
        # Verificar que el archivo existe
        if not report_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Report not found for submission {submission_id}"
            )
        
        # Leer y retornar el contenido HTML
        with open(report_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        return HTMLResponse(content=html_content, status_code=200)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error serving report: {str(e)}"
        )

@app.get("/report/{submission_id}/download")
async def download_txt_report(submission_id: str):
    """
    Endpoint para descargar reportes TXT de Checkstyle por submission_id
    """
    try:
        # Construir ruta del archivo TXT
        report_path = Path("analysis/reports") / f"{submission_id}_checkstyle_report.txt"
        
        # Verificar que el archivo existe
        if not report_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"TXT report not found for submission {submission_id}"
            )
        
        # Servir el archivo TXT como descarga
        return FileResponse(
            path=report_path,
            media_type='text/plain',
            filename=f"checkstyle_report_{submission_id}.txt"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error serving TXT report: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)