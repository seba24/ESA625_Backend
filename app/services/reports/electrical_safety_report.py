# -*- coding: utf-8 -*-
"""
Generador de Reportes PDF para Seguridad Eléctrica
Genera reportes profesionales de pruebas según IEC 62353 / IEC 60601-1

Hereda de BaseReportGenerator para mantener formato consistente con otros módulos.

Incluye:
- Primera página estandarizada (cliente, equipo, resumen, firmas)
- Tabla de mediciones eléctricas con límites normativos
- Conclusiones según norma aplicable
"""

import io
import os
import datetime
import tempfile
from typing import Dict, Any, List, Optional
import logging

from app.services.reports.base_report_generator import BaseReportGenerator

log = logging.getLogger(__name__)


# Nombres legibles para mediciones de seguridad eléctrica
MEASUREMENT_DISPLAY_NAMES = {
    'earth_resistance': 'Resistencia de Tierra Protectora',
    'insulation_main': 'Resistencia de Aislación (Red-Tierra)',
    'insulation_applied_parts': 'Resistencia de Aislación (Partes Aplicadas)',
    'earth_leakage': 'Corriente de Fuga a Tierra',
    'equipment_leakage': 'Corriente de Fuga del Equipo',
    'enclosure_leakage': 'Corriente de Fuga de Carcasa',
    'patient_leakage': 'Corriente de Fuga del Paciente',
    'patient_auxiliary_leakage': 'Corriente Auxiliar del Paciente',
    'direct_equipment_leakage': 'Fuga Directa del Equipo',
    'direct_applied_part_leakage': 'Fuga Directa Partes Aplicadas',
}


