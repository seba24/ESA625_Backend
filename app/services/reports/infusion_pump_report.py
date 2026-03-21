# -*- coding: utf-8 -*-
"""
Generador de Reportes PDF para Bombas de Infusión
Genera reportes profesionales de pruebas IDA-4 Plus

Hereda de BaseReportGenerator para formato consistente.
"""

import io
import datetime
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

from app.services.reports.base_report_generator import BaseReportGenerator

log = logging.getLogger(__name__)


class InfusionPumpReportGenerator(BaseReportGenerator):
    """Generador de reportes PDF para pruebas de bombas de infusión."""

    MODULE_TITLE = "PRUEBA DE BOMBA DE INFUSIÓN"
    MODULE_SUBTITLE = "Analizador de Dispositivos de Infusión"
    MODULE_STANDARD = "IEC 60601-2-24"

    def __init__(self):
        super().__init__()

    def generate_report(self, results_data: Dict[str, Any],
                        output_path: Optional[str] = None) -> Optional[str]:
        try:
            from reportlab.platypus import PageBreak, Spacer
        except ImportError as e:
            log.error(f"Dependencia no instalada: {e}")
            return None

        self._init_colors_and_styles()
        self.elements = []

        if not results_data:
            log.error("results_data es None o vacío")
            return None

        results = results_data.get('results', {}) or {}
        client_info = results_data.get('client', {}) or {}
        equipment_info = results_data.get('equipment', {}) or {}
        protocol_info = results_data.get('protocol', {}) or {}
        analyzer_info = results_data.get('analyzer', {}) or {}

        # Logo y empresa desde protocolo
        if isinstance(protocol_info, dict):
            if not self.company_name and protocol_info.get('company_name'):
                self.company_name = protocol_info['company_name']
            if not self.logo_path and protocol_info.get('logo_path'):
                import os
                logo = protocol_info['logo_path']
                if os.path.exists(logo):
                    self.logo_path = logo

        # Contadores
        test_results = results.get('test_results', [])
        measurements = results.get('measurements', [])
        passed = results.get('passed_tests', sum(1 for m in measurements if m.get('passed', False)))
        failed = results.get('failed_tests', sum(1 for m in measurements if not m.get('passed', True)))
        total = passed + failed
        test_passed = (failed == 0 and passed > 0)
        protocol_name = protocol_info.get('name', results.get('protocol_name', 'Protocolo de Infusión'))

        # Subtítulo con modelo de analizador
        analyzer_model = analyzer_info.get('model', results.get('analyzer', ''))
        if analyzer_model:
            self.MODULE_SUBTITLE = f"Analizador {analyzer_model}"

        # ========== PRIMERA PÁGINA ==========
        self._add_title_section(protocol_name, test_passed)
        self._add_client_section(client_info)
        self._add_equipment_section(equipment_info, "DATOS DEL EQUIPO BAJO PRUEBA (BOMBA DE INFUSIÓN)")

        extra_info = []
        pump_manufacturer = equipment_info.get('marca', '') or protocol_info.get('pump_manufacturer', '')
        pump_model = equipment_info.get('modelo', '') or protocol_info.get('pump_model', '')
        if pump_manufacturer:
            extra_info.append(("Fabricante Bomba:", pump_manufacturer))
        if pump_model:
            extra_info.append(("Modelo Bomba:", pump_model))

        standard = protocol_info.get('standard', self.MODULE_STANDARD)
        extra_info.append(("Norma:", standard))

        self._add_execution_info_section(
            start_time=results.get('start_time'),
            protocol_name=protocol_name,
            passed=passed,
            failed=failed,
            skipped=0,
            overall_status='pass' if test_passed else 'fail',
            extra_info=extra_info if extra_info else None,
        )

        self._add_analyzer_section(analyzer_info, "ANALIZADOR UTILIZADO")

        self._add_signature_section()
        self.elements.append(PageBreak())

        # ========== SEGUNDA PÁGINA+ ==========

        # Tabla de resultados
        if test_results:
            self._add_infusion_results_table(test_results)
        elif measurements:
            self._add_results_section(results)

        # Fotos
        photos = results_data.get('photos', [])
        if photos:
            self._add_photos_section(photos)

        # Conclusiones
        conclusion_pass = (
            f"<b><font color='#10b981'>✓ EQUIPO APROBADO:</font></b> "
            f"La bomba de infusión ha superado todas las pruebas. "
            f"Las {passed} mediciones están dentro de la tolerancia especificada "
            f"según {standard}."
        )
        conclusion_fail = (
            f"<b><font color='#ef4444'>✗ EQUIPO NO APROBADO:</font></b> "
            f"La bomba presenta {failed} mediciones fuera de tolerancia. "
            "Se requiere calibración o mantenimiento preventivo. "
            "Las mediciones en rojo exceden el rango permitido."
        )
        self._add_conclusion_section(passed, failed, 0, conclusion_pass, conclusion_fail)

        # Ruta de salida
        if not output_path:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = protocol_name.replace(' ', '_')
            import tempfile
            output_dir = tempfile.gettempdir()
            output_path = os.path.join(output_dir, f"Infusion_{safe_name}_{timestamp}.pdf")

        # Generar PDF
        buffer = io.BytesIO()
        doc = self._create_pdf_document(buffer)
        doc.build(self.elements)

        buffer.seek(0)
        pdf_bytes = self._add_page_numbers(buffer.getvalue())
        pdf_bytes = self._apply_pdf_security(pdf_bytes)
        pdf_bytes = self._sign_pdf(pdf_bytes)
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)

        log.info(f"Reporte PDF infusión generado: {output_path}")
        return output_path

    def _add_infusion_results_table(self, test_results: List[Dict[str, Any]]):
        """Tabla de resultados de pruebas de infusión."""
        from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph("RESULTADOS DE MEDICIONES", self.style_seccion))
        self.elements.append(Spacer(1, 6))

        # Agrupar por tipo de test
        groups = {}
        for r in test_results:
            test_type = r.get('test_type', 'unknown')
            groups.setdefault(test_type, []).append(r)

        type_titles = {
            'flow_rate': 'TASA DE FLUJO',
            'volume': 'VOLUMEN',
            'occlusion': 'PRESIÓN DE OCLUSIÓN',
            'pca': 'PCA (BOLUS)',
            'dual_flow': 'FLUJO DUAL',
        }

        for test_type, items in groups.items():
            title = type_titles.get(test_type, test_type.upper())
            self.elements.append(Paragraph(title, self.style_subseccion))
            self.elements.append(Spacer(1, 4))

            if test_type == 'occlusion':
                # Tabla de oclusión: Canal | Presión Máx | Límite | Estado
                data = [["Canal", "Presión Medida", "Límite Máximo", "Estado"]]
                for r in items:
                    ch = r.get('channel', 1)
                    measured = r.get('measured_value', 0)
                    limit_val = r.get('set_value', r.get('tolerance', 0))
                    unit = r.get('unit', 'psi')
                    passed = r.get('passed', False)
                    status = "APROBADO" if passed else "RECHAZADO"
                    data.append([
                        f"CH {ch}",
                        f"{measured} {unit}",
                        f"≤ {limit_val} {unit}",
                        status,
                    ])
                col_widths = [60, 120, 120, 100]
            else:
                # Tabla estándar: Canal | Programado | Medido | Error% | Tolerancia | Estado
                data = [["Canal", "Programado", "Medido", "Error %", "Tolerancia", "Estado"]]
                for r in items:
                    ch = r.get('channel', 1)
                    set_val = r.get('set_value', 0)
                    measured = r.get('measured_value', 0)
                    error = r.get('error_percent', 0)
                    tol = r.get('tolerance', 0)
                    unit = r.get('unit', '')
                    passed = r.get('passed', False)
                    status = "APROBADO" if passed else "RECHAZADO"
                    data.append([
                        f"CH {ch}",
                        f"{set_val} {unit}",
                        f"{measured} {unit}",
                        f"{error:.1f}%",
                        f"±{tol}%",
                        status,
                    ])
                col_widths = [50, 90, 90, 65, 75, 80]

            table = Table(data, colWidths=col_widths, hAlign='LEFT')
            style_commands = [
                ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]

            # Colorear filas pass/fail
            for i, r in enumerate(items, start=1):
                if r.get('passed', False):
                    style_commands.append(('TEXTCOLOR', (-1, i), (-1, i), colors.HexColor('#10b981')))
                else:
                    style_commands.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fef2f2')))
                    style_commands.append(('TEXTCOLOR', (-1, i), (-1, i), colors.HexColor('#ef4444')))
                # Alterno fondo
                if i % 2 == 0:
                    style_commands.append(('BACKGROUND', (0, i), (-1, i), self.COLOR_GRIS_CLARO))

            table.setStyle(TableStyle(style_commands))
            self.elements.append(table)
            self.elements.append(Spacer(1, 12))
