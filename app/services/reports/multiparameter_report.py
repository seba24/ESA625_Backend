# -*- coding: utf-8 -*-
"""
Generador de Reportes PDF - Monitor Multiparamétrico

Genera reportes de verificación de monitores multiparamétricos.
Tablas agrupadas por parámetro (ECG, SpO2, NIBP, IBP, Resp, Temp, CO).
"""

import io
import os
import logging
from typing import Dict, Any, Optional, List

from app.services.reports.base_report_generator import BaseReportGenerator

log = logging.getLogger(__name__)

# Display names for parameter groups
GROUP_NAMES = {
    'ecg': 'ECG',
    'spo2': 'SpO2',
    'nibp': 'NIBP',
    'ibp': 'IBP (Presión Invasiva)',
    'resp': 'Respiración',
    'temp': 'Temperatura',
    'co': 'Gasto Cardíaco',
}


class MPReportGenerator(BaseReportGenerator):
    """Generador de reportes para el módulo de Monitores Multiparamétricos."""

    MODULE_TITLE = "VERIFICACIÓN DE MONITOR MULTIPARAMÉTRICO"
    MODULE_SUBTITLE = "ProSim 8 Patient Simulator"
    MODULE_STANDARD = "IEC 80601-2-49 / IEC 60601-2-25"

    def _add_results_section(self, results: Dict[str, Any]):
        """Tablas de resultados agrupadas por parámetro."""
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        step_results = results.get('step_results', [])
        if not step_results:
            self.elements.append(Paragraph(
                "RESULTADOS DE VERIFICACIÓN", self.style_seccion))
            self.elements.append(Paragraph(
                "No se registraron resultados.", self.styles['Normal']))
            self.elements.append(Spacer(1, 15))
            return

        # Group results by parameter_group
        groups: Dict[str, List[Dict]] = {}
        for step in step_results:
            gid = step.get('parameter_group', 'otros')
            if gid not in groups:
                groups[gid] = []
            groups[gid].append(step)

        for gid, steps in groups.items():
            group_name = GROUP_NAMES.get(gid, gid.upper())
            self.elements.append(Paragraph(
                f"RESULTADOS — {group_name}", self.style_seccion))

            header = ['#', 'Parámetro', 'Valor Simulado', 'Valor Medido',
                      'Unidad', 'Tolerancia', 'Resultado']
            data = [header]

            for i, step in enumerate(steps, 1):
                status = step.get('status', 'pending').upper()
                sim_val = step.get('sim_value', '-')
                measured = step.get('measured_value')
                measured_str = f"{measured}" if measured is not None else '-'

                data.append([
                    str(i),
                    step.get('test_name', '-'),
                    str(sim_val),
                    measured_str,
                    step.get('unit', ''),
                    step.get('tolerance_str', '-'),
                    status,
                ])

            col_widths = [25, 130, 65, 65, 45, 80, 60]
            table = Table(data, colWidths=col_widths, hAlign='LEFT',
                          repeatRows=1)

            style_cmds = [
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (2, 0), (3, -1), 'CENTER'),
                ('ALIGN', (6, 0), (6, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1),
                 [colors.white, self.COLOR_GRIS_CLARO]),
            ]

            # Color per status
            for row_idx in range(1, len(data)):
                status = data[row_idx][6]
                if status == 'PASS':
                    style_cmds.append(
                        ('TEXTCOLOR', (6, row_idx), (6, row_idx), self.COLOR_ACENTO))
                elif status in ('FAIL',):
                    style_cmds.append(
                        ('TEXTCOLOR', (6, row_idx), (6, row_idx), self.COLOR_ERROR))
                elif status in ('SKIPPED', 'ERROR'):
                    style_cmds.append(
                        ('TEXTCOLOR', (6, row_idx), (6, row_idx), self.COLOR_ADVERTENCIA))

            table.setStyle(TableStyle(style_cmds))
            self.elements.append(table)

            # Group summary
            passed = sum(1 for s in steps if s.get('status') == 'pass')
            failed = sum(1 for s in steps if s.get('status') == 'fail')
            total = len(steps)
            summary_text = (
                f"<b>{group_name}:</b> {passed}/{total} aprobados"
            )
            if failed > 0:
                summary_text += f", <font color='#ef4444'><b>{failed} rechazados</b></font>"
            self.elements.append(Paragraph(summary_text, self.styles['Normal']))
            self.elements.append(Spacer(1, 10))

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
                             or 'Verificación de Monitor')

            # Count results
            step_results = results.get('step_results', [])
            passed = sum(1 for s in step_results if s.get('status') == 'pass')
            failed = sum(1 for s in step_results if s.get('status') == 'fail')
            skipped = sum(1 for s in step_results
                          if s.get('status') in ('skipped', 'error'))
            overall = results.get('overall_status', '')
            test_passed = (failed == 0 and passed > 0) if step_results else None

            # === PAGE 1 ===
            self._add_title_section(protocol_name, test_passed)
            self._add_client_section(client_info)
            self._add_equipment_section(equipment_info,
                                        "DATOS DEL EQUIPO BAJO PRUEBA (MONITOR)")

            extra = []
            monitor_brand = results.get('monitor_brand', '')
            monitor_model = results.get('monitor_model', '')
            if monitor_brand or monitor_model:
                extra.append(("Monitor:", f"{monitor_brand} {monitor_model}".strip()))

            self._add_execution_info_section(
                start_time=results.get('start_time'),
                protocol_name=protocol_name,
                passed=passed, failed=failed, skipped=skipped,
                overall_status=overall,
                extra_info=extra if extra else None,
            )
            analyzer_info = {'model': 'ProSim 8', 'serial': ''}
            self._add_analyzer_section(analyzer_info,
                                        "DATOS DEL SIMULADOR (PROSIM 8)")

            self._add_signature_section()
            self.elements.append(PageBreak())

            # === PAGE 2+ ===
            self._add_results_section(results)

            conclusion_pass = (
                f"<b><font color='#10b981'>✓ MONITOR APROBADO:</font></b> "
                f"Todos los parámetros verificados ({passed}) están dentro de las "
                f"tolerancias especificadas por las normas IEC/ISO aplicables."
            )
            conclusion_fail = (
                f"<b><font color='#ef4444'>✗ MONITOR NO APROBADO:</font></b> "
                f"{failed} parámetro(s) fuera de tolerancia. "
                f"Se requiere calibración o mantenimiento del monitor."
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
                log.info(f"Reporte MP generado: {output_path}")
                return output_path

            return None

        except Exception as e:
            log.error(f"Error generando reporte de monitor MP: {e}")
            return None