class ElectricalSafetyReportGenerator(BaseReportGenerator):
    """
    Generador de reportes PDF para pruebas de seguridad eléctrica.

    Hereda de BaseReportGenerator para mantener formato consistente.
    La primera página tiene el mismo formato que los demás módulos.
    """

    MODULE_TITLE = "TEST DE SEGURIDAD ELÉCTRICA"
    MODULE_SUBTITLE = "Analizador de Seguridad Eléctrica"
    MODULE_STANDARD = "IEC 62353 / IEC 60601-1"

    def __init__(self):
        super().__init__()

    def generate_report(self,
                        results_data: Dict[str, Any],
                        output_path: Optional[str] = None) -> Optional[str]:
        """
        Generar reporte PDF de resultados de seguridad eléctrica.

        Args:
            results_data: Diccionario con datos del reporte:
                - results: dict con overall_status, measurements (list o dict)
                - client: dict con datos del cliente
                - equipment: dict con datos del equipo
                - protocol: dict con datos del protocolo
                - analyzer: dict con modelo y serie del analizador
            output_path: Ruta de salida opcional.

        Returns:
            Ruta del archivo generado o None si hay error
        """
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

        # Configurar logo y empresa desde el protocolo
        if isinstance(protocol_info, dict):
            if not self.company_name and protocol_info.get('company_name'):
                self.company_name = protocol_info['company_name']
            if not self.logo_path and protocol_info.get('logo_path'):
                logo = protocol_info['logo_path']
                if os.path.exists(logo):
                    self.logo_path = logo

        # Obtener datos de mediciones
        measurements = results.get('measurements', [])

        # Normalizar: puede venir como dict (nombre→resultado) o lista
        if isinstance(measurements, dict):
            meas_list = []
            for name, meas in measurements.items():
                if isinstance(meas, dict):
                    meas['parameter'] = meas.get('parameter', MEASUREMENT_DISPLAY_NAMES.get(name, name))
                    meas_list.append(meas)
                else:
                    meas_list.append({
                        'parameter': MEASUREMENT_DISPLAY_NAMES.get(name, name),
                        'measured': meas,
                        'passed': True,
                    })
            measurements = meas_list

        # Calcular contadores
        passed = sum(1 for m in measurements if m.get('passed', False)
                     or m.get('evaluation', '') == 'PASS')
        failed = sum(1 for m in measurements if not m.get('passed', True)
                     and m.get('evaluation', 'PASS') != 'PASS')
        total = len(measurements)
        test_passed = (failed == 0 and passed > 0)

        overall_status = results.get('overall_status', 'PASS' if test_passed else 'FAIL')
        if overall_status in ('APROBADO', 'PASS'):
            test_passed = True
        elif overall_status in ('RECHAZADO', 'FAIL'):
            test_passed = False

        protocol_name = protocol_info.get('name', 'Protocolo de Seguridad Eléctrica')
        standard = protocol_info.get('standard', self.MODULE_STANDARD)

        # Actualizar subtítulo con modelo de analizador
        analyzer_model = analyzer_info.get('model', '')
        if analyzer_model:
            self.MODULE_SUBTITLE = f"Analizador {analyzer_model}"

        # Actualizar estándar
        if standard:
            self.MODULE_STANDARD = standard

        # ========== PRIMERA PÁGINA ==========

        self._add_title_section(protocol_name, test_passed)
        self._add_client_section(client_info)

        # Datos del equipo bajo prueba
        self._add_equipment_section(equipment_info, "DATOS DEL EQUIPO BAJO PRUEBA")

        # Info adicional: clase de equipo, tipo de partes aplicadas
        extra_info = []
        equipment_class = equipment_info.get('class', '') or protocol_info.get('equipment_class', '')
        applied_parts_type = equipment_info.get('applied_parts_type', '') or protocol_info.get('applied_parts_type', '')

        if equipment_class:
            extra_info.append(("Clase del Equipo:", f"Clase {equipment_class}"))
        if applied_parts_type:
            extra_info.append(("Tipo Partes Aplicadas:", applied_parts_type))
        if standard:
            extra_info.append(("Norma:", standard))

        self._add_execution_info_section(
            start_time=results.get('start_time'),
            protocol_name=protocol_name,
            passed=passed,
            failed=failed,
            skipped=0,
            overall_status='pass' if test_passed else 'fail',
            extra_info=extra_info if extra_info else None
        )

        self._add_analyzer_section(analyzer_info, "ANALIZADOR UTILIZADO")

        self._add_signature_section()

        # Salto de página para resultados detallados
        self.elements.append(PageBreak())

        # ========== SEGUNDA PÁGINA+ ==========

        self._add_safety_results(measurements)

        # Conclusiones
        conclusion_pass = (
            f"<b><font color='#10b981'>✓ EQUIPO APROBADO:</font></b> "
            f"El equipo ha superado todas las pruebas de seguridad eléctrica. "
            f"Todas las mediciones ({passed}) están dentro de los límites "
            f"establecidos por {self.MODULE_STANDARD}."
        )
        conclusion_fail = (
            f"<b><font color='#ef4444'>✗ EQUIPO NO APROBADO:</font></b> "
            f"El equipo presenta {failed} mediciones fuera de los límites normativos. "
            "Se requiere reparación o mantenimiento antes de su uso clínico. "
            "Las mediciones marcadas en rojo están fuera del rango permitido."
        )
        self._add_conclusion_section(passed, failed, 0, conclusion_pass, conclusion_fail)

        # Generar ruta de salida
        if not output_path:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            protocol_name_file = protocol_name.replace(' ', '_')
            output_path = os.path.join(tempfile.gettempdir(),
                                       f"Seguridad_{protocol_name_file}_{timestamp}.pdf")

        # Crear PDF
        buffer = io.BytesIO()
        doc = self._create_pdf_document(buffer)
        doc.build(self.elements)

        buffer.seek(0)
        pdf_bytes = self._add_page_numbers(buffer.getvalue())
        pdf_bytes = self._apply_pdf_security(pdf_bytes)
        pdf_bytes = self._sign_pdf(pdf_bytes)
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)

        log.info(f"Reporte PDF seguridad eléctrica generado: {output_path}")
        return output_path

    def _add_safety_results(self, measurements: List[Dict[str, Any]]):
        """
        Agregar tabla de resultados de seguridad eléctrica.
        Columnas: Medición | Valor | Unidad | Límite | Evaluación
        """
        from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors

        self.elements.append(Paragraph(
            "RESULTADOS DE SEGURIDAD ELÉCTRICA",
            self.style_seccion))

        if not measurements:
            self.elements.append(Paragraph(
                "No hay mediciones registradas.", self.styles['Normal']))
            return

        data = [["Medición", "Valor", "Unidad", "Límite", "Evaluación"]]

        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 1), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
        ])

        row_index = 1

        for m in measurements:
            param_name = m.get('parameter', 'N/A')
            measured = m.get('measured', m.get('value', 'N/A'))
            unit = m.get('unit', '')
            limit_val = m.get('limit', m.get('tolerance', ''))
            evaluation = m.get('evaluation', '')

            # Si no hay evaluation, derivar de passed
            if not evaluation:
                passed = m.get('passed', True)
                evaluation = 'PASS' if passed else 'FAIL'

            is_pass = evaluation in ('PASS', 'APROBADO')

            # Formatear valor
            if isinstance(measured, (int, float)):
                meas_str = f"{measured:.3f}" if abs(measured) < 10 else f"{measured:.1f}"
            else:
                meas_str = str(measured)

            limit_str = str(limit_val) if limit_val else ""
            eval_str = "APROBADO" if is_pass else "RECHAZADO"

            data.append([param_name, meas_str, unit, limit_str, eval_str])

            if row_index % 2 == 0:
                table_style.add('BACKGROUND', (0, row_index), (-1, row_index),
                                self.COLOR_GRIS_CLARO)

            if is_pass:
                table_style.add('TEXTCOLOR', (4, row_index), (4, row_index),
                                self.COLOR_ACENTO)
                table_style.add('FONTNAME', (4, row_index), (4, row_index),
                                'Helvetica-Bold')
            else:
                table_style.add('BACKGROUND', (0, row_index), (-1, row_index),
                                colors.HexColor('#fee2e2'))
                table_style.add('TEXTCOLOR', (0, row_index), (-1, row_index),
                                self.COLOR_ERROR)
                table_style.add('FONTNAME', (0, row_index), (-1, row_index),
                                'Helvetica-Bold')

            row_index += 1

        tabla = Table(data, colWidths=[160, 70, 70, 90, 80], hAlign='CENTER',
                      repeatRows=1)
        tabla.setStyle(table_style)
        self.elements.append(tabla)
        self.elements.append(Spacer(1, 15))
