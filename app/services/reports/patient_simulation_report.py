# -*- coding: utf-8 -*-
"""
Generador de Reportes PDF - Simulación de Paciente

Genera reportes de ejecución de protocolos de simulación ECG.
"""

import io
import os
import logging
from typing import Dict, Any, Optional

from app.services.reports.base_report_generator import BaseReportGenerator

log = logging.getLogger(__name__)


class PatientSimulationReportGenerator(BaseReportGenerator):
    """Generador de reportes para el módulo de Simulación de Paciente."""

    MODULE_NAME = "SIMULACIÓN DE PACIENTE"
    MODULE_TITLE = "VALIDACIÓN TRAZABLE — SIMULACIÓN DE PACIENTE"
    MODULE_SUBTITLE = "Simulador ECG"
    MODULE_STANDARD = "Verificación funcional"

    def _add_results_section(self, results: Dict[str, Any]):
        """Tabla de resultados de simulación."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph(
            "RESULTADOS DE SIMULACIÓN", self.style_seccion))

        step_results = results.get('step_results', [])
        if not step_results:
            self.elements.append(Paragraph(
                "No se registraron resultados.", self.styles['Normal']))
            self.elements.append(Spacer(1, 15))
            return

        # Header
        header = ['#', 'Forma de Onda', 'Código', 'Duración (s)', 'Estado']
        data = [header]

        for i, step in enumerate(step_results, 1):
            status = step.get('status', 'pending').upper()
            duration = step.get('duration_actual', 0)
            data.append([
                str(i),
                step.get('waveform_name', '-'),
                step.get('waveform_code', '-'),
                f"{duration:.1f}",
                status,
            ])

        col_widths = [30, 200, 80, 80, 80]
        table = Table(data, colWidths=col_widths, hAlign='LEFT',
                      repeatRows=1)

        style_cmds = [
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (3, 0), (3, -1), 'CENTER'),
            ('ALIGN', (4, 0), (4, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.white, self.COLOR_GRIS_CLARO]),
        ]

        # Color per status
        for row_idx in range(1, len(data)):
            status = data[row_idx][4]
            if status == 'EXECUTED':
                style_cmds.append(
                    ('TEXTCOLOR', (4, row_idx), (4, row_idx), self.COLOR_ACENTO))
            elif status in ('ERROR', 'CANCELLED'):
                style_cmds.append(
                    ('TEXTCOLOR', (4, row_idx), (4, row_idx), self.COLOR_ERROR))

        table.setStyle(TableStyle(style_cmds))
        self.elements.append(table)
        self.elements.append(Spacer(1, 15))

    def generate_report(self, results_data: Dict[str, Any],
                        output_path: Optional[str] = None) -> Optional[str]:
        """Generar reporte PDF completo."""
        from reportlab.platypus import PageBreak

        try:
            self._init_colors_and_styles()
            self.elements = []

            results = results_data.get('results', {}) or {}
            client_info = results_data.get('client', {}) or {}
            equipment_info = results_data.get('equipment', {}) or {}
            protocol_data = results_data.get('protocol', {}) or {}

            protocol_name = (protocol_data.get('name', '')
                             or results.get('protocol_name', '')
                             or 'Simulación de Paciente')

            # Count results
            step_results = results.get('step_results', [])
            passed = sum(1 for s in step_results if s.get('status') == 'executed')
            failed = sum(1 for s in step_results if s.get('status') == 'error')
            skipped = sum(1 for s in step_results
                          if s.get('status') in ('skipped', 'cancelled'))
            overall = results.get('overall_status', '')
            test_passed = (failed == 0 and passed > 0) if step_results else None

            # === PAGE 1 ===
            self._add_title_section(protocol_name, test_passed)
            self._add_client_section(client_info)
            self._add_equipment_section(equipment_info,
                                        "DATOS DEL EQUIPO BAJO PRUEBA (MONITOR)")

            extra = []
            device_model = results.get('device_model', '')
            if device_model:
                extra.append(("Simulador:", device_model))

            self._add_execution_info_section(
                start_time=results.get('start_time'),
                protocol_name=protocol_name,
                passed=passed, failed=failed, skipped=skipped,
                overall_status=overall,
                extra_info=extra if extra else None,
            )
            analyzer_info = {
                'model': device_model,
            }
            self._add_analyzer_section(analyzer_info, "DATOS DEL SIMULADOR")

            self._add_signature_section()
            self.elements.append(PageBreak())

            # === PAGE 2+ ===
            self._add_results_section(results)

            conclusion_pass = (
                f"<b><font color='#10b981'>✓ SIMULACIÓN COMPLETADA:</font></b> "
                f"Todas las formas de onda ({passed}) fueron simuladas correctamente."
            )
            conclusion_fail = (
                f"<b><font color='#ef4444'>✗ SIMULACIÓN CON ERRORES:</font></b> "
                f"{failed} forma(s) de onda presentaron errores durante la simulación."
            )
            self._add_conclusion_section(passed, failed, skipped,
                                          conclusion_pass, conclusion_fail)

            photos = results_data.get('photos', [])
            if photos:
                self._add_photos_section(photos)

            # Build PDF
            buffer = io.BytesIO()
            doc = self._create_pdf_document(buffer)
            doc.build(self.elements)
            buffer.seek(0)

            pdf_bytes = self._add_page_numbers(buffer.getvalue())
            pdf_bytes = self._apply_pdf_security(pdf_bytes)
            pdf_bytes = self._sign_pdf(pdf_bytes)

            if output_path:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(pdf_bytes)
                log.info(f"Reporte generado: {output_path}")
                return output_path

            return None

        except Exception as e:
            log.error(f"Error generando reporte de simulación: {e}")
            return None
